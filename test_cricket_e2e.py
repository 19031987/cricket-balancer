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

def test_04_captain_nomination_toss_and_post_toss_decision():
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

    # Execute toss - verify decision is NOT preselected
    toss_res = client.post(f"/api/match/{match_id}/toss", json={
        "calling_captain_id": cap_a,
        "call": "HEADS"
    })
    assert toss_res.status_code == 200
    toss_data = toss_res.json()
    assert toss_data["coin"] in ["HEADS", "TAILS"]
    assert toss_data["decision"] is None
    assert "won the toss!" in toss_data["statement"]

    # Winning captain chooses to BAT or BOWL
    dec_res = client.post(f"/api/match/{match_id}/decision", json={"decision": "BAT"})
    assert dec_res.status_code == 200
    dec_data = dec_res.json()
    assert dec_data["decision"] == "BAT"
    assert "elected to BAT first!" in dec_data["message"]

def test_05_player_availability_toggle():
    db = SessionLocal()
    player = db.query(User).filter(User.role == "player").first()
    player_id = player.id
    db.close()

    # Toggle player unavailable
    res_off = client.post(f"/api/member/{player_id}/availability", json={"is_available": False})
    assert res_off.status_code == 200
    assert res_off.json()["is_available"] is False

    # Check state reflects availability
    state_res = client.get("/api/state")
    p_state = next(p for p in state_res.json()["players"] if p["id"] == player_id)
    assert p_state["is_available"] is False

    # Restore availability
    res_on = client.post(f"/api/member/{player_id}/availability", json={"is_available": True})
    assert res_on.status_code == 200
    assert res_on.json()["is_available"] is True

def test_06_admin_add_user_and_change_member_password():
    # Login as Admin
    client.post("/api/login", json={"username": "Admin", "password": "Admin@123"})
    
    # Clean up test user if exists from prior run
    db = SessionLocal()
    existing = db.query(User).filter(User.username == "karthik").first()
    if existing:
        db.delete(existing)
        db.commit()
    db.close()

    # 1. Admin adds new member
    add_res = client.post("/api/admin/member", json={
        "username": "karthik",
        "full_name": "Karthik",
        "password": "initial_password_123"
    })
    assert add_res.status_code == 200
    assert "added successfully" in add_res.json()["message"]

    # Verify new user can login
    new_login = client.post("/api/login", json={"username": "karthik", "password": "initial_password_123"})
    assert new_login.status_code == 200

    # 2. Member changes own password
    chg_res = client.post("/api/change-password", json={"new_password": "member_new_pass_456"})
    assert chg_res.status_code == 200

    # 3. Admin resets member password
    client.post("/api/login", json={"username": "Admin", "password": "Admin@123"})
    db = SessionLocal()
    karthik = db.query(User).filter(User.username == "karthik").first()
    karthik_id = karthik.id
    db.close()

    admin_chg = client.post("/api/admin/member/change-password", json={
        "user_id": karthik_id,
        "new_password": "admin_set_pass_789"
    })
    assert admin_chg.status_code == 200
    assert "updated successfully" in admin_chg.json()["message"]

    # Verify login with the admin-set password
    verify_login = client.post("/api/login", json={"username": "karthik", "password": "admin_set_pass_789"})
    assert verify_login.status_code == 200

def test_07_admin_change_own_password():
    # Login as Admin
    login_res = client.post("/api/login", json={"username": "Admin", "password": "Admin@123"})
    assert login_res.status_code == 200

    # Admin changes own password
    chg_res = client.post("/api/change-password", json={"new_password": "NewAdminPassword@2026"})
    assert chg_res.status_code == 200
    assert "updated successfully" in chg_res.json()["message"]

    # Verify login with new password
    new_login = client.post("/api/login", json={"username": "Admin", "password": "NewAdminPassword@2026"})
    assert new_login.status_code == 200

    # Restore default Admin password
    restore_res = client.post("/api/change-password", json={"new_password": "Admin@123"})
    assert restore_res.status_code == 200

def test_08_admin_delete_member():
    # Login as Admin
    client.post("/api/login", json={"username": "Admin", "password": "Admin@123"})
    db = SessionLocal()
    karthik = db.query(User).filter(User.username == "karthik").first()
    target_id = karthik.id if karthik else None
    db.close()

    if target_id:
        del_res = client.delete(f"/api/admin/member/{target_id}")
        assert del_res.status_code == 200
        assert "deleted successfully" in del_res.json()["message"]
