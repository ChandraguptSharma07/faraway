import csv
import json
import zipfile

import pytest

from backend.server.journeys import JourneyStore


def frame(t=0.0, passive_force=110.0, active_force=115.0, gust=False):
    return {
        "t": t,
        "speed_kmh": 250.0,
        "gust_active": gust,
        "passive": {
            "contact_force": passive_force,
            "contact_lost": passive_force <= 0.0,
        },
        "aeropinn": {
            "contact_force": active_force,
            "contact_lost": active_force <= 0.0,
            "f_command": 5.0,
        },
        "state_estimation": {"fallback_active": False},
        "catenary_dynamics": {"control_authority_N": 25.0},
    }


def test_journey_persists_metadata_telemetry_events_and_summary(tmp_path):
    store = JourneyStore(tmp_path)
    journey = store.create({"route_name": "Accessible Test Route"})
    store.update_metadata(journey.id, {
        "track": "2",
        "start_chainage_km": 10.0,
        "end_chainage_km": 11.0,
    })
    journey.record(frame(0.0))
    journey.record(frame(0.1, passive_force=0.0, gust=True))
    journey.finalize()

    saved = store.get(journey.id)
    assert saved["status"] == "COMPLETED"
    assert saved["metadata"]["route_name"] == "Accessible Test Route"
    assert saved["metadata"]["track"] == "2"
    assert saved["sample_count"] == 2
    assert saved["event_count"] >= 3
    assert saved["storage"]["total_bytes"] > 0
    assert saved["summary"]["lanes"]["passive"]["contact_loss_pct"] == 50.0

    path, media_type = store.export(journey.id, "json")
    payload = json.loads(path.read_text())
    assert media_type == "application/json"
    assert payload["telemetry"][1]["location"]["route_chainage_km"] > 10.0
    assert payload["events"]


def test_csv_and_audit_package_are_accessible_and_self_documenting(tmp_path):
    store = JourneyStore(tmp_path)
    journey = store.create()
    journey.record(frame())
    journey.finalize()

    csv_path, _ = store.export(journey.id, "csv")
    with csv_path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows[0]["telemetry.passive.contact_force"] == "110.0"
    assert rows[0]["location.route_chainage_km"] == "120.0"

    package, media_type = store.export(journey.id, "audit")
    assert media_type == "application/zip"
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert {
            "manifest.json",
            "summary.json",
            "telemetry.csv",
            "physics_1khz.csv",
            "dashboard_30hz.csv",
            "constants_1hz.csv",
            "telemetry.json",
            "events.csv",
            "events.json",
            "data_dictionary.md",
            "README.md",
        } <= names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["journey"]["metadata"]["data_source"] == "SIMULATION"
        assert manifest["files"]["telemetry.csv"]["sha256"]


def test_archive_and_confirmed_delete_preserve_catalog_safety(tmp_path):
    store = JourneyStore(tmp_path)
    journey = store.create()
    journey.finalize()
    store.archive(journey.id)
    assert store.list() == []
    assert store.list(include_archived=True)[0]["archived"] is True
    with pytest.raises(ValueError, match="confirmation"):
        store.delete(journey.id, "wrong")
    store.delete(journey.id, journey.id)
    with pytest.raises(KeyError):
        store.get(journey.id)
    audit = store._connection.execute(
        "SELECT action FROM audit_log WHERE journey_id=?", (journey.id,)
    ).fetchall()
    assert "PERMANENTLY_DELETED" in {row[0] for row in audit}


def test_running_journey_cannot_be_deleted(tmp_path):
    store = JourneyStore(tmp_path)
    journey = store.create()
    with pytest.raises(ValueError, match="running"):
        store.archive(journey.id)
    with pytest.raises(ValueError, match="running"):
        store.delete(journey.id, journey.id)
    journey.finalize()


def test_metadata_rejects_invalid_location_and_unknown_fields(tmp_path):
    store = JourneyStore(tmp_path)
    journey = store.create()
    with pytest.raises(ValueError, match="between -90 and 90"):
        store.update_metadata(journey.id, {"start_latitude": 100.0})
    with pytest.raises(ValueError, match="unsupported"):
        store.update_metadata(journey.id, {"secret_field": "value"})
    journey.finalize()


def test_actuator_saturation_events_require_dwell_and_hysteresis(tmp_path):
    store = JourneyStore(tmp_path)
    journey = store.create()

    # Boundary chatter is preserved in telemetry and duty statistics, but does not
    # create a misleading series of start/end incidents.
    for index in range(20):
        sample = frame(index * 0.01)
        sample["aeropinn"]["f_command"] = 25.0 if index % 2 else 24.0
        journey.record(sample)
    assert journey.event_count == 0

    for index in range(20, 32):
        sample = frame(index * 0.01)
        sample["aeropinn"]["f_command"] = 25.0
        journey.record(sample)
    for index in range(32, 44):
        sample = frame(index * 0.01)
        sample["aeropinn"]["f_command"] = 20.0
        journey.record(sample)
    journey.finalize()

    events = JourneyStore._read_ndjson(journey.events_path)
    event_types = [event["event_type"] for event in events]
    assert event_types.count("ACTUATOR_SATURATION_START") == 1
    assert event_types.count("ACTUATOR_SATURATION_END") == 1


def test_record_pages_use_bounded_byte_cursors(tmp_path):
    store = JourneyStore(tmp_path)
    journey = store.create()
    journey.record(frame(0.0))
    journey.record(frame(0.1, gust=True))
    journey.event("OPERATOR_NOTE", {"text": "inspect this point"})

    first = store.page(
        journey.id,
        "telemetry",
        limit=1,
        stream="dashboard_frame_30hz",
    )
    assert len(first["records"]) == 1
    assert first["next_cursor"] is not None
    second = store.page(
        journey.id,
        "telemetry",
        cursor=first["next_cursor"],
        limit=1,
        stream="dashboard_frame_30hz",
    )
    assert second["records"][0]["telemetry"]["t"] == 0.1
    assert second["next_cursor"] is None

    events = store.page(journey.id, "events", limit=10)
    assert events["records"][-1]["event_type"] == "OPERATOR_NOTE"
    journey.finalize()


def test_exports_stream_without_materializing_full_ndjson(tmp_path, monkeypatch):
    store = JourneyStore(tmp_path)
    journey = store.create()
    journey.record(frame())
    journey.finalize()

    monkeypatch.setattr(
        JourneyStore,
        "_read_ndjson",
        staticmethod(lambda _path: (_ for _ in ()).throw(AssertionError("full read"))),
    )
    csv_path, _ = store.export(journey.id, "csv")
    json_path, _ = store.export(journey.id, "json")
    package, _ = store.export(journey.id, "audit")
    assert csv_path.stat().st_size > 0
    assert json.loads(json_path.read_text())["telemetry"]
    assert zipfile.is_zipfile(package)


def test_configuration_constants_are_recorded_once_per_second(tmp_path):
    store = JourneyStore(tmp_path)
    journey = store.create()

    def snapshot(t, tension=20_000.0):
        return {
            "t_s": t,
            "controller": {"setpoint_N": 115.0},
            "distributed_catenary": {"contact_tension": tension},
            "solver": {"integration_step_s": 0.001},
            "actuator": {"response_time": 0.04},
            "operating_configuration": {"speed_kmh": 250.0},
        }

    assert journey.record_constants(snapshot(0.0)) is not None
    assert journey.record_constants(snapshot(0.5)) is None
    assert journey.record_constants(snapshot(1.0, tension=18_000.0)) is not None
    journey.finalize()

    saved = store.get(journey.id)
    assert saved["summary"]["sample_streams"]["configuration_snapshot_1hz"] == 2
    page = store.page(
        journey.id,
        "telemetry",
        stream="configuration_snapshot_1hz",
    )
    assert [
        row["constants"]["distributed_catenary"]["contact_tension"]
        for row in page["records"]
    ] == [20_000.0, 18_000.0]
