import datetime as dt
import hashlib
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import engine as rules
from .db import Mission, OptionCount, Run, insert_for

KST = ZoneInfo("Asia/Seoul")


def week_bounds(now):
    day = dt.datetime.fromtimestamp(now, KST)
    start = (day - dt.timedelta(days=day.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%G-W%V"), start.timestamp(), (start + dt.timedelta(days=7)).timestamp()


def counts(db, mission_id, cache=None):
    if cache:
        cached = cache.get("option_counts:" + mission_id)
        if cached is not None:
            return cached
    result = [[0] * 4 for _ in range(10)]
    for row in db.scalars(select(OptionCount).where(OptionCount.mission_id == mission_id)):
        result[row.question][row.option] = row.count
    if cache:
        cache.set("option_counts:" + mission_id, result)
    return result


def add_vote(db, mission_id, question, option):
    statement = insert_for(db, OptionCount).values(mission_id=mission_id, question=question, option=option, count=1)
    db.execute(statement.on_conflict_do_update(
        index_elements=["mission_id", "question", "option"], set_={"count": OptionCount.count + 1}))


def mission_public(mission, now):
    return {key: getattr(mission, key) for key in ("id", "template", "title", "starts_at", "ends_at", "is_sponsored", "sponsor_name", "accent_color", "closed")} | {"has_logo": bool(mission.logo), "active": mission.starts_at <= now < mission.ends_at and not mission.closed}


def expire_run(run, mission, now):
    if run.finished_at is None and now >= min(run.state["deadline"], mission.ends_at):
        run.finished_at = min(run.state["deadline"], mission.ends_at)
        run.state = run.state | {"reason": "timeout"}


def run_public(db, run, mission, now, cache=None):
    state = run.state
    score = run.score
    if mission.template == "telepathy":
        # Live majorities stay server-side: a mid-run score or count would tell players what to pick next.
        score = rules.telepathy_score(state["answers"], counts(db, mission.id)) if run.finished_at is not None else None
    result = {"id": run.id, "mission_id": mission.id, "template": mission.template, "score": score, "finished": run.finished_at is not None, "final": mission.closed if mission.template == "telepathy" else run.finished_at is not None, "index": state["index"], "deadline": state["deadline"], "server_now": now, "reason": state["reason"], "digs": state["digs"], "used": state["used"]}
    if mission.template == "no-rieul" and run.finished_at is None:
        result["category"] = state["categories"][state["index"]]
    if mission.template == "telepathy" and mission.closed:
        result["counts"] = counts(db, mission.id, cache)
    if mission.template == "ore-hunt" and run.finished_at is not None:
        result["board"] = rules.ore_board(mission.seed)
    return result


def leaderboard_snapshot(db, mission_id, now):
    query = select(Run, Mission).join(Mission, Run.mission_id == Mission.id).where(Run.finished_at.is_not(None))
    if mission_id == "weekly":
        _, start, end = week_bounds(now)
        query = query.where(Run.finished_at >= start, Run.finished_at < end)
    else:
        query = query.where(Run.mission_id == mission_id)
    best, names, demos = {}, {}, {}
    count_cache = {}
    provisional = False
    for run, mission in db.execute(query):
        if mission.template == "telepathy" and not mission.closed:
            provisional = True
            if mission.id not in count_cache:
                count_cache[mission.id] = counts(db, mission.id)
            score = rules.telepathy_score(run.state["answers"], count_cache[mission.id])
        else:
            score = run.score
        key = (run.token, mission.id)
        best[key] = max(best.get(key, 0), score)
        names[run.token] = run.nickname
        demos[run.token] = demos.get(run.token, False) or run.is_demo
    totals = {}
    for (owner, _), score in best.items():
        totals[owner] = totals.get(owner, 0) + score
    ordered = sorted(totals, key=lambda owner: (-totals[owner], owner))
    rank, last_score = 0, None
    rows, owners = [], {}
    for index, owner in enumerate(ordered, 1):
        if totals[owner] != last_score:
            rank, last_score = index, totals[owner]
        row = {"rank": rank, "nickname": names[owner], "score": totals[owner], "is_demo": demos[owner]}
        if index <= 100:
            rows.append(row)
        owners[hashlib.sha256(owner.encode()).hexdigest()] = row
    return {"rows": rows, "owners": owners, "has_demo": any(row["is_demo"] for row in rows), "provisional": provisional}


def personal_leaderboard(snapshot, token):
    return {key: value for key, value in snapshot.items() if key != "owners"} | {
        "mine": snapshot["owners"].get(hashlib.sha256(token.encode()).hexdigest())}


def leaderboard(db, mission_id, token, now):
    return personal_leaderboard(leaderboard_snapshot(db, mission_id, now), token)
