import pytest

from fitlog_store import authenticate_user, create_user, save_workout
from fitcircle import (
    challenges, compare_progress, create_challenge, friends, get_privacy,
    init_fitcircle, invite_code, join_challenge, leaderboard, remove_friend, respond_request,
    search_users, send_request, update_discovery_settings, update_privacy, valid_invite,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "social.sqlite"
    return path


def user(db, name):
    account = create_user(name, "secure-pass-123", db, db.parent / "missing.csv")
    init_fitcircle(db)
    return account


def connect(a, b, db):
    send_request(a["id"], b["id"], db)
    req = next(r for r in __import__("fitcircle").requests(b["id"], db) if r["direction"] == "incoming")
    respond_request(b["id"], req["id"], "accepted", db)


def test_registration_login_search_and_ids(db):
    a = user(db, "alice_fit")
    user(db, "bob_fit")
    assert authenticate_user("alice_fit", "secure-pass-123", db) == a
    assert search_users(a["id"], "bob_fit", db)[0]["fitlog_id"] == "FL000002"
    assert search_users(a["id"], "FL000002", db)
    code = invite_code(a["id"], db)
    assert valid_invite(code, db)
    assert not valid_invite("made-up-code", db)


def test_friend_requests_duplicate_accept_and_remove(db):
    a, b = user(db, "alice_one"), user(db, "bob_two")
    with pytest.raises(ValueError, match="yourself"): send_request(a["id"], a["id"], db)
    send_request(a["id"], b["id"], db)
    with pytest.raises(ValueError, match="already pending"): send_request(a["id"], b["id"], db)
    req = next(r for r in __import__("fitcircle").requests(b["id"], db) if r["direction"] == "incoming")
    respond_request(b["id"], req["id"], "accepted", db)
    assert len(friends(a["id"], db)) == 1
    remove_friend(a["id"], b["id"], db)
    assert friends(a["id"], db) == []


def test_reject_and_cancel_requests(db):
    a, b, c = user(db, "alice_two"), user(db, "bob_three"), user(db, "cara_four")
    send_request(a["id"], b["id"], db)
    req = next(r for r in __import__("fitcircle").requests(b["id"], db) if r["direction"] == "incoming")
    respond_request(b["id"], req["id"], "rejected", db)
    send_request(a["id"], c["id"], db)
    req = next(r for r in __import__("fitcircle").requests(a["id"], db) if r["direction"] == "outgoing")
    respond_request(a["id"], req["id"], "cancelled", db)
    assert not __import__("fitcircle").requests(a["id"], db)


def test_progress_privacy_and_friend_gate(db):
    a, b, c = user(db, "alice_three"), user(db, "bob_four"), user(db, "cara_five")
    connect(a, b, db)
    update_privacy(b["id"], {"share_workouts": True, "share_duration": True}, db)
    save_workout(b["id"], {"date": "2026-11-14", "workout": "Walk", "duration": 35, "calories": 120}, db)
    result = compare_progress(a["id"], b["id"], db)
    assert result["workouts"] == 1 and result["duration"] == 35 and result["calories"] is None
    with pytest.raises(PermissionError): compare_progress(a["id"], c["id"], db)
    update_privacy(b["id"], {"share_workouts": False}, db)
    assert compare_progress(a["id"], b["id"], db)["workouts"] is None


def test_leaderboard_and_challenge_use_recorded_workouts(db):
    a, b = user(db, "alice_four"), user(db, "bob_five")
    connect(a, b, db)
    update_discovery_settings(a["id"], True, True, db)
    update_discovery_settings(b["id"], True, True, db)
    update_privacy(a["id"], {"leaderboard_visibility": True}, db)
    update_privacy(b["id"], {"leaderboard_visibility": True}, db)
    save_workout(a["id"], {"date": "2026-11-14", "workout": "Run", "duration": 30, "calories": 100}, db)
    assert leaderboard(a["id"], db)[0]["workouts"] == 1
    cid = create_challenge(a["id"], "Weekly movement", "Recorded workouts", "workouts", 1, "2026-11-10", "2026-11-20", db, invite_ids=[b["id"]])
    join_challenge(b["id"], cid, db)
    entries = challenges(a["id"], db)
    assert entries[0]["progress"] == 1 and entries[0]["completion_status"] == "complete"
    assert get_privacy(b["id"], db)["share_workouts"] == 0
    from fitcircle import user_achievements
    assert user_achievements(a["id"], db)[0]["badge_name"] == "Challenge: Weekly movement"
    other = user(db, "cody_six")
    with pytest.raises(PermissionError): join_challenge(other["id"], cid, db)
