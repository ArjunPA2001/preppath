"""
Users router.

Roles: executive | feeder | candidate

Endpoints:
  POST  /users                — create a user (any role)
                                creating a candidate-role user also creates a Candidate record
  GET   /users                — list all users
  GET   /users/{id}           — get one user (with candidate profile if role=candidate)
  PUT   /users/{id}           — update name / email / role
  DELETE /users/{id}          — delete user (and linked candidate record if any)
  POST  /users/login          — authenticate with email + password
"""
import json
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
import models
from database import get_db

router = APIRouter()


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

VALID_ROLES = {"executive", "feeder", "candidate"}


# ── Request schemas ──────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str  # executive | feeder | candidate
    # When a feeder/executive creates a candidate user, pass their own user.id here.
    # Used for attribution in the executive dashboard. Ignored for non-candidate roles.
    created_by_user_id: int | None = None


class UpdateUserRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    password: str | None = None
    # Used when promoting a user to role=candidate and a new Candidate record is auto-created
    created_by_user_id: int | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_dict(u: models.User, candidate: models.Candidate | None = None) -> dict:
    d = {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }
    if candidate:
        d["candidate"] = {
            "id": candidate.id,
            "learning_path_id": candidate.learning_path_id,
            "channel": candidate.channel,
            "level": candidate.level,
            "gaps": json.loads(candidate.gaps or "[]"),
            "strengths": json.loads(candidate.strengths or "[]"),
            "interview_ready": candidate.interview_ready,
            "readiness_score": candidate.readiness_score,
            "plan_id": candidate.plan_id,
        }
    return d


def _get_candidate(db: DBSession, user_id: int) -> models.Candidate | None:
    return db.query(models.Candidate).filter_by(user_id=user_id).first()


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("")
def create_user(body: CreateUserRequest, db: DBSession = Depends(get_db)):
    """
    Create a new user.
    If role=candidate, a blank Candidate profile is also created automatically.
    """
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{body.role}'. Must be one of: {', '.join(sorted(VALID_ROLES))}",
        )
    existing = db.query(models.User).filter_by(email=body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Email '{body.email}' is already registered")

    user = models.User(
        email=body.email,
        name=body.name,
        role=body.role,
        hashed_pw=_hash(body.password),
    )
    db.add(user)
    db.flush()  # get user.id before commit

    candidate = None
    if body.role == "candidate":
        candidate = models.Candidate(
            user_id=user.id,
            created_by_user_id=body.created_by_user_id,
            channel="",
            level="",
            gaps=json.dumps([]),
            strengths=json.dumps([]),
        )
        db.add(candidate)

    db.commit()
    if candidate:
        db.refresh(candidate)
    db.refresh(user)

    return _user_dict(user, candidate)


@router.get("")
def list_users(role: str | None = None, db: DBSession = Depends(get_db)):
    """List all users. Optionally filter by role."""
    q = db.query(models.User)
    if role:
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role filter '{role}'")
        q = q.filter_by(role=role)
    users = q.order_by(models.User.id).all()

    result = []
    for u in users:
        cand = _get_candidate(db, u.id) if u.role == "candidate" else None
        result.append(_user_dict(u, cand))
    return {"users": result}


@router.get("/{user_id}")
def get_user(user_id: int, db: DBSession = Depends(get_db)):
    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    cand = _get_candidate(db, user_id) if user.role == "candidate" else None
    return _user_dict(user, cand)


@router.put("/{user_id}")
def update_user(user_id: int, body: UpdateUserRequest, db: DBSession = Depends(get_db)):
    """Update name, email, role, or password."""
    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.email is not None:
        clash = db.query(models.User).filter(
            models.User.email == body.email,
            models.User.id != user_id,
        ).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Email '{body.email}' is already registered")
        user.email = body.email

    if body.name is not None:
        user.name = body.name

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'")
        old_role = user.role
        user.role = body.role
        # If promoted to candidate, create the Candidate profile if missing
        if body.role == "candidate" and old_role != "candidate":
            if not _get_candidate(db, user_id):
                db.add(models.Candidate(
                    user_id=user_id,
                    created_by_user_id=body.created_by_user_id,
                    channel="",
                    level="",
                    gaps=json.dumps([]),
                    strengths=json.dumps([]),
                ))

    if body.password is not None:
        user.hashed_pw = _hash(body.password)

    db.commit()
    db.refresh(user)
    cand = _get_candidate(db, user_id) if user.role == "candidate" else None
    return _user_dict(user, cand)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: DBSession = Depends(get_db)):
    """Delete a user. Also deletes the linked Candidate record if present."""
    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    cand = _get_candidate(db, user_id)
    if cand:
        db.delete(cand)

    db.delete(user)
    db.commit()
    return {"deleted": True, "user_id": user_id}


@router.post("/login")
def login(body: LoginRequest, db: DBSession = Depends(get_db)):
    """
    Authenticate with email + password.
    Returns the user record (and candidate profile if role=candidate).
    Does NOT issue a JWT — caller uses the returned id for subsequent requests.
    """
    user = db.query(models.User).filter_by(email=body.email).first()
    if not user or not _verify(body.password, user.hashed_pw):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    cand = _get_candidate(db, user.id) if user.role == "candidate" else None
    return _user_dict(user, cand)
