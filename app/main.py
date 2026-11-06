import asyncio
import base64
import csv
import hashlib
import html
import io
import json
import logging
import os
import re
import secrets
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from . import engine as rules, jobs
from .cache import Cache
from .db import Application, Mission, Run, ShortLink, Visit, make_engine, transaction, insert_for
from .security import session_key, sign, unsign, verify_password
from .services import KST, add_vote, counts, expire_run, leaderboard_snapshot, personal_leaderboard, mission_public, run_public, week_bounds

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("open_casting")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StartInput(Input):
    mission_id: str = Field(max_length=80)
    nickname: str = Field(default="", max_length=24)


class AnswerInput(Input):
    text: str | int = Field(union_mode="left_to_right")
    index: int | None = None


class DigInput(Input):
    x: int = Field(strict=True, ge=0, le=9)
    y: int = Field(strict=True, ge=0, le=9)


class CastingInput(Input):
    nickname: str = Field(min_length=1, max_length=24)
    birth_year: int = Field(strict=True, ge=1900, le=2200)
    contact: str = Field(min_length=2, max_length=120)
    intro: str = Field(max_length=100)
    consent: bool = Field(strict=True)


class LoginInput(Input):
    password: str = Field(max_length=200)


class StatusInput(Input):
    status: str


class SponsorInput(Input):
    template: str
    title: str = Field(min_length=1, max_length=100)
    sponsor_name: str = Field(min_length=1, max_length=60)
    accent_color: str = "#d5ef45"
    logo: str | None = Field(default=None, max_length=280000)
    starts_at: float = Field(allow_inf_nan=False)
    ends_at: float = Field(allow_inf_nan=False)


class LinkInput(Input):
    mission_id: str = Field(max_length=80)


def safe_csv(rows, columns):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value for key, value in row.items()})
    return Response("\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="open-casting.csv"'})


def clean_logo(value):
    if not value:
        return None
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) > 200 * 1024:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ("PNG", "JPEG") or image.width * image.height > 4_000_000:
                raise ValueError()
            image.load()
            output = io.BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            if output.tell() > 200 * 1024:
                raise ValueError()
            return base64.b64encode(output.getvalue()).decode()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise rules.RuleError("invalid_logo")


def create_app(*, engine=None, secret=None, password_hash=None, clock=None, background=True, cache=None):
    engine = engine or make_engine()
    key = secret or session_key()
    studio_hash = os.getenv("STUDIO_PASSWORD_HASH", "") if password_hash is None else password_hash
    now = clock or time.time
    cache = cache or Cache(os.getenv("REDIS_URL"))
    secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    metrics = {}

    def maintenance():
        import datetime as dt
        jobs.rotate_daily_missions(dt.datetime.fromtimestamp(now(), KST).date(), engine=engine)
        jobs.close_due_missions(now(), engine=engine)
        jobs.purge_expired_applications(now(), engine=engine)

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(maintenance)
        async def loop():
            while True:
                await asyncio.sleep(30)
                try:
                    await asyncio.to_thread(maintenance)
                except Exception:
                    log.error(json.dumps({"event": "maintenance_failed"}))
        task = asyncio.create_task(loop()) if background else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Open Casting", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine, app.state.cache, app.state.clock = engine, cache, now

    @app.exception_handler(rules.RuleError)
    async def rule_error(request, exc):
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo contact details, passwords or submitted answers into errors/logs.
        return JSONResponse({"error": "invalid_input"}, status_code=422)

    @app.middleware("http")
    async def guard(request, call_next):
        started = time.perf_counter()
        device = unsign(request.cookies.get("oc_device", ""), key)
        minted = not device or device.get("kind") != "device"
        token = secrets.token_hex(24) if minted else device["token"]
        request.state.token = token
        # X-Forwarded-For is client-writable behind Render (it only appends), so trust only the configured edge header.
        edge = os.getenv("CLIENT_IP_HEADER", "")
        host = (edge and request.headers.get(edge)) or (request.client.host if request.client else "local")
        request.state.ip = hashlib.sha256(host.encode()).hexdigest()
        response = None
        if request.method in ("POST", "PATCH", "DELETE", "PUT"):
            origin = request.headers.get("origin")
            expected = urlsplit(str(request.url))
            if origin and origin != f"{expected.scheme}://{expected.netloc}":
                response = JSONResponse({"error": "origin_denied"}, status_code=403)
            elif request.headers.get("content-type", "").split(";")[0] != "application/json":
                response = JSONResponse({"error": "json_required"}, status_code=415)
            else:
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 300000:
                        response = JSONResponse({"error": "body_too_large"}, status_code=413)
                        break
                request._body = bytes(body)
        if response is None and request.url.path.startswith("/api/"):
            # The device token carries the real limit; the loose IP cap only stops cookie-dropping floods,
            # since carrier NAT and school Wi-Fi put many players behind one address.
            if not cache.hit("ip:" + request.state.ip, int(os.getenv("RATE_LIMIT_IP", "300")), 10) or not cache.hit("token:" + token, 30, 10):
                response = JSONResponse({"error": "rate_limit"}, status_code=429, headers={"Retry-After": "10"})
        if response is None:
            response = await call_next(request)
        if minted:
            response.set_cookie("oc_device", sign({"kind": "device", "token": token, "exp": time.time() + 365 * 86400}, key), httponly=True, samesite="strict", secure=secure, max_age=365 * 86400)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        response.headers["Cache-Control"] = "no-store"
        route = getattr(request.scope.get("route"), "path", "unmatched")
        metric = metrics.setdefault(route, {"count": 0, "sum": 0.0, "buckets": [0] * 6})
        elapsed = time.perf_counter() - started
        metric["count"] += 1
        metric["sum"] += elapsed
        for index, bound in enumerate((.005, .025, .1, .5, 1, float("inf"))):
            metric["buckets"][index] += elapsed <= bound
        log.info(json.dumps({"event": "request", "route": route, "method": request.method, "status": response.status_code, "duration_ms": round(elapsed * 1000, 2)}))
        return response

    def has_studio_session(request: Request):
        payload = unsign(request.cookies.get("oc_studio", ""), key)
        return bool(payload and payload.get("kind") == "studio" and payload.get("version") == hashlib.sha256(studio_hash.encode()).hexdigest())

    def studio(request: Request):
        if not has_studio_session(request):
            raise rules.RuleError("unauthorized", 401)

    def locked_mission(db, mission_id):
        mission = db.scalar(select(Mission).where(Mission.id == mission_id).with_for_update(read=True))
        if mission is None:
            raise rules.RuleError("not_found", 404)
        return mission

    def owned_run(db, run_id, token):
        # Keep lock ordering mission -> run, matching attempt creation and close jobs.
        initial = db.get(Run, run_id)
        if not initial or initial.token != token:
            raise rules.RuleError("not_found", 404)
        mission = locked_mission(db, initial.mission_id)
        run = db.scalar(select(Run).where(Run.id == run_id).with_for_update().execution_options(populate_existing=True))
        expire_run(run, mission, now())
        return run, mission

    @app.get("/healthz")
    def healthz():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            healthy = cache.ping()
            return JSONResponse({"ok": healthy, "database": "ok", "cache": "redis" if cache.redis else "memory"}, status_code=200 if healthy else 503)
        except Exception:
            return JSONResponse({"ok": False}, status_code=503)

    @app.get("/metrics")
    def prometheus(request: Request):
        token = os.getenv("METRICS_TOKEN", "")
        if token and not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
            raise rules.RuleError("unauthorized", 401)
        lines = ["# TYPE oc_requests_total counter", "# TYPE oc_request_duration_seconds histogram"]
        for route, values in list(metrics.items()):
            label = json.dumps(route)
            lines.append(f"oc_requests_total{{route={label}}} {values['count']}")
            lines.append(f"oc_request_duration_seconds_count{{route={label}}} {values['count']}")
            lines.append(f"oc_request_duration_seconds_sum{{route={label}}} {values['sum']}")
            for bound, value in zip(("0.005", "0.025", "0.1", "0.5", "1", "+Inf"), values["buckets"]):
                lines.append(f'oc_request_duration_seconds_bucket{{route={label},le="{bound}"}} {value}')
        with transaction(engine) as db:
            for template in rules.TEMPLATES:
                for name, finished in (("started", False), ("finished", True)):
                    query = select(func.count()).select_from(Run).join(Mission).where(Mission.template == template)
                    if finished:
                        query = query.where(Run.finished_at.is_not(None))
                    lines.append(f'oc_runs_{name}_total{{template="{template}"}} {db.scalar(query)}')
        return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    @app.get("/api/missions")
    def missions():
        with transaction(engine) as db:
            rows = db.scalars(select(Mission).where(Mission.ends_at > now()).order_by(Mission.is_sponsored, Mission.starts_at)).all()
            return {"missions": [mission_public(m, now()) for m in rows], "server_now": now()}

    @app.get("/api/missions/{mission_id}")
    def mission_detail(mission_id: str, request: Request):
        with transaction(engine) as db:
            m = db.get(Mission, mission_id)
            if m is None:
                raise rules.RuleError("not_found", 404)
            recent = db.scalars(select(Run).where(Run.token == request.state.token, Run.mission_id == m.id).order_by(Run.started_at.desc())).all()
            for r in recent:
                db.expunge(r)
                expire_run(r, m, now())
            return {"mission": mission_public(m, now()), "attempts_left": max(0, 3 - len(recent)), "recent_run": run_public(db, recent[0], m, now(), cache=cache) if recent else None}

    @app.get("/api/missions/{mission_id}/logo")
    def mission_logo(mission_id: str):
        with transaction(engine) as db:
            m = db.get(Mission, mission_id)
            if not m or not m.logo:
                raise rules.RuleError("not_found", 404)
            return Response(base64.b64decode(m.logo), media_type="image/png")

    @app.post("/api/runs")
    def start_run(data: StartInput, request: Request):
        with transaction(engine) as db:
            m = db.get(Mission, data.mission_id)
            if m is None:
                raise rules.RuleError("not_found", 404)
            if m.closed or not m.starts_at <= now() < m.ends_at:
                raise rules.RuleError("mission_closed", 409)
            timestamp = now()
            for attempt in range(1, 4):
                statement = insert_for(db, Run).values(
                    mission_id=m.id, token=request.state.token, attempt_no=attempt,
                    nickname=data.nickname or "Guest-" + request.state.token[:4], started_at=timestamp,
                    state=rules.start(m.template, m.seed, timestamp, m.ends_at))
                identifier = db.scalar(statement.on_conflict_do_nothing(
                    index_elements=["token", "mission_id", "attempt_no"]).returning(Run.id))
                if identifier:
                    return run_public(db, db.get(Run, identifier), m, timestamp, cache=cache)
            raise rules.RuleError("attempt_cap", 409)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, request: Request):
        with transaction(engine) as db:
            r, m = owned_run(db, run_id, request.state.token)
            return run_public(db, r, m, now(), cache=cache)

    @app.post("/api/runs/{run_id}/answer")
    def answer_run(run_id: str, data: AnswerInput, request: Request):
        with transaction(engine) as db:
            r, m = owned_run(db, run_id, request.state.token)
            if r.finished_at is not None:
                return run_public(db, r, m, now(), cache=cache)
            if data.index is not None and data.index != r.state["index"]:
                raise rules.RuleError("stale_prompt", 409)
            value = data.text
            if m.template == "no-rieul" and (not isinstance(value, str) or len(value) > 100):
                raise rules.RuleError("invalid_input")
            r.state, r.score, done, vote = rules.answer(m.template, r.state, r.score, value, now(), m.ends_at)
            if vote:
                add_vote(db, m.id, *vote)
                cache.delete("option_counts:" + m.id)
            if done:
                r.finished_at = now()
            return run_public(db, r, m, now(), cache=cache)

    @app.post("/api/runs/{run_id}/dig")
    def dig_run(run_id: str, data: DigInput, request: Request):
        with transaction(engine) as db:
            r, m = owned_run(db, run_id, request.state.token)
            if m.template != "ore-hunt":
                raise rules.RuleError("wrong_action")
            if r.finished_at is not None:
                return run_public(db, r, m, now())
            r.state, r.score, done, cell = rules.dig(r.state, r.score, m.seed, data.x, data.y, now(), m.ends_at)
            if done:
                r.finished_at = now()
            return run_public(db, r, m, now()) | {"cell": cell}

    @app.get("/api/leaderboards/{mission_id}")
    def rankings(mission_id: str, request: Request):
        def build():
            with transaction(engine) as db:
                return leaderboard_snapshot(db, mission_id, now())
        # Weekly keys roll at the week boundary, independent of the short cache TTL.
        period = week_bounds(now())[0] if mission_id == "weekly" else ""
        snapshot = cache.remember("leaderboard:" + mission_id + ":" + period, build)
        return personal_leaderboard(snapshot, request.state.token)

    @app.get("/api/casting/eligibility")
    def eligibility(request: Request):
        _, start, end = week_bounds(now())
        with transaction(engine) as db:
            rows = db.scalars(select(Run).where(Run.token == request.state.token, Run.is_demo.is_(False), Run.finished_at >= start, Run.finished_at < end)).all()
            records = {}
            for row in rows:
                m = db.get(Mission, row.mission_id)
                score = run_public(db, row, m, now())["score"]
                records[m.id] = {"mission_id": m.id, "template": m.template, "score": max(score, records.get(m.id, {}).get("score", 0))}
            return {"eligible": bool(rows), "records": list(records.values())}

    @app.post("/api/casting")
    def apply_casting(data: CastingInput, request: Request):
        import datetime as dt
        year = dt.datetime.fromtimestamp(now(), KST).year
        # Birth year alone cannot prove 만 14세 before the birthday, so require 15 by year.
        if not 15 <= year - data.birth_year <= 126:
            raise rules.RuleError("age_gate")
        if not data.consent:
            raise rules.RuleError("consent_required")
        if re.fullmatch(r"[+\d\s().-]{7,}", data.contact) or "\n" in data.contact or "\r" in data.contact:
            raise rules.RuleError("invalid_contact")
        if "@" in data.contact and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", data.contact):
            raise rules.RuleError("invalid_contact")
        attached = eligibility(request)
        if not attached["eligible"]:
            raise rules.RuleError("not_eligible", 403)
        week, _, _ = week_bounds(now())
        with transaction(engine) as db:
            statement = insert_for(db, Application).values(token=request.state.token, week=week,
                nickname=data.nickname, age_ok=True, contact=data.contact, intro=data.intro,
                records=attached["records"], submitted_at=now())
            identifier = db.scalar(statement.on_conflict_do_nothing(index_elements=["token", "week"]).returning(Application.id))
            if not identifier:
                raise rules.RuleError("already_applied", 409)
            return {"id": identifier, "expires_at": now() + 30 * 86400}

    @app.get("/api/studio/session")
    def studio_session(request: Request):
        return {"authenticated": has_studio_session(request)}

    @app.post("/api/studio/login")
    def login(data: LoginInput, request: Request):
        if not cache.hit("login:" + request.state.ip, 5, 60):
            raise rules.RuleError("rate_limit", 429)
        if not studio_hash:
            raise rules.RuleError("studio_unconfigured", 503)
        if not verify_password(data.password, studio_hash):
            raise rules.RuleError("unauthorized", 401)
        response = JSONResponse({"ok": True})
        response.set_cookie("oc_studio", sign({"kind": "studio", "exp": time.time() + 8 * 3600, "version": hashlib.sha256(studio_hash.encode()).hexdigest()}, key), httponly=True, secure=secure, samesite="strict", max_age=8 * 3600)
        return response

    @app.post("/api/studio/logout")
    def logout():
        response = JSONResponse({"ok": True})
        response.delete_cookie("oc_studio")
        return response

    @app.get("/api/studio/applications", dependencies=[Depends(studio)])
    def studio_applications(status: str = "all", sort: str = "newest", format: str = "json"):
        jobs.purge_expired_applications(now(), engine=engine)
        with transaction(engine) as db:
            query = select(Application)
            if status != "all":
                query = query.where(Application.status == status)
            rows = db.scalars(query.order_by(Application.submitted_at.desc())).all()
            result = [{key: getattr(row, key) for key in ("id", "nickname", "age_ok", "contact", "intro", "records", "submitted_at", "status")} for row in rows]
            if sort == "score":
                result.sort(key=lambda row: sum(r["score"] for r in row["records"]), reverse=True)
            if format == "csv":
                return safe_csv([{**row, "records": json.dumps(row["records"], ensure_ascii=False)} for row in result], ["id", "nickname", "age_ok", "contact", "intro", "records", "status", "submitted_at"])
            return {"applications": result}

    @app.patch("/api/studio/applications/{application_id}", dependencies=[Depends(studio)])
    def update_application(application_id: str, data: StatusInput):
        if data.status not in ("shortlisted", "invited", "declined"):
            raise rules.RuleError("invalid_status")
        with transaction(engine) as db:
            row = db.get(Application, application_id)
            if not row or row.submitted_at <= now() - 30 * 86400:
                raise rules.RuleError("not_found", 404)
            row.status = data.status
            return {"ok": True}

    @app.get("/api/studio/missions", dependencies=[Depends(studio)])
    def studio_missions():
        with transaction(engine) as db:
            rows = db.scalars(select(Mission).order_by(Mission.starts_at.desc())).all()
            return {"missions": [mission_public(m, now()) for m in rows]}

    @app.post("/api/studio/missions", dependencies=[Depends(studio)])
    def create_sponsored(data: SponsorInput):
        if data.template not in rules.TEMPLATES or not re.fullmatch(r"#[0-9a-fA-F]{6}", data.accent_color) or data.starts_at >= data.ends_at or data.ends_at <= now() or data.ends_at - data.starts_at > 90 * 86400:
            raise rules.RuleError("invalid_mission")
        logo = clean_logo(data.logo)
        with transaction(engine) as db:
            identifier = secrets.token_hex(12)
            m = Mission(id=identifier, seed=secrets.token_hex(24), template=data.template, title=data.title, sponsor_name=data.sponsor_name, accent_color=data.accent_color, starts_at=data.starts_at, ends_at=data.ends_at, is_sponsored=True, logo=logo)
            db.add(m)
            db.flush()
            return mission_public(m, now())

    @app.get("/api/studio/reports/{mission_id}", dependencies=[Depends(studio)])
    def sponsor_report(mission_id: str, format: str = "json"):
        report = jobs.build_sponsor_report(mission_id, engine=engine)
        if format == "csv":
            return safe_csv(report["days"], ["date", "unique_players", "runs", "completed_runs", "completion_rate", "average_score", "average_session_time", "short_link_visits", "has_demo"])
        return report

    @app.get("/api/studio/links", dependencies=[Depends(studio)])
    def links():
        with transaction(engine) as db:
            return {"links": [{"code": r.code, "mission_id": r.mission_id, "visits": db.scalar(select(func.count()).select_from(Visit).where(Visit.code == r.code))} for r in db.scalars(select(ShortLink))]}

    @app.post("/api/studio/links", dependencies=[Depends(studio)])
    def create_link(data: LinkInput):
        with transaction(engine) as db:
            locked_mission(db, data.mission_id)
            code = secrets.token_urlsafe(6)
            db.add(ShortLink(code=code, mission_id=data.mission_id))
            return {"code": code, "url": "/v/" + code}

    @app.get("/v/{code}")
    def visit(code: str):
        with transaction(engine) as db:
            link = db.get(ShortLink, code)
            if not link:
                raise rules.RuleError("not_found", 404)
            db.add(Visit(code=code, visited_at=now()))
            return RedirectResponse("/missions/" + link.mission_id, status_code=302)

    @app.get("/api/config")
    def config():
        return {"sponsor_contact": os.getenv("SPONSOR_CONTACT", "")}

    @app.get("/favicon.ico")
    def favicon():
        return Response(status_code=204)

    @app.get("/", response_class=HTMLResponse)
    @app.get("/missions/{mission_id}", response_class=HTMLResponse)
    @app.get("/leaderboard", response_class=HTMLResponse)
    @app.get("/casting", response_class=HTMLResponse)
    @app.get("/studio", response_class=HTMLResponse)
    @app.get("/studio/reports/{mission_id}", response_class=HTMLResponse)
    @app.get("/sponsor", response_class=HTMLResponse)
    @app.get("/faq", response_class=HTMLResponse)
    def page(mission_id: str | None = None):
        label = ""
        if mission_id:
            with transaction(engine) as db:
                m = db.get(Mission, mission_id)
                if not m:
                    raise rules.RuleError("not_found", 404)
                if m.is_sponsored:
                    label = '<div class="sponsor-label">광고 · Sponsored by ' + html.escape(m.sponsor_name) + '</div>'
        return (STATIC / "index.html").read_text().replace("<!--SPONSOR-->", label)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
