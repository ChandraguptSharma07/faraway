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
