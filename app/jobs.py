"""Idempotent jobs, independent of HTTP/request state."""
import argparse
import datetime as dt
import json
import secrets
import time

from sqlalchemy import delete, select, or_

from . import engine as rules
from .db import Application, Mission, Run, ShortLink, Visit, make_engine, transaction, insert_for
from .services import KST, counts, expire_run


def rotate_daily_missions(date=None, *, engine=None):
    engine = engine or make_engine()
    day = dt.date.fromisoformat(date) if isinstance(date, str) else date or dt.datetime.now(KST).date()
    start = dt.datetime.combine(day, dt.time(), KST)
    with transaction(engine) as db:
        for template in rules.TEMPLATES:
            key = f"{day.isoformat()}-{template}"
            db.execute(insert_for(db, Mission).values(id=key, template=template, seed=secrets.token_hex(24), starts_at=start.timestamp(), ends_at=(start + dt.timedelta(days=1)).timestamp()).on_conflict_do_nothing(index_elements=["id"]))
    return day.isoformat()


def close_due_missions(now=None, *, engine=None):
    engine, now = engine or make_engine(), time.time() if now is None else now
    # Abandoned runs: lock only those rows and skip any a request holds; past the deadline that request can only time out too.
    # Own transaction, so it never holds run locks while waiting for a mission lock (requests lock mission -> run).
    with transaction(engine) as db:
        open_runs = select(Run, Mission).join(Mission, Run.mission_id == Mission.id).where(Run.finished_at.is_(None), or_(Run.state["deadline"].as_float() <= now, Mission.ends_at <= now))
        for run, mission in db.execute(open_runs.with_for_update(of=Run, skip_locked=True)):
            expire_run(run, mission, now)
    changed = 0
    with transaction(engine) as db:
        due = select(Mission).where(Mission.closed.is_(False), Mission.ends_at <= now).order_by(Mission.id).with_for_update(skip_locked=True)
        for mission in db.scalars(due).all():
            runs = db.scalars(select(Run).where(Run.mission_id == mission.id)).all()
            for run in runs:
                expire_run(run, mission, now)
            if mission.template == "telepathy":
                final_counts = counts(db, mission.id)
                for run in runs:
                    run.score = rules.telepathy_score(run.state["answers"], final_counts)
            mission.closed = True
            changed += 1
    return changed


def purge_expired_applications(now=None, *, engine=None):
    engine, now = engine or make_engine(), time.time() if now is None else now
    with transaction(engine) as db:
        return db.execute(delete(Application).where(Application.submitted_at <= now - 30 * 86400)).rowcount


def build_sponsor_report(mission_id, *, engine=None):
    engine = engine or make_engine()
    with transaction(engine) as db:
        mission = db.get(Mission, mission_id)
        if not mission:
            raise rules.RuleError("not_found", 404)
        rows = db.scalars(select(Run).where(Run.mission_id == mission_id)).all()
        visits = db.scalars(select(Visit).join(ShortLink, Visit.code == ShortLink.code).where(ShortLink.mission_id == mission_id)).all()
        live_counts = counts(db, mission_id) if mission.template == "telepathy" else None
        def summarize(runs, links):
            finished = [r for r in runs if r.finished_at is not None]
            scores = [rules.telepathy_score(r.state["answers"], live_counts) if live_counts else r.score for r in finished]
            return {"unique_players": len({r.token for r in runs}), "runs": len(runs), "completed_runs": len(finished), "completion_rate": round(len(finished) / len(runs), 4) if runs else 0, "average_score": round(sum(scores) / len(scores), 2) if scores else 0, "average_session_time": round(sum(r.finished_at - r.started_at for r in finished) / len(finished), 2) if finished else 0, "short_link_visits": len(links), "has_demo": any(r.is_demo for r in runs)}
        def day(timestamp):
            return dt.datetime.fromtimestamp(timestamp, KST).date().isoformat()
        days = sorted({day(r.started_at) for r in rows} | {day(v.visited_at) for v in visits})
        return {"mission_id": mission_id, "sponsor_name": mission.sponsor_name, "provisional": mission.template == "telepathy" and not mission.closed, "totals": summarize(rows, visits), "days": [{"date": d, **summarize([r for r in rows if day(r.started_at) == d], [v for v in visits if day(v.visited_at) == d])} for d in days]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name", choices=["rotate_daily_missions", "close_due_missions", "purge_expired_applications", "build_sponsor_report"])
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    if args.name == "rotate_daily_missions":
        result = rotate_daily_missions(args.value)
    elif args.name == "build_sponsor_report":
        result = build_sponsor_report(args.value)
    else:
        result = globals()[args.name](float(args.value) if args.value else None)
    print(json.dumps(result, ensure_ascii=False))
