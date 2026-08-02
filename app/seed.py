import json
from pathlib import Path
from sqlalchemy.orm import Session
from .models import Unit


def seed_units(db: Session) -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "units.json"
    if not path.exists():
        return
    items = json.loads(path.read_text(encoding="utf-8"))
    for item in items:
        existing = db.query(Unit).filter(Unit.code == item["code"]).first()
        if existing:
            for key, value in item.items():
                setattr(existing, key, value)
        else:
            db.add(Unit(**item))
    db.commit()
