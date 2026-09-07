import pytest
from fastapi.testclient import TestClient
from app import app, Base, engine, SessionLocal, User, Rating

client = TestClient(app)

def test_01_admin_login():
    res = client.post("/api/login", json={"username": "Admin", "password": "Admin@123"})
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "admin"
    assert "cric_token" in res.cookies

def test_02_member_login_and_rate_peer():
    # Login as raghavendra
    login_res = client.post("/api/login", json={"username": "raghavendra", "password": "cricket123"})
    assert login_res.status_code == 200

    # Look up Manoj's id
    db = SessionLocal()
    manoj = db.query(User).filter(User.username == "manoj").first()
    manoj_id = manoj.id
    db.close()

    # Rate Manoj
    rate_res = client.post("/api/rate", json={
        "rated_player_id": manoj_id,
        "batting": 9.5,
        "bowling": 5.0,
        "fielding": 8.5
    })
    assert rate_res.status_code == 200
    assert "Rating saved" in rate_res.json()["message"]

def test_03_shuffler_diff_less_than_or_equal_0_1():
    res = client.post("/api/shuffle", json={})
    assert res.status_code == 200
    data = res.json()
    assert len(data["team_a"]) == 6
    assert len(data["team_b"]) == 6
    diff = data["diff"]
    print(f"\n[E2E Balance Check] Team A Avg: {data['team_a_avg']} | Team B Avg: {data['team_b_avg']} | Diff: {diff}")
    assert diff <= 0.1, f"Team rating difference {diff} exceeds 0.1!"

def test_04_captain_nomination_and_toss():
    shuffle_res = client.post("/api/shuffle", json={})
    match_id = shuffle_res.json()["match_id"]
    cap_a = shuffle_res.json()["team_a"][0]["id"]
    cap_b = shuffle_res.json()["team_b"][0]["id"]

    # Confirm captains
    cap_res = client.post(f"/api/match/{match_id}/captains", json={
        "team_a_captain_id": cap_a,
        "team_b_captain_id": cap_b
    })
    assert cap_res.status_code == 200

    # Execute toss
    toss_res = client.post(f"/api/match/{match_id}/toss", json={
        "calling_captain_id": cap_a,
        "call": "HEADS",
        "decision": "BAT"
    })
    assert toss_res.status_code == 200
    toss_data = toss_res.json()
    assert toss_data["coin"] in ["HEADS", "TAILS"]
    assert "won the toss and elected to BAT first" in toss_data["statement"]

def test_05_admin_delete_member():
    # Login as Admin
    client.post("/api/login", json={"username": "Admin", "password": "Admin@123"})
    db = SessionLocal()
    pavan = db.query(User).filter(User.username == "pavan").first()
    target_id = pavan.id
    db.close()

    del_res = client.delete(f"/api/admin/member/{target_id}")
    assert del_res.status_code == 200
    assert "deleted successfully" in del_res.json()["message"]
