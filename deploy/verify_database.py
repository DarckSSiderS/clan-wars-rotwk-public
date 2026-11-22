from sqlalchemy import inspect

from app.database import SessionLocal, engine
from app.models.clan import Clan
from app.models.match import Match
from app.models.territory import Territory
from app.models.user import User


with SessionLocal() as db:
    result = {
        "dialect": engine.dialect.name,
        "users": db.query(User).count(),
        "clans": db.query(Clan).count(),
        "matches": db.query(Match).count(),
        "territories": db.query(Territory).count(),
        "tables": len(inspect(engine).get_table_names()),
    }
    print(result)

if result["users"] < 1 or result["territories"] != 76:
    raise SystemExit("Database verification failed")
