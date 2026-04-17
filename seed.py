"""
Seed the database with one executive and one feeder user.
Idempotent — safe to call on every startup.
"""
import bcrypt
from sqlalchemy.orm import Session
import models


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def run_seed(db: Session) -> None:
    if db.query(models.User).count() > 0:
        return

    db.add(models.User(
        email="exec@preppath.io",
        name="Exec Admin",
        role="executive",
        hashed_pw=_hash("exec123"),
    ))
    db.add(models.User(
        email="feeder@preppath.io",
        name="Feeder User",
        role="feeder",
        hashed_pw=_hash("feeder123"),
    ))

    db.commit()
    print("✓ Database seeded: 2 users")
    print("  Seed credentials:")
    print("    executive  → exec@preppath.io   / exec123")
    print("    feeder     → feeder@preppath.io  / feeder123")
