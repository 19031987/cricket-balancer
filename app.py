import os
import json
import random
import hashlib
import secrets
import itertools
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from jose import jwt, JWTError

DATABASE_FILE = "cricket.db"
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"
SECRET_KEY = "super-cricket-balanced-jwt-secret-key"
ALGORITHM = "HS256"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="player")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ratings_received = relationship("Rating", foreign_keys="Rating.rated_player_id", cascade="all, delete-orphan")
    ratings_given = relationship("Rating", foreign_keys="Rating.rater_id", cascade="all, delete-orphan")

class Rating(Base):
    __tablename__ = "ratings"
    id = Column(Integer, primary_key=True, index=True)
    rater_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rated_player_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    batting = Column(Float, nullable=False)
    bowling = Column(Float, nullable=False)
    fielding = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    team_a_players = Column(String, nullable=False)
    team_b_players = Column(String, nullable=False)
    team_a_avg = Column(Float, nullable=False)
    team_b_avg = Column(Float, nullable=False)
    avg_diff = Column(Float, nullable=False)
    team_a_captain_id = Column(Integer, nullable=True)
    team_b_captain_id = Column(Integer, nullable=True)
    toss_winner_id = Column(Integer, nullable=True)
    toss_decision = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + pw).encode('utf-8')).hexdigest()
    return f"{salt}:{h}"

def verify_pw(plain: str, hashed: str) -> bool:
    try:
        salt, h = hashed.split(":")
        check = hashlib.sha256((salt + plain).encode('utf-8')).hexdigest()
        return secrets.compare_digest(check, h)
    except Exception:
        return False

def create_token(username: str) -> str:
    exp = datetime.utcnow() + timedelta(days=7)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(request: Request, db: Session):
    token = request.cookies.get("cric_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            return None
        return db.query(User).filter(User.username == username, User.is_active == True).first()
    except JWTError:
        return None

def get_player_stats(user: User, db: Session):
    ratings = db.query(Rating).filter(Rating.rated_player_id == user.id).all()
    if not ratings:
        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "batting_avg": 6.0,
            "bowling_avg": 6.0,
            "fielding_avg": 6.0,
            "overall_rating": 6.0,
            "rating_count": 0
        }
    bat = sum(r.batting for r in ratings) / len(ratings)
    bowl = sum(r.bowling for r in ratings) / len(ratings)
    fld = sum(r.fielding for r in ratings) / len(ratings)
    overall = round((bat + bowl + fld) / 3.0, 2)
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "batting_avg": round(bat, 2),
        "bowling_avg": round(bowl, 2),
        "fielding_avg": round(fld, 2),
        "overall_rating": overall,
        "rating_count": len(ratings)
    }

def balance_12_players(players: List[dict], target_diff: float = 0.10):
    if len(players) != 12:
        raise ValueError(f"Exactly 12 players required to balance teams. Given: {len(players)}")

    indices = list(range(12))
    valid_splits = []
    best_split = None
    min_diff = float("inf")

    for a_indices in itertools.combinations(indices, 6):
        if 0 not in a_indices:
            continue
        b_indices = [i for i in indices if i not in a_indices]

        team_a = [players[i] for i in a_indices]
        team_b = [players[i] for i in b_indices]

        avg_a = round(sum(p['overall_rating'] for p in team_a) / 6.0, 3)
        avg_b = round(sum(p['overall_rating'] for p in team_b) / 6.0, 3)
        diff = round(abs(avg_a - avg_b), 3)

        split_info = {
            "team_a": team_a,
            "team_b": team_b,
            "team_a_avg": round(avg_a, 2),
            "team_b_avg": round(avg_b, 2),
            "diff": diff,
            "target_met": diff <= target_diff
        }

        if diff < min_diff:
            min_diff = diff
            best_split = split_info

        if diff <= target_diff:
            valid_splits.append(split_info)

    if valid_splits:
        return random.choice(valid_splits)
    return best_split

def seed_initial_data():
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "Admin").first()
    if not admin:
        admin = User(
            username="Admin",
            password_hash=hash_pw("Admin@123"),
            full_name="System Admin",
            role="admin"
        )
        db.add(admin)
        db.commit()

    default_members = [
        ("raghavendra", "Raghavendra", 9.2, 5.0, 8.8),
        ("manoj", "Manoj", 8.8, 4.5, 8.4),
        ("sairam", "Sai ram reddy", 8.5, 7.8, 8.6),
        ("nagarjuna", "Nagarjuna", 7.5, 8.9, 8.0),
        ("randeep", "randeep", 6.8, 9.2, 7.8),
        ("yaswanth", "Yaswanth", 8.9, 4.0, 8.5),
        ("siva", "Siva", 6.5, 8.7, 7.9),
        ("srini", "Srini", 7.8, 7.9, 8.2),
        ("thofiq", "Thofiq", 8.4, 6.5, 8.1),
        ("sai", "Sai", 7.2, 8.5, 7.5),
        ("omhkar", "Omhkar", 8.1, 7.0, 8.3),
        ("dhana", "Dhana", 6.9, 8.8, 7.6),
        ("pavan", "Pavan", 8.7, 5.5, 8.9)
    ]

    created_players = []
    for uname, name, bat, bowl, fld in default_members:
        u = db.query(User).filter(User.username == uname).first()
        if not u:
            u = User(
                username=uname,
                password_hash=hash_pw("cricket123"),
                full_name=name,
                role="player"
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        created_players.append((u, bat, bowl, fld))

    if db.query(Rating).count() == 0:
        for rater_tuple in created_players[:3]:
            rater = rater_tuple[0]
            for rated_u, bat, bowl, fld in created_players:
                if rater.id != rated_u.id:
                    r = Rating(
                        rater_id=rater.id,
                        rated_player_id=rated_u.id,
                        batting=bat,
                        bowling=bowl,
                        fielding=fld
                    )
                    db.add(r)
        db.commit()
    db.close()

seed_initial_data()

app = FastAPI(title="CricEquiBalance")

class LoginReq(BaseModel):
    username: str
    password: str

class PasswordChangeReq(BaseModel):
    new_password: str

class RateReq(BaseModel):
    rated_player_id: int
    batting: float = Field(..., ge=1.0, le=10.0)
    bowling: float = Field(..., ge=1.0, le=10.0)
    fielding: float = Field(..., ge=1.0, le=10.0)

class ShuffleReq(BaseModel):
    selected_ids: Optional[List[int]] = None

class CaptainReq(BaseModel):
    team_a_captain_id: int
    team_b_captain_id: int

class TossReq(BaseModel):
    calling_captain_id: int
    call: str
    decision: str = "BAT"

@app.get("/api/state")
def get_app_state(request: Request):
    db = SessionLocal()
    current_user = get_current_user(request, db)
    players = db.query(User).filter(User.role == "player", User.is_active == True).all()
    players_data = [{
        "id": p.id,
        "username": p.username,
        "full_name": p.full_name,
        "rating_count": db.query(Rating).filter(Rating.rated_player_id == p.id).count()
    } for p in players]
    user_data = {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role
    } if current_user else None
    db.close()
    return {"current_user": user_data, "players": players_data}

@app.post("/api/login")
def login(req: LoginReq, response: Response):
    db = SessionLocal()
    user = db.query(User).filter(User.username == req.username, User.is_active == True).first()
    if not user or not verify_pw(req.password, user.password_hash):
        db.close()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(user.username)
    response.set_cookie("cric_token", token, httponly=True)
    user_data = {"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role}
    db.close()
    return {"message": "Success", "user": user_data}

@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("cric_token")
    return {"message": "Logged out"}

@app.post("/api/change-password")
def change_password(req: PasswordChangeReq, request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        raise HTTPException(status_code=401, detail="Not logged in")
    user.password_hash = hash_pw(req.new_password)
    db.commit()
    db.close()
    return {"message": "Password updated successfully!"}

class AddMemberReq(BaseModel):
    username: str
    full_name: str
    password: str = "cricket123"

class AdminChangePasswordReq(BaseModel):
    user_id: int
    new_password: str

@app.post("/api/admin/member")
def add_member(req: AddMemberReq, request: Request):
    db = SessionLocal()
    admin = get_current_user(request, db)
    if not admin or admin.role != "admin":
        db.close()
        raise HTTPException(status_code=403, detail="Only Admin can add members.")
    
    clean_uname = req.username.strip().lower()
    if db.query(User).filter(User.username == clean_uname).first():
        db.close()
        raise HTTPException(status_code=400, detail="Username already exists.")
    
    new_user = User(
        username=clean_uname,
        password_hash=hash_pw(req.password.strip() if req.password else "cricket123"),
        full_name=req.full_name.strip(),
        role="player"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    db.close()
    return {"message": f"Member '{new_user.full_name}' added successfully!"}

@app.post("/api/admin/member/change-password")
def admin_change_member_password(req: AdminChangePasswordReq, request: Request):
    db = SessionLocal()
    admin = get_current_user(request, db)
    if not admin or admin.role != "admin":
        db.close()
        raise HTTPException(status_code=403, detail="Only Admin can change member passwords.")
    
    target = db.query(User).filter(User.id == req.user_id).first()
    if not target:
        db.close()
        raise HTTPException(status_code=404, detail="Member not found.")
    
    name = target.full_name
    target.password_hash = hash_pw(req.new_password)
    db.commit()
    db.close()
    return {"message": f"Password for '{name}' updated successfully."}

@app.delete("/api/admin/member/{member_id}")
def delete_member(member_id: int, request: Request):
    db = SessionLocal()
    admin = get_current_user(request, db)
    if not admin or admin.role != "admin":
        db.close()
        raise HTTPException(status_code=403, detail="Only Admin can delete members.")
    
    target = db.query(User).filter(User.id == member_id).first()
    if not target:
        db.close()
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == "admin":
        db.close()
        raise HTTPException(status_code=400, detail="Cannot delete Admin account")

    name = target.full_name
    db.delete(target)
    db.commit()
    db.close()
    return {"message": f"Member {name} deleted successfully."}

@app.post("/api/rate")
def rate_player(req: RateReq, request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        raise HTTPException(status_code=401, detail="Please login as a member to rate.")
    if user.id == req.rated_player_id:
        db.close()
        raise HTTPException(status_code=400, detail="Players cannot rate themselves.")

    existing = db.query(Rating).filter(
        Rating.rater_id == user.id,
        Rating.rated_player_id == req.rated_player_id
    ).first()

    if existing:
        existing.batting = req.batting
        existing.bowling = req.bowling
        existing.fielding = req.fielding
    else:
        new_r = Rating(
            rater_id=user.id,
            rated_player_id=req.rated_player_id,
            batting=req.batting,
            bowling=req.bowling,
            fielding=req.fielding
        )
        db.add(new_r)
    db.commit()
    db.close()
    return {"message": "Rating saved successfully!"}

@app.post("/api/shuffle")
def shuffle_teams(req: ShuffleReq):
    db = SessionLocal()
    query = db.query(User).filter(User.role == "player", User.is_active == True)
    if req.selected_ids and len(req.selected_ids) == 12:
        players_db = query.filter(User.id.in_(req.selected_ids)).all()
    else:
        players_db = query.limit(12).all()

    if len(players_db) != 12:
        db.close()
        raise HTTPException(status_code=400, detail=f"12 players must be selected. Selected: {len(players_db)}")

    players_data = [get_player_stats(p, db) for p in players_db]
    result = balance_12_players(players_data, target_diff=0.10)

    match = Match(
        team_a_players=json.dumps([p['id'] for p in result['team_a']]),
        team_b_players=json.dumps([p['id'] for p in result['team_b']]),
        team_a_avg=result['team_a_avg'],
        team_b_avg=result['team_b_avg'],
        avg_diff=result['diff']
    )
    # Set default captains as first player of each team
    match.team_a_captain_id = result['team_a'][0]['id']
    match.team_b_captain_id = result['team_b'][0]['id']
    db.add(match)
    db.commit()
    db.refresh(match)
    db.close()

    return {
        "match_id": match.id,
        "team_a": [{"id": p["id"], "full_name": p["full_name"]} for p in result['team_a']],
        "team_b": [{"id": p["id"], "full_name": p["full_name"]} for p in result['team_b']],
        "team_a_captain_id": match.team_a_captain_id,
        "team_b_captain_id": match.team_b_captain_id,
        "team_a_avg": result['team_a_avg'],
        "team_b_avg": result['team_b_avg'],
        "diff": result['diff'],
        "target_met": result['target_met']
    }

@app.post("/api/match/{match_id}/captains")
def select_captains(match_id: int, req: CaptainReq):
    db = SessionLocal()
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        db.close()
        raise HTTPException(status_code=404, detail="Match not found")
    match.team_a_captain_id = req.team_a_captain_id
    match.team_b_captain_id = req.team_b_captain_id
    db.commit()
    
    cap_a = db.query(User).filter(User.id == req.team_a_captain_id).first()
    cap_b = db.query(User).filter(User.id == req.team_b_captain_id).first()
    db.close()
    return {
        "message": "Captains updated successfully.",
        "team_a_captain": cap_a.full_name if cap_a else "",
        "team_b_captain": cap_b.full_name if cap_b else ""
    }

@app.post("/api/match/{match_id}/toss")
def execute_toss(match_id: int, req: TossReq):
    db = SessionLocal()
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        db.close()
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Ensure captains are set
    calling_cap_id = req.calling_captain_id or match.team_a_captain_id
    if not calling_cap_id:
        calling_cap_id = match.team_a_captain_id

    coin = random.choice(["HEADS", "TAILS"])
    other_cap_id = match.team_b_captain_id if calling_cap_id == match.team_a_captain_id else match.team_a_captain_id

    winner_id = calling_cap_id if req.call.upper() == coin else other_cap_id
    winner = db.query(User).filter(User.id == winner_id).first()

    match.toss_winner_id = winner_id
    match.toss_decision = req.decision.upper()
    db.commit()

    statement = f"Coin showed {coin}! Captain {winner.full_name} won the toss and elected to {req.decision.upper()} first!"
    db.close()
    return {
        "coin": coin,
        "winner_id": winner_id,
        "winner_name": winner.full_name,
        "decision": req.decision.upper(),
        "statement": statement
    }

@app.get("/", response_class=HTMLResponse)
def index_page():
    html_path = Path("templates") / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
