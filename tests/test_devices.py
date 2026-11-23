import pytest

from fitlog_store import create_user
from fitcircle import compare_progress, respond_request, send_request, update_privacy
from fitlog_devices import import_daily_steps, list_daily_steps


@pytest.fixture
def device_db(tmp_path):
    return tmp_path / "device_test.sqlite"


def make_user(db, name):
    return create_user(name, "secure-pass-123", db, db.parent / "missing.csv")


def test_device_steps_import_is_validated_and_idempotent(device_db):
    owner = make_user(device_db, "device_owner")
    first = import_daily_steps(owner["id"], "fitbit", [
        {"date": "2026-11-14", "steps": 8032},
        {"date": "bad-date", "steps": 100},
        {"date": "2026-11-13", "steps": -10},
    ], device_db)
    assert first == {"added": 1, "updated": 0, "total": 1}
    second = import_daily_steps(owner["id"], "fitbit", [
        {"date": "2026-11-14", "steps": 9100},
    ], device_db)
    assert second == {"added": 0, "updated": 1, "total": 1}
    rows = list_daily_steps(owner["id"], db_file=device_db)
    assert len(rows) == 1 and rows[0]["steps"] == 9100
    with pytest.raises(ValueError, match="supported device"):
        import_daily_steps(owner["id"], "unknown", [{"date": "2026-11-14", "steps": 5}], device_db)


def test_steps_are_hidden_from_friends_until_explicit_consent(device_db):
    owner, friend = make_user(device_db, "device_alice"), make_user(device_db, "device_bob")
    send_request(owner["id"], friend["id"], device_db)
    from fitcircle import requests
    incoming = next(row for row in requests(friend["id"], device_db) if row["direction"] == "incoming")
    respond_request(friend["id"], incoming["id"], "accepted", device_db)
    import_daily_steps(friend["id"], "apple_health", [{"date": "2026-11-14", "steps": 7000}], device_db)
    assert compare_progress(owner["id"], friend["id"], device_db)["steps"] is None
    update_privacy(friend["id"], {"share_steps": True}, device_db)
    assert compare_progress(owner["id"], friend["id"], device_db)["steps"] == 7000
