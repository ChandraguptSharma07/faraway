"""Persistent journey telemetry, event indexing, and accessible audit exports."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import sqlite3
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "aeropinn-journey-v1"
FIELD_DOCUMENTATION = {
    "schema_version": "Journey export schema identifier.",
    "session_id": "Stable unique journey identifier.",
    "recorded_at": "Server capture timestamp in ISO 8601 UTC.",
    "location.route_chainage_km": "Distance marker along the configured route, in kilometres.",
    "location.latitude": "Interpolated WGS84 latitude for the configured scenario path.",
    "location.longitude": "Interpolated WGS84 longitude for the configured scenario path.",
    "telemetry.t": "Elapsed simulation time in seconds.",
    "telemetry.speed_kmh": "Train speed in kilometres per hour.",
    "telemetry.tension_factor": "Contact-wire tension multiplier relative to nominal.",
    "telemetry.turbulence_gain": "Stochastic turbulence amplitude multiplier.",
    "telemetry.gust_active": "True while a transient gust remains active.",
    "telemetry.passive.contact_force": "Passive pantograph contact force in newtons.",
    "telemetry.aeropinn.contact_force": "Controlled pantograph contact force in newtons.",
    "telemetry.passive.contact_lost": "Passive-lane zero-contact indicator.",
    "telemetry.aeropinn.contact_lost": "Controlled-lane zero-contact indicator.",
    "telemetry.aeropinn.f_command": "Controller-requested actuator force in newtons.",
    "telemetry.aeropinn.f_actuator_estimate": "Simulated actuator applied-force estimate in newtons.",
    "telemetry.pinn_latency_ms": "Most recent PINN inference time in milliseconds.",
    "constants": "Periodic configuration snapshot used to reproduce the simulation.",
}
DEFAULT_METADATA = {
    "train_name": "Lastochka",
    "train_id": "LASTOCHKA-DEMO-01",
    "route_name": "AeroPINN Test Corridor A",
    "route_id": "AP-TCA-01",
    "origin": "Sector A",
    "destination": "Sector B",
    "direction": "UP",
    "track": "1",
    "start_chainage_km": 120.0,
    "end_chainage_km": 126.0,
    "start_latitude": 18.5204,
    "start_longitude": 73.8567,
    "end_latitude": 18.5650,
    "end_longitude": 73.9140,
    "ambient_temperature_C": 32.0,
    "wire_temperature_C": 38.0,
    "wind_speed_m_s": 4.0,
    "weather": "clear",
    "scenario_name": "Nominal journey",
    "data_source": "SIMULATION",
    "is_sample": False,
}

EDITABLE_METADATA = frozenset(DEFAULT_METADATA) - {"data_source", "is_sample"}
NUMERIC_METADATA = {
    "start_chainage_km",
    "end_chainage_km",
    "start_latitude",
    "start_longitude",
    "end_latitude",
    "end_longitude",
    "ambient_temperature_C",
    "wire_temperature_C",
    "wind_speed_m_s",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_data_root() -> Path:
    configured = os.getenv("AEROPINN_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "journeys"


def _flatten(value: dict, prefix: str = "") -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            output.update(_flatten(item, name))
        elif isinstance(item, (list, tuple)):
            output[name] = json.dumps(item, separators=(",", ":"))
        else:
            output[name] = item
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _describe_field(field: str) -> str:
    if field in FIELD_DOCUMENTATION:
        return FIELD_DOCUMENTATION[field]
    units = {
        "_N": "newtons",
        "_mm": "millimetres",
        "_mm_s": "millimetres per second",
        "_ms": "milliseconds",
        "_m_s": "metres per second",
        "_m": "metres",
        "_hz": "hertz",
        "_pct": "percent",
        "_C": "degrees Celsius",
    }
    for suffix, unit in units.items():
        if field.endswith(suffix):
            return f"Telemetry value in {unit}; see the nested JSON context for its subsystem."
    return "Documented telemetry value preserved from the live simulation frame."


def _validate_metadata(changes: dict) -> dict:
    unsupported = set(changes) - EDITABLE_METADATA
    if unsupported:
        raise ValueError(f"unsupported metadata fields: {', '.join(sorted(unsupported))}")
    clean = {}
    for key, value in changes.items():
        if key in NUMERIC_METADATA:
            if isinstance(value, bool):
                raise ValueError(f"{key} must be numeric")
            try:
                value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be numeric") from exc
            if not math.isfinite(value):
                raise ValueError(f"{key} must be finite")
        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be non-empty text")
            value = value.strip()
            if len(value) > 200:
                raise ValueError(f"{key} must be at most 200 characters")
        clean[key] = value
    for key in ("start_latitude", "end_latitude"):
        if key in clean and not -90.0 <= clean[key] <= 90.0:
            raise ValueError(f"{key} must be between -90 and 90")
    for key in ("start_longitude", "end_longitude"):
        if key in clean and not -180.0 <= clean[key] <= 180.0:
            raise ValueError(f"{key} must be between -180 and 180")
    if clean.get("wind_speed_m_s", 0.0) < 0.0:
        raise ValueError("wind_speed_m_s cannot be negative")
    return clean


class JourneyStore:
    def __init__(self, root: Path | None = None):
        self.root = (root or _project_data_root()).resolve()
        self.telemetry_dir = self.root / "telemetry"
        self.events_dir = self.root / "events"
        self.export_dir = self.root / "exports"
        for directory in (self.root, self.telemetry_dir, self.events_dir, self.export_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.root / "journeys.sqlite3", check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._active: dict[str, JourneySession] = {}
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS journeys (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    telemetry_file TEXT NOT NULL,
                    events_file TEXT NOT NULL,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    event_count INTEGER NOT NULL DEFAULT 0,
                    schema_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    journey_id TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                """
            )
            self._connection.execute(
                "UPDATE journeys SET status='INTERRUPTED', ended_at=? "
                "WHERE status='RUNNING'",
                (_utc_now(),),
            )

    def create(self, metadata: dict | None = None) -> "JourneySession":
        journey_id = uuid.uuid4().hex
        supplied = dict(metadata or {})
        internal = {
            key: supplied.pop(key)
            for key in tuple(supplied)
            if key in {"data_source", "is_sample"}
        }
        details = {**DEFAULT_METADATA, **_validate_metadata(supplied), **internal}
        started_at = _utc_now()
        telemetry_path = self.telemetry_dir / f"{journey_id}.ndjson"
        events_path = self.events_dir / f"{journey_id}.ndjson"
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO journeys
                (id, started_at, status, metadata_json, summary_json,
                 telemetry_file, events_file, schema_version)
                VALUES (?, ?, 'RUNNING', ?, '{}', ?, ?, ?)""",
                (
                    journey_id,
                    started_at,
                    json.dumps(details),
                    str(telemetry_path),
                    str(events_path),
                    SCHEMA_VERSION,
                ),
            )
            self._audit("CREATED", journey_id, {"metadata": details})
        session = JourneySession(self, journey_id, started_at, details)
        with self._lock:
            self._active[journey_id] = session
        return session

    def _audit(self, action: str, journey_id: str, details: dict | None = None) -> None:
        self._connection.execute(
            "INSERT INTO audit_log(recorded_at, action, journey_id, details_json) "
            "VALUES (?, ?, ?, ?)",
            (_utc_now(), action, journey_id, json.dumps(details or {})),
        )

    def update_metadata(self, journey_id: str, changes: dict) -> dict:
        clean = _validate_metadata(changes)
        if not clean:
            raise ValueError("no supported metadata fields supplied")
        with self._lock, self._connection:
            row = self._row(journey_id)
            metadata = json.loads(row["metadata_json"])
            metadata.update(clean)
            self._connection.execute(
                "UPDATE journeys SET metadata_json=? WHERE id=?",
                (json.dumps(metadata), journey_id),
            )
            self._audit("METADATA_UPDATED", journey_id, {"fields": sorted(clean)})
            active = self._active.get(journey_id)
            if active is not None:
                active.metadata = metadata
                active.event("METADATA_UPDATED", {"fields": sorted(clean)})
            return metadata

    def list(self, include_archived: bool = False) -> list[dict]:
        clause = "" if include_archived else "WHERE archived=0"
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM journeys {clause} ORDER BY started_at DESC"
            ).fetchall()
        return [self._serialize(row, include_paths=False) for row in rows]

    def get(self, journey_id: str) -> dict:
        with self._lock:
            return self._serialize(self._row(journey_id), include_paths=False)

    def has_sample(self) -> bool:
        with self._lock:
            rows = self._connection.execute("SELECT metadata_json FROM journeys").fetchall()
        return any(json.loads(row[0]).get("is_sample") for row in rows)

    def archive(self, journey_id: str) -> dict:
        with self._lock, self._connection:
            row = self._row(journey_id)
            if row["status"] == "RUNNING":
                raise ValueError("a running journey cannot be archived")
            self._connection.execute(
                "UPDATE journeys SET archived=1 WHERE id=?", (journey_id,)
            )
            self._audit("ARCHIVED", journey_id)
        return self.get(journey_id)

    def delete(self, journey_id: str, confirmation: str) -> None:
        if confirmation != journey_id:
            raise ValueError("confirmation must exactly match the journey id")
        with self._lock, self._connection:
            row = self._row(journey_id)
            if row["status"] == "RUNNING":
                raise ValueError("a running journey cannot be deleted")
            paths = [Path(row["telemetry_file"]), Path(row["events_file"])]
            self._audit("PERMANENTLY_DELETED", journey_id, {
                "started_at": row["started_at"],
                "metadata": json.loads(row["metadata_json"]),
            })
            self._connection.execute("DELETE FROM journeys WHERE id=?", (journey_id,))
            for path in paths:
                path.unlink(missing_ok=True)
            for path in self.export_dir.glob(f"{journey_id}.*"):
                path.unlink(missing_ok=True)

    def export(self, journey_id: str, kind: str) -> tuple[Path, str]:
        if kind not in {"csv", "json", "audit"}:
            raise ValueError("format must be csv, json, or audit")
        with self._lock:
            row = self._row(journey_id)
            journey = self._serialize(row, include_paths=True)
        telemetry_path = Path(journey.pop("telemetry_file"))
        events_path = Path(journey.pop("events_file"))
        telemetry_size = telemetry_path.stat().st_size if telemetry_path.exists() else 0
        events_size = events_path.stat().st_size if events_path.exists() else 0
        if kind == "csv":
            destination = self.export_dir / f"{journey_id}.telemetry.csv"
            self._write_csv_snapshot(telemetry_path, telemetry_size, destination)
            return destination, "text/csv"
        if kind == "json":
            destination = self.export_dir / f"{journey_id}.journey.json"
            self._write_json_export(
                destination,
                journey,
                telemetry_path,
                telemetry_size,
                events_path,
                events_size,
            )
            return destination, "application/json"

        return self._write_audit_package(
            journey_id,
            journey,
            telemetry_path,
            telemetry_size,
            events_path,
            events_size,
        )

    def page(
        self,
        journey_id: str,
        source: str,
        cursor: int = 0,
        limit: int = 25,
        stream: str | None = None,
    ) -> dict:
        """Read a bounded NDJSON page using byte cursors, never whole-file loading."""
        if source not in {"telemetry", "events"}:
            raise ValueError("source must be telemetry or events")
        if cursor < 0:
            raise ValueError("cursor cannot be negative")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if stream not in {
            None,
            "physics_audit_1khz",
            "dashboard_frame_30hz",
            "configuration_snapshot_1hz",
        }:
            raise ValueError("unsupported telemetry stream")
        if source == "events" and stream is not None:
            raise ValueError("stream filtering only applies to telemetry")

        with self._lock:
            row = self._row(journey_id)
            path = Path(row[f"{source}_file"])
        size = path.stat().st_size if path.exists() else 0
        if cursor > size:
            raise ValueError("cursor is beyond the current log snapshot")

        records: list[dict] = []
        next_cursor: int | None = None
        if path.exists():
            with path.open("rb") as handle:
                handle.seek(cursor)
                if cursor:
                    handle.seek(cursor - 1)
                    if handle.read(1) != b"\n":
                        handle.readline()
                while handle.tell() < size and len(records) < limit:
                    raw = handle.readline()
                    if not raw or handle.tell() > size:
                        break
                    record = json.loads(raw)
                    if stream is None or record.get("stream") == stream:
                        records.append(record)
                if handle.tell() < size:
                    next_cursor = handle.tell()
        return {
            "journey_id": journey_id,
            "source": source,
            "stream": stream,
            "cursor": cursor,
            "next_cursor": next_cursor,
            "snapshot_bytes": size,
            "records": records,
        }

    def _write_audit_package(
        self,
        journey_id: str,
        journey: dict,
        telemetry_path: Path,
        telemetry_size: int,
        events_path: Path,
        events_size: int,
    ) -> tuple[Path, str]:
        export_token = uuid.uuid4().hex
        work = self.export_dir / f"{journey_id}.{export_token}.work"
        work.mkdir()
        destination = self.export_dir / f"{journey_id}.audit.zip"
        partial = self.export_dir / f"{journey_id}.{export_token}.audit.partial"
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "journey": journey,
            "files": {},
        }

        try:
            with zipfile.ZipFile(
                partial, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                def add(path: Path) -> None:
                    manifest["files"][path.name] = {
                        "sha256": _sha256(path),
                        "bytes": path.stat().st_size,
                    }
                    archive.write(path, path.name)
                    path.unlink()

                generated = work / "telemetry.csv"
                self._write_csv_snapshot(telemetry_path, telemetry_size, generated)
                add(generated)
                generated = work / "physics_1khz.csv"
                self._write_csv_snapshot(
                    telemetry_path,
                    telemetry_size,
                    generated,
                    stream="physics_audit_1khz",
                )
                add(generated)
                generated = work / "dashboard_30hz.csv"
                self._write_csv_snapshot(
                    telemetry_path,
                    telemetry_size,
                    generated,
                    stream="dashboard_frame_30hz",
                )
                add(generated)
                generated = work / "constants_1hz.csv"
                self._write_csv_snapshot(
                    telemetry_path,
                    telemetry_size,
                    generated,
                    stream="configuration_snapshot_1hz",
                )
                add(generated)
                generated = work / "events.csv"
                self._write_csv_snapshot(events_path, events_size, generated)
                add(generated)
                generated = work / "telemetry.json"
                self._write_json_array(generated, telemetry_path, telemetry_size)
                add(generated)
                generated = work / "events.json"
                self._write_json_array(generated, events_path, events_size)
                add(generated)

                small_files = {
                    "summary.json": json.dumps(journey["summary"], indent=2),
                    "README.md": (
                        "# AeroPINN journey audit package\n\n"
                        "Persistent simulation telemetry for asynchronous, screen-reader-compatible review.\n"
                        "The manifest records provenance and integrity hashes. CSV files provide flat tables; "
                        "JSON files preserve complete nested telemetry. The physics and dashboard CSV files "
                        "separate native 1 kHz audit samples from complete 30 Hz UI frames; "
                        "constants_1hz.csv records the reproducibility configuration.\n"
                    ),
                }
                fields = self._snapshot_fields(telemetry_path, telemetry_size)
                small_files["data_dictionary.md"] = (
                    "# Telemetry data dictionary\n\n"
                    "All timestamps are ISO 8601 UTC. Dotted names represent nested JSON fields.\n\n"
                    "| Field | Meaning |\n|---|---|\n"
                    + "".join(
                        f"| `{field}` | {_describe_field(field)} |\n"
                        for field in fields
                    )
                )
                for name, content in small_files.items():
                    generated = work / name
                    generated.write_text(content, encoding="utf-8")
                    add(generated)
                archive.writestr(
                    "manifest.json", json.dumps(manifest, indent=2)
                )
            partial.replace(destination)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return destination, "application/zip"

    @staticmethod
    def _iter_ndjson(path: Path, snapshot_bytes: int | None = None):
        if not path.exists():
            return
        boundary = path.stat().st_size if snapshot_bytes is None else snapshot_bytes
        with path.open("rb") as source:
            while source.tell() < boundary:
                line = source.readline()
                if not line or source.tell() > boundary:
                    break
                if line.strip():
                    yield json.loads(line)

    @staticmethod
    def _read_ndjson(path: Path) -> list[dict]:
        return list(JourneyStore._iter_ndjson(path))

    @staticmethod
    def _snapshot_fields(
        path: Path,
        snapshot_bytes: int,
        stream: str | None = None,
    ) -> list[str]:
        fields: set[str] = set()
        for record in JourneyStore._iter_ndjson(path, snapshot_bytes):
            if stream is None or record.get("stream") == stream:
                fields.update(_flatten(record))
        return sorted(fields)

    @staticmethod
    def _write_csv_snapshot(
        source: Path,
        snapshot_bytes: int,
        destination: Path,
        stream: str | None = None,
    ) -> None:
        fields = JourneyStore._snapshot_fields(source, snapshot_bytes, stream)
        with destination.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for record in JourneyStore._iter_ndjson(source, snapshot_bytes):
                if stream is None or record.get("stream") == stream:
                    writer.writerow(_flatten(record))

    @staticmethod
    def _write_json_array(
        destination: Path,
        source: Path,
        snapshot_bytes: int,
    ) -> None:
        with destination.open("w", encoding="utf-8") as output:
            output.write("[\n")
            first = True
            for record in JourneyStore._iter_ndjson(source, snapshot_bytes):
                if not first:
                    output.write(",\n")
                json.dump(record, output, separators=(",", ":"))
                first = False
            output.write("\n]\n")

    @staticmethod
    def _write_json_export(
        destination: Path,
        journey: dict,
        telemetry_path: Path,
        telemetry_size: int,
        events_path: Path,
        events_size: int,
    ) -> None:
        with destination.open("w", encoding="utf-8") as output:
            output.write('{"schema_version":')
            json.dump(SCHEMA_VERSION, output)
            output.write(',"journey":')
            json.dump(journey, output, separators=(",", ":"))
            for name, path, size in (
                ("events", events_path, events_size),
                ("telemetry", telemetry_path, telemetry_size),
            ):
                output.write(f',"{name}":[')
                first = True
                for record in JourneyStore._iter_ndjson(path, size):
                    if not first:
                        output.write(",")
                    json.dump(record, output, separators=(",", ":"))
                    first = False
                output.write("]")
            output.write("}\n")

    def _row(self, journey_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM journeys WHERE id=?", (journey_id,)
        ).fetchone()
        if row is None:
            raise KeyError(journey_id)
        return row

    @staticmethod
    def _serialize(row: sqlite3.Row, include_paths: bool) -> dict:
        telemetry_path = Path(row["telemetry_file"])
        events_path = Path(row["events_file"])
        telemetry_bytes = telemetry_path.stat().st_size if telemetry_path.exists() else 0
        events_bytes = events_path.stat().st_size if events_path.exists() else 0
        output = {
            "id": row["id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "status": row["status"],
            "archived": bool(row["archived"]),
            "metadata": json.loads(row["metadata_json"]),
            "summary": json.loads(row["summary_json"]),
            "sample_count": row["sample_count"],
            "event_count": row["event_count"],
            "storage": {
                "telemetry_bytes": telemetry_bytes,
                "events_bytes": events_bytes,
                "total_bytes": telemetry_bytes + events_bytes,
            },
            "schema_version": row["schema_version"],
        }
        if include_paths:
            output["telemetry_file"] = row["telemetry_file"]
            output["events_file"] = row["events_file"]
        return output


class JourneySession:
    def __init__(self, store: JourneyStore, journey_id: str, started_at: str, metadata: dict):
        self.store = store
        self.id = journey_id
        self.started_at = started_at
        self.metadata = metadata
        self.telemetry_path = store.telemetry_dir / f"{journey_id}.ndjson"
        self.events_path = store.events_dir / f"{journey_id}.ndjson"
        self._telemetry = self.telemetry_path.open("a", encoding="utf-8", buffering=1)
        self._events = self.events_path.open("a", encoding="utf-8", buffering=1)
        self.sample_count = 0
        self.frame_count = 0
        self.physics_count = 0
        self.constants_count = 0
        self._stats_count = 0
        self.event_count = 0
        self.distance_m = 0.0
        self._last_t: float | None = None
        self._last_constants_t: float | None = None
        self._force_stats = {
            "passive": {"mean": 0.0, "m2": 0.0, "loss": 0, "min": None, "max": None},
            "aeropinn": {"mean": 0.0, "m2": 0.0, "loss": 0, "min": None, "max": None},
        }
        self._previous_flags: dict[str, bool] = {}
        self._saturation_candidate: bool | None = None
        self._saturation_candidate_since: float | None = None
        self._control_samples = 0
        self._saturated_samples = 0
        self._closed = False

    def record(self, frame: dict) -> dict:
        if self._closed:
            raise RuntimeError("journey is closed")
        simulation_t = float(frame["t"])
        location = self._location(simulation_t, float(frame["speed_kmh"]))
        record = {
            "schema_version": SCHEMA_VERSION,
            "stream": "dashboard_frame_30hz",
            "session_id": self.id,
            "recorded_at": _utc_now(),
            "location": location,
            "telemetry": frame,
        }
        self._write_record(record)
        self.frame_count += 1
        if self.physics_count == 0:
            self._update_force_stats(
                float(frame["passive"]["contact_force"]),
                float(frame["aeropinn"]["contact_force"]),
                bool(frame["passive"]["contact_lost"]),
                bool(frame["aeropinn"]["contact_lost"]),
            )
        self._detect_events({
            "t": frame["t"],
            "passive_lost": frame["passive"]["contact_lost"],
            "aeropinn_lost": frame["aeropinn"]["contact_lost"],
            "gust_active": frame["gust_active"],
            "fallback": frame["state_estimation"]["fallback_active"],
            "command_N": frame["aeropinn"]["f_command"],
            "authority_N": frame["catenary_dynamics"]["control_authority_N"],
        }, location)
        if self.physics_count == 0 and self.frame_count % 30 == 0:
            self._checkpoint()
        return record

    def record_physics(self, sample: dict) -> dict:
        """Append one native 1 ms plant/controller sample."""
        if self._closed:
            raise RuntimeError("journey is closed")
        if self.physics_count == 0 and self.frame_count:
            # Native-rate evidence supersedes any provisional dashboard statistics.
            self._reset_force_stats()
        simulation_t = float(sample["t_s"])
        location = self._location(simulation_t, float(sample["speed_kmh"]))
        record = {
            "schema_version": SCHEMA_VERSION,
            "stream": "physics_audit_1khz",
            "session_id": self.id,
            "recorded_at": _utc_now(),
            "location": location,
            "physics": sample,
        }
        self._write_record(record)
        self.physics_count += 1
        self._control_samples += 1
        self._saturated_samples += int(
            abs(float(sample["aeropinn"]["command_force_N"]))
            >= float(sample["timing"]["control_authority_N"])
        )
        self._update_force_stats(
            float(sample["passive"]["contact_force_N"]),
            float(sample["aeropinn"]["contact_force_N"]),
            bool(sample["passive"]["contact_lost"]),
            bool(sample["aeropinn"]["contact_lost"]),
        )
        self._detect_events({
            "t": sample["t_s"],
            "passive_lost": sample["passive"]["contact_lost"],
            "aeropinn_lost": sample["aeropinn"]["contact_lost"],
            "gust_active": abs(float(sample["gust_force_N"])) >= 0.5,
            "fallback": sample["estimator"]["fallback_active"],
            "command_N": sample["aeropinn"]["command_force_N"],
            "authority_N": sample["timing"]["control_authority_N"],
        }, location)
        if self.physics_count % 1000 == 0:
            self._checkpoint()
        return record

    def record_constants(self, snapshot: dict, period_s: float = 1.0) -> dict | None:
        """Persist configuration at a bounded cadence for later reproducibility."""
        if self._closed:
            raise RuntimeError("journey is closed")
        simulation_t = float(snapshot["t_s"])
        if (
            self._last_constants_t is not None
            and simulation_t - self._last_constants_t < period_s
        ):
            return None
        operating = snapshot["operating_configuration"]
        record = {
            "schema_version": SCHEMA_VERSION,
            "stream": "configuration_snapshot_1hz",
            "session_id": self.id,
            "recorded_at": _utc_now(),
            "sampling_period_s": period_s,
            "location": self._location(simulation_t, float(operating["speed_kmh"])),
            "constants": snapshot,
        }
        self._write_record(record)
        self.constants_count += 1
        self._last_constants_t = simulation_t
        return record

    def _location(self, simulation_t: float, speed_kmh: float) -> dict:
        if self._last_t is not None:
            self.distance_m += max(simulation_t - self._last_t, 0.0) * speed_kmh / 3.6
        self._last_t = max(simulation_t, self._last_t or simulation_t)
        start = float(self.metadata.get("start_chainage_km", 0.0))
        end = float(self.metadata.get("end_chainage_km", start))
        route_length = max(abs(end - start) * 1000.0, 1.0)
        fraction = min(max(self.distance_m / route_length, 0.0), 1.0)
        chainage = start + fraction * (end - start)
        latitude = self._interpolate("start_latitude", "end_latitude", fraction)
        longitude = self._interpolate("start_longitude", "end_longitude", fraction)
        return {
            "route_chainage_km": round(chainage, 6),
            "latitude": round(latitude, 7),
            "longitude": round(longitude, 7),
        }

    def _write_record(self, record: dict) -> None:
        self._telemetry.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.sample_count += 1

    def _reset_force_stats(self) -> None:
        self._stats_count = 0
        for stats in self._force_stats.values():
            stats.update({"mean": 0.0, "m2": 0.0, "loss": 0, "min": None, "max": None})

    def _update_force_stats(
        self, passive_force: float, active_force: float, passive_lost: bool, active_lost: bool
    ) -> None:
        self._stats_count += 1
        for lane, force, lost in (
            ("passive", passive_force, passive_lost),
            ("aeropinn", active_force, active_lost),
        ):
            stats = self._force_stats[lane]
            delta = force - stats["mean"]
            stats["mean"] += delta / self._stats_count
            stats["m2"] += delta * (force - stats["mean"])
            stats["loss"] += int(lost)
            stats["min"] = force if stats["min"] is None else min(stats["min"], force)
            stats["max"] = force if stats["max"] is None else max(stats["max"], force)

    def _interpolate(self, start_key: str, end_key: str, fraction: float) -> float:
        start = float(self.metadata.get(start_key, 0.0))
        end = float(self.metadata.get(end_key, start))
        return start + fraction * (end - start)

    def _detect_events(self, sample: dict, location: dict) -> None:
        flags = {
            "PASSIVE_CONTACT_LOSS": bool(sample["passive_lost"]),
            "AEROPINN_CONTACT_LOSS": bool(sample["aeropinn_lost"]),
            "GUST": bool(sample["gust_active"]),
            "ESTIMATOR_FALLBACK": bool(sample["fallback"]),
        }
        for name, active in flags.items():
            previous = self._previous_flags.get(name, False)
            if active != previous:
                self.event(f"{name}_{'START' if active else 'END'}", {
                    "simulation_t_s": sample["t"], "location": location
                })
            self._previous_flags[name] = active
        self._detect_saturation(sample, location)

    def _detect_saturation(self, sample: dict, location: dict) -> None:
        """Debounce actuator-limit events while retaining raw duty-cycle evidence."""
        name = "ACTUATOR_SATURATION"
        active = self._previous_flags.get(name, False)
        command = abs(float(sample["command_N"]))
        authority = max(float(sample["authority_N"]), 1.0e-9)
        threshold_crossed = (
            command <= 0.90 * authority if active else command >= 0.98 * authority
        )
        desired = not active
        simulation_t = float(sample["t"])

        if not threshold_crossed:
            self._saturation_candidate = None
            self._saturation_candidate_since = None
            return
        if self._saturation_candidate != desired:
            self._saturation_candidate = desired
            self._saturation_candidate_since = simulation_t
            return
        if (
            self._saturation_candidate_since is None
            or simulation_t - self._saturation_candidate_since < 0.10
        ):
            return

        self.event(f"{name}_{'START' if desired else 'END'}", {
            "simulation_t_s": sample["t"],
            "location": location,
            "dwell_s": round(simulation_t - self._saturation_candidate_since, 3),
            "enter_threshold_pct": 98.0,
            "exit_threshold_pct": 90.0,
        })
        self._previous_flags[name] = desired
        self._saturation_candidate = None
        self._saturation_candidate_since = None

    def event(self, event_type: str, details: dict | None = None) -> None:
        if self._closed:
            return
        event = {
            "session_id": self.id,
            "recorded_at": _utc_now(),
            "event_type": event_type,
            "details": details or {},
        }
        self._events.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.event_count += 1

    def summary(self) -> dict:
        lanes = {}
        for lane, stats in self._force_stats.items():
            variance = stats["m2"] / self._stats_count if self._stats_count else 0.0
            lanes[lane] = {
                "mean_contact_force_N": round(stats["mean"], 3),
                "std_contact_force_N": round(variance ** 0.5, 3),
                "min_contact_force_N": stats["min"],
                "max_contact_force_N": stats["max"],
                "contact_loss_samples": stats["loss"],
                "contact_loss_pct": round(100.0 * stats["loss"] / max(self._stats_count, 1), 3),
            }
        return {
            "sample_count": self.sample_count,
            "dashboard_frame_count": self.frame_count,
            "physics_sample_count": self.physics_count,
            "event_count": self.event_count,
            "distance_km": round(self.distance_m / 1000.0, 6),
            "simulation_duration_s": self._last_t or 0.0,
            "sample_streams": {
                "physics_audit_1khz": self.physics_count,
                "dashboard_frame_30hz": self.frame_count,
                "configuration_snapshot_1hz": self.constants_count,
            },
            "controller": {
                "command_limit_samples": self._saturated_samples,
                "command_limit_duty_pct": round(
                    100.0 * self._saturated_samples / max(self._control_samples, 1),
                    3,
                ),
            },
            "lanes": lanes,
        }

    def _checkpoint(self) -> None:
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                """UPDATE journeys SET summary_json=?, sample_count=?, event_count=?
                   WHERE id=?""",
                (json.dumps(self.summary()), self.sample_count, self.event_count, self.id),
            )

    def finalize(self, status: str = "COMPLETED") -> None:
        if self._closed:
            return
        self.event("JOURNEY_ENDED", {"status": status})
        summary = self.summary()
        self._telemetry.close()
        self._events.close()
        self._closed = True
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                """UPDATE journeys SET ended_at=?, status=?, summary_json=?,
                   sample_count=?, event_count=? WHERE id=?""",
                (_utc_now(), status, json.dumps(summary), self.sample_count, self.event_count, self.id),
            )
            self.store._audit("FINALIZED", self.id, {"status": status})
            self.store._active.pop(self.id, None)


def ensure_sample_journey(store: JourneyStore, predictor) -> str | None:
    """Create one reproducible stress-test journey through the production engine."""
    if store.has_sample():
        return None
    from backend.server.engine import Engine

    journey = store.create({
        "scenario_name": "High-wind contact stress test",
        "weather": "crosswind gusts",
        "ambient_temperature_C": 35.0,
        "wire_temperature_C": 44.0,
        "wind_speed_m_s": 18.0,
        "is_sample": True,
    })
    engine = Engine(seed=999, predictor=predictor)

    def capture(frames: int) -> None:
        for _ in range(frames):
            engine.step(33, audit_callback=journey.record_physics)
            frame = engine.frame()
            frame["journey"] = {
                "id": journey.id,
                "status": "RUNNING",
                "started_at": journey.started_at,
                "schema_version": SCHEMA_VERSION,
            }
            journey.record(frame)
            journey.record_constants(engine.constants_snapshot())

    try:
        journey.event("SCENARIO_PHASE", {"name": "nominal baseline"})
        capture(30)
        journey.event("SCENARIO_PHASE", {"name": "high-wind section"})
        engine.set_speed(350.0)
        engine.set_tension(0.5)
        engine.set_turbulence(3.5)
        for kind, value in (("speed", 350.0), ("tension", 0.5), ("turbulence", 3.5)):
            journey.event("AUTOMATIC_SCENARIO_INPUT", {"type": kind, "value": value})
        capture(45)
        journey.event("SCENARIO_PHASE", {"name": "extreme gust"})
        engine.trigger_gust(70.0)
        journey.event("AUTOMATIC_SCENARIO_INPUT", {"type": "gust", "value": 70.0})
        capture(90)
        journey.finalize("COMPLETED")
    except Exception:
        journey.finalize("INTERRUPTED")
        raise
    return journey.id
