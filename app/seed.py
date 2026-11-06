"""Synthetic demo records only. Safe to run repeatedly."""
import datetime as dt
import random

from sqlalchemy import select

from . import engine as rules
from .db import Mission, Run, ShortLink, make_engine, transaction
from .jobs import rotate_daily_missions
from .services import KST, add_vote


def seed(engine=None):
    engine = engine or make_engine()
    day = dt.datetime.now(KST).date()
    rotate_daily_missions(day, engine=engine)
    start = dt.datetime.combine(day, dt.time(), KST).timestamp()
    rng = random.Random("open-casting-demo")
    with transaction(engine) as db:
        sponsored_id = f"{day}-sponsored-demo"
        if not db.get(Mission, sponsored_id):
            db.add(Mission(id=sponsored_id, template="ore-hunt", seed="demo-" + str(day), starts_at=start, ends_at=start + 86400, is_sponsored=True, sponsor_name="Demo Games", title=""))
            db.flush()
        missions = db.scalars(select(Mission).where(Mission.starts_at == start)).all()
        for m in missions:
            if not db.get(ShortLink, "demo-" + m.template + ("-ad" if m.is_sponsored else "")):
                db.add(ShortLink(code="demo-" + m.template + ("-ad" if m.is_sponsored else ""), mission_id=m.id))
            for i in range(50):
                identifier = f"demo-{m.id}-{i}"
                if db.get(Run, identifier):
                    continue
                timestamp = min(dt.datetime.now(KST).timestamp() - 65, start + 300 + i * 60)
                state = rules.start(m.template, m.seed, timestamp, m.ends_at)
                score = rng.randrange(1, 9) * 100
                if m.template == "telepathy":
                    state["answers"] = [rng.randrange(4) for _ in range(10)]
                    for q, option in enumerate(state["answers"]):
                        add_vote(db, m.id, q, option)
                elif m.template == "ore-hunt":
                    score = rng.choice([10, 30, 40, 60, 100, 140, 180, 200])
                state["reason"] = "complete"
                db.add(Run(id=identifier, mission_id=m.id, token=f"demo-{i}", nickname=f"Demo {i + 1:02}", started_at=timestamp, finished_at=timestamp + 25, score=score, state=state, is_demo=True))
    print("Demo seed ready (synthetic records, is_demo=true).")


if __name__ == "__main__":
    seed()
