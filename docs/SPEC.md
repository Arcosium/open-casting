# Open Casting — Product & Build Spec (M1)

Hackathon: Extriver "Hack the Audience" (build Nov 5 – Dec 5, 2026, final pitch Dec 7).
Creator partner: **GodDot** (YouTube channel "Dname", @d_name0 — Shorts only).
Team: Arka (1 person). This file is the source of truth for M1. Korean background research lives outside this repo.

## 1. Why this product

GodDot's Shorts invite viewers to join on-camera missions ("Don't say ㄹ for 100,000 won", "Find the ore in one minute").
The channel description's first line is "구독하고 게임에 참가하세요!" (Subscribe and join the game!).
Median views of the latest 50 Shorts: **1.7M** on **270K** subscribers (6.3× views per subscriber; the other four creators sit at 0.07–0.55×).
Comments keep asking to join, but only a handful of people can appear per video.

**Open Casting** lets every viewer play the same missions in the browser at any time.
Records become a public reference attached to an on-camera casting application. The creator picks the cast.
Brands (game publishers etc.) pay for **sponsored missions**. Viewers never pay.

## 2. Legal guardrails (non-negotiable, encode them in product and tests)

1. The service gives **no money, goods, coupons or anything of value**. Rank rewards are display-only badges.
2. **No paid entry, no paid retries, no randomized paid items.** Free attempts are capped per day.
3. Casting is **not decided by rank**. Anyone who finished ≥1 mission this week may apply; the creator chooses. Any prize money stays inside the creator's own recorded event, outside this service.
4. Sponsored missions show a fixed **"광고 · Sponsored by {name}"** label at the top of every sponsored screen.
5. Play is anonymous (device token + nickname). Casting applications only from age **만 14+**. Only the birth year is asked, so the check is `current year − birth year ≥ 15` (a 14-year-old before their birthday would otherwise pass). Contact data (Discord ID or email) is **auto-deleted 30 days** after submission.
6. Voice input (optional) uses the browser Web Speech API on device. **No audio leaves the device**; only the transcript is sent.
7. No Minecraft names, textures or logos. No creator face or voice. Original flat graphics only.

## 3. Missions (server-authoritative)

All timing and scoring is computed by the server from its own clock. The client only renders.
Each mission instance has `id`, `template`, `seed`, `starts_at`, `ends_at`, `is_sponsored`, `sponsor_name`, `accent_color`, `logo` (optional).
Default daily rotation creates one instance per template for today (Asia/Seoul).
Attempts: 3 per device token per mission instance.

### 3.1 `no-rieul` — "ㄹ 금지 토크" / "Don't Say ㄹ"
- Run = up to 8 prompts. Each prompt is a category (과일, 동물, 나라, 색깔, 음식, 직업, 탈것, 운동 …) with a **7.0 s** limit (server measures; +1.5 s network grace).
- Answer valid iff: normalized (trim, remove spaces) answer is in that category's word list, not used earlier in the run, and contains **no ㄹ** (initial ㄹ, or final ㄹ/ㄺ/ㄻ/ㄼ/ㄽ/ㄾ/ㄿ/ㅀ).
  Hangul syllable s: `i = ord(s) - 0xAC00`, `cho = i // 588`, `jong = i % 28`; ㄹ iff `cho == 5` or `jong in {8..15}`.
- Word lists: `app/words_ko.json`, ≥ 40 words per category, deliberately mixing ㄹ and non-ㄹ words (e.g. 과일: 사과 ✓, 딸기 ✗, 귤 ✗, 포도 ✓, 레몬 ✗, 수박 ✓).
- First invalid / ㄹ / timeout ends the run. Score = cleared × 100 + Σ remaining tenths of a second.
- API: `POST /api/runs {mission_id}` → run + first prompt; `POST /api/runs/{id}/answer {text}` → result + next prompt or final score.

### 3.2 `telepathy` — "텔레파시" / "Mind Match"
- 10 questions, 4 options each, 5 s per question (server measures; +1.5 s network grace). Generic everyday prompts (no third-party IP).
- Option counts stored atomically per (mission, question, option). Counts are returned only after the mission closes, and no score is returned while a run is in progress; either would reveal the live majority for the next pick.
- Provisional score of a finished run = matches with the **current** majority. At mission close a job computes the **final** majority and final scores (ties: all tied options count as majority).
- Close job must be idempotent.

### 3.3 `ore-hunt` — "1분 광석 찾기" / "One-Minute Ore Hunt"
- 10×10 grid from `random.Random(f"{mission.seed}")`: 12 hidden ores (iron 10 / gold 30 / gem 100 points). Same board for everyone in the instance.
- 25 digs, 60 s limit. `POST /api/runs/{id}/dig {x, y}` returns only that cell: ore type, or Manhattan distance to the nearest undiscovered ore.
- Score = sum of ore points. The board never leaves the server before the run ends.

## 4. Other features

- **Leaderboards**: per mission instance (top 100 + my rank) and weekly (best per mission summed). Rows created by the demo seed carry `is_demo` and the UI shows a "시연용 가상 데이터 / Demo data" badge when any are visible.
- **Casting application** `/casting`: eligible if ≥1 finished run this ISO week. Fields: nickname, birth year (만 14+ via the §2-5 year rule, else a clear message), contact (Discord ID or email), intro ≤ 100 chars, consent checkbox (purpose: casting contact, retention 30 days). Best records attached automatically. No phone numbers.
- **Creator studio** `/studio`: password from env `STUDIO_PASSWORD_HASH` (scrypt via `hashlib.scrypt`), signed session cookie, login rate limit. Views: applications (sort/filter by records, statuses shortlisted/invited/declined, CSV export without birth year — only an `age_ok` flag), mission stats, short links, sponsored mission builder.
- **Sponsored mission builder** (in studio): template, title, sponsor name, accent color, optional logo (PNG/JPEG ≤ 200 KB), start/end. **Report**: unique players, runs, completion rate, average score, average session time, short-link visits, per day; CSV export.
- **Short links** `/v/{code}`: per-video entry links that count visits then redirect to a mission.
- **Sponsor info page** `/sponsor`: what a sponsored mission is, sample report, contact. No payments in M1.
- **i18n**: Korean default, English toggle. All UI strings in `app/static/i18n/{ko,en}.json`; a test enforces identical key sets.
- **FAQ** with the guardrails in plain words ("이 사이트는 상금을 주지 않습니다. 출연자는 크리에이터가 직접 고릅니다.").

## 5. Architecture

- Python 3.12, FastAPI, SQLAlchemy 2. `DATABASE_URL` (SQLite file locally, Postgres on Render later). `REDIS_URL` optional: leaderboards, option counts and rate limits use Redis when set, otherwise an in-process fallback with the same interface.
- Frontend: static HTML + ES modules served by FastAPI. No bundler. Mobile-first (390 px), also checked at 1280 px.
- `app/jobs.py`: pure, idempotent jobs callable as `python -m app.jobs <name>` — `rotate_daily_missions(date)`, `close_due_missions(now)`, `purge_expired_applications(now)`, `build_sponsor_report(mission_id)`. M2 wraps these as Render Workflows tasks; keep them free of web/request state.
- Ops endpoints: `/healthz` (DB + cache ping, JSON), `/metrics` (Prometheus text: request count and latency histogram by route, runs started/finished by template). Structured JSON logs to stdout. Rate limits return 429: 30 requests / 10 s per device token on `/api/*`, plus a loose 300 / 10 s per IP backstop (carrier NAT and school Wi-Fi share addresses). Behind a proxy the IP comes from the edge header named in `CLIENT_IP_HEADER`, never from client-writable `X-Forwarded-For`.
- `python -m app.seed`: today's three missions, one sponsored demo mission ("Sponsored by Demo Games"), ~200 demo runs flagged `is_demo`.
- Config only via env; commit `.env.example`, never `.env`.

## 6. Design

Read the arka-design skill first (Codex: `~/.codex/skills/arka-design/SKILL.md`) and follow it, including its verification loop.
Korean text uses the workspace default font stack (Malgun Gothic first, system fallbacks); do not bundle or embed web fonts.
Bold, playful but clean; big tap targets; timers and score feedback must read instantly on a phone.

## 7. Done criteria for M1

- `./run.sh` starts the app bound to 127.0.0.1 on a free port in 8900–8999 (check with `ss -ltn`).
- `pytest -q` passes, covering at least: ㄹ detection incl. compound finals; word validation and reuse; server-side timing with a patched clock; ore board determinism and scoring; telepathy majority incl. ties and close-job idempotency; attempt cap; rate limit 429; casting age gate and 30-day purge; studio auth and login rate limit; sponsored label present on sponsored mission pages; i18n key parity.
- Playwright screenshots at 390 px and 1280 px of home, each mission (start, mid-run, result), leaderboard, casting, studio, sponsor report → `_workspace/shots/`.
- `README.md` (English): what it is, run, test, env vars, guardrails, what was built during the hackathon (all of it: started Nov 6, 2026).
- No secrets, no personal data, no third-party IP in the repo.

Out of scope for M1: deployment, Render Workflows SDK wiring, CI, load tests, payments, GitHub push.

## 8. M2 — Render deployment and load-test readiness (added 2026-11-06)

Goal: the same code runs locally and on Render, survives a creator-driven spike ("thousands arrive at once" is the DevOps bonus criterion), and proves it with measured numbers.
There is **no Render account and no GitHub repo yet**. Everything here must be built and verified locally; the real deploy happens after the owner creates the workspace. No pushes, no Render/GitHub API calls, no accounts, no payments.

### 8.1 Throughput (do first; the load test measures it)
Today every answer, dig and mission-detail request takes `FOR UPDATE` on the mission row, so one mission's players are served one at a time on PostgreSQL.
- answer / dig: mission `FOR SHARE` (`with_for_update(read=True)`), then run `FOR UPDATE`. The close job keeps mission `FOR UPDATE`, so it waits for in-flight answers and no vote lands after the final count. Answers after `ends_at` already time out in `engine.answer`.
- Votes: atomic upsert `INSERT … ON CONFLICT (mission_id, question, option) DO UPDATE SET count = count + 1` (SQLAlchemy SQLite/PostgreSQL dialect inserts).
- Start: no mission lock. Keep the 3-attempt cap exact with a unique `(token, mission_id, attempt_no)` constraint; on conflict retry with the next number; `attempt_cap` after 3.
- Casting: unique `(token, week)` on applications instead of the mission lock; conflict → 409 `already_applied`.
- `GET /api/missions/{id}`: no exclusive lock and no unlocked writes (compute the timeout view in memory, or lock the run rows it changes).
- Leaderboard: compute once per mission per TTL (2–5 s) into one shared cache entry (top 100 plus `{sha256(token): [rank, score]}`) and answer "mine" from it. No per-user recomputation.
- DB pool from env `DB_POOL_SIZE` (default 5) and `DB_MAX_OVERFLOW` (default 5); total PostgreSQL connections across all instances stay under 100.
- `rotate_daily_missions` and `close_due_missions` must be safe when several instances run them at the same moment (insert-on-conflict-do-nothing; no errors logged).

### 8.2 Runtime configuration
- `serve.py`: when `PORT` is set, bind `0.0.0.0:$PORT` (Render default 10000). Otherwise keep the local 127.0.0.1 / 8900–8999 behaviour.
- `RATE_LIMIT_IP` (requests per 10 s per IP, default 300). A single-machine load generator needs a temporary higher value; the per-device limit (30 / 10 s) stays fixed. A test still proves the IP limiter.
- `METRICS_TOKEN`: when set, `/metrics` requires `Authorization: Bearer <token>`.
- `SEED_DEMO=true`: idempotent demo seed during pre-deploy; demo rows keep their visible labels.
- Schema: `python -m app.db init` (create tables, then optional seed) runs as Render `preDeployCommand`, so instances never race on DDL. Mark with `ponytail:` that Alembic comes with the first post-launch schema change.

### 8.3 Render
- One `Dockerfile` for local and Render (`runtime: docker`): Python 3.12 slim, non-root user, one uvicorn worker per instance (scale by instances).
- `render.yaml` Blueprint, region `singapore` for every resource (closest to Korean viewers), validated against `https://render.com/schema/render.yaml.json`:
  - web: plan `0.5c-512mb`, `healthCheckPath: /healthz`, `autoDeployTrigger: checksPass`, `preDeployCommand`, env `DATABASE_URL` (fromDatabase, connectionString), `REDIS_URL` (fromService type keyvalue, connectionString), `SESSION_SECRET` (`generateValue: true`), `STUDIO_PASSWORD_HASH` and `METRICS_TOKEN` (`sync: false`), `COOKIE_SECURE=true`, `CLIENT_IP_HEADER=True-Client-IP` (never `FORWARDED_ALLOW_IPS='*'`: Render only appends to `X-Forwarded-For`, so its left entry is client-written), `SEED_DEMO=true`. Autoscaling min 1 / max 3 / CPU 70 % needs a Pro workspace; document the `numInstances` fallback for Hobby.
  - Postgres: plan `0.1c-256mb`, `postgresMajorVersion: "18"`, `ipAllowList: []` (private network only).
  - Key Value: plan `256mb`, `ipAllowList: []`.
- **Render Workflows** — the organisers' perk email (2026-10-23) says projects using Render Workflows are eligible for the special Render awards ($500 / $300 / $100 credits). Read the official docs (`https://render.com/docs/workflows` and the Python SDK) and expose the four `app/jobs.py` functions as Workflow tasks, plus the documented way to run them on a schedule. Locally, and whenever no workflow is configured, the in-app 30 s loop keeps running; jobs stay idempotent so both can coexist. List anything that can only be verified on a real workspace (region support, plan requirements, triggering).

### 8.4 CI/CD
- `.github/workflows/ci.yml`: pytest on SQLite, then pytest against PostgreSQL 18 and Valkey service containers. Render deploys only after checks pass (`checksPass`). Rollback = Render "Rollback" to the previous deploy; document the steps.

### 8.5 Local production-like stack and tests
- `compose.yaml` (project name `open-casting`): app from the Dockerfile with `cpus: 0.5` and `mem_limit: 512m` (same as `0.5c-512mb`), `postgres:18-alpine`, `valkey/valkey:8-alpine`. Only the app is published, on 127.0.0.1 and a free port in 8900–8999. Never touch other containers on this machine.
- The pytest fixture uses `TEST_DATABASE_URL` / `TEST_REDIS_URL` when set. On PostgreSQL add concurrency tests: 10 concurrent starts on one device → exactly 3 succeed; 50 concurrent votes counted exactly; closing while answers are in flight is idempotent and final; two concurrent close jobs and two concurrent rotations do not error.

### 8.6 Load test
- `loadtest/spike.js` (k6, run with the `grafana/k6` image on the compose network). Each virtual user has its own cookie jar (= own device): home → missions → start a random template → play with 1–3 s think time (valid non-ㄹ words for no-rieul, random options, random digs) → leaderboard; 10 % also open `/casting`.
- Step test against ONE app container at 0.5 CPU: 50 → 100 → 200 → 400 → 800 VUs, 45 s per step. Record per step: req/s, p50 / p95 / p99, error rate (5xx, timeouts, unexpected 429). Report the knee (first step with p95 > 500 ms or errors > 1 %).
- Machine safety: this host runs live market-data collectors. Cap k6 at `--cpus 2`, keep each run ≤ 5 min, record `uptime` before and after, and stop only the `open-casting` compose project at the end.
- Results → `_workspace/load/<timestamp>/` (k6 summary JSON) and a table in `docs/OPERATIONS.md`. If practical, run once before and once after §8.1 so the document shows the gain.

### 8.7 `docs/OPERATIONS.md` (English, for judges)
Architecture (text diagram), scaling, CI/CD, monitoring (healthz, metrics, JSON logs, Render alerts), resilience (rate limits, caching, load numbers, rollback), maintenance (backups, patches, on-call), monthly cost at idle and at spike. Mark Render-only numbers as TODO.

### 8.8 Free-plan deployment (owner decision 2026-11-06)
The owner dropped the optional Best Use of Render track (it requires Workflows, which has no free plan) and deploys on Render's free instances only, with no card on file. This overrides the plans in §8.3 until the owner approves paid instances:
- web, Postgres and Key Value use plan `free`; no `scaling` (free web services run one instance); no workflow service in the Blueprint (`app/workflows.py` stays in the repo, unprovisioned).
- Free web services have no `preDeployCommand`, so `dockerCommand` runs `python -m app.db init` and then `app.serve`. With one instance there is no DDL race. Restore `preDeployCommand` with the first paid plan.
- Free limits to state in OPERATIONS: spin-down after 15 idle minutes (about a minute to wake), free Postgres expires 30 days after creation (14-day grace, then deleted), Key Value is in-memory only, outbound bandwidth over the included amount suspends the services without a card.
- Upgrade path: switch the three plans back to §8.3 values, then restore `preDeployCommand` and scaling (autoscaling needs a Pro workspace).

### 8.9 Done criteria for M2 (local)
- `pytest -q` passes on SQLite and on PostgreSQL + Valkey, including the new concurrency tests.
- `docker compose up` → `/healthz` returns `{"ok": true, "cache": "redis"}`.
- `render.yaml` is schema-valid; the Dockerfile builds.
- Local step-test table with the knee, in `docs/OPERATIONS.md`.
- README updated (deploy, env vars, load test). No secrets, no personal data in the repo.
