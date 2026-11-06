# Open Casting

A free browser mission platform that connects viewers with future on-camera casting. Play three short challenges, compare records, and apply after finishing any mission this week. The creator chooses the cast; rank never guarantees selection.

Everything in this implementation was built during the hackathon, starting **November 6, 2026**. The product source of truth is [docs/SPEC.md](docs/SPEC.md).

## Run locally

Requires Python 3.12 and a browser. No frontend build step.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
SEED_DEMO=true .venv/bin/python -m app.db init  # optional: labeled synthetic rows
./run.sh
```

When `PORT` is absent, `run.sh` reserves a free socket between **8900 and 8999** and serves only on **127.0.0.1**. The chosen URL is printed as JSON. It creates a virtual environment if absent. Stop with Ctrl+C; do not kill other services. If all ports are occupied it exits without disturbing them.

Local runtime data and the session key live under `~/vault/runtime/open-casting/`, referenced by the git-ignored `data` symlink. Set `OPEN_CASTING_RUNTIME_DIR` before first run to choose a different private directory. For environment configuration, keep the actual `.env` in private storage and link it into the project. Never commit it.

Generate a studio password hash interactively:

```sh
.venv/bin/python -m app.security hash-password
```

Set the returned hash as `STUDIO_PASSWORD_HASH` in the private environment file and start your local app. There is no default password. A missing password disables login with a clear message. Studio sessions expire after eight hours, and changing the password hash invalidates old sessions.

## Configuration

| Variable | Default / purpose |
|---|---|
| `DATABASE_URL` | `sqlite:///data/open-casting.sqlite`; PostgreSQL URLs use psycopg |
| `REDIS_URL` | Empty: process-local cache and limits; set for a Redis cache |
| `STUDIO_PASSWORD_HASH` | Empty: studio login disabled; scrypt `salt:hex` hash |
| `SESSION_SECRET` | Locally generated private `data/session.key`; set a random 32+ character secret for other environments |
| `COOKIE_SECURE` | `false` for loopback HTTP; set `true` with HTTPS |
| `SPONSOR_CONTACT` | Public sponsor inquiry contact; if empty the page asks viewers to contact the creator |
| `OPEN_CASTING_RUNTIME_DIR` | Private runtime path used by `run.sh` when creating `data` |
| `FORWARDED_ALLOW_IPS` | Read by uvicorn; default `127.0.0.1`. Never `*` on a public host: uvicorn would then take the client-written left entry of `X-Forwarded-For` |
| `CLIENT_IP_HEADER` | Edge-set header used as the client IP for rate limits. Render: `True-Client-IP` (set by Cloudflare in front of Render; verify after deploy). Empty: the socket peer |

SQLite is supported locally, and M2 adds PostgreSQL 18 plus Valkey integration and concurrency tests. PostgreSQL answers take shared mission locks and exclusive run locks; votes use atomic upserts. Database constraints enforce attempt and casting limits. Shared three-second leaderboard snapshots avoid per-player recomputation. SQL is the durable authority; cache loss never loses game progress. Run one web worker per instance and scale instances instead.

Additional M2 configuration:

| Variable | Default / purpose |
|---|---|
| `PORT` | Unset: loopback scan; set: `0.0.0.0:$PORT` for containers/Render |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 5 / 5 PostgreSQL connections per web instance |
| `RATE_LIMIT_IP` | 300 requests/10 s; device limit remains 30/10 s |
| `METRICS_TOKEN` | Optional Bearer token required by `/metrics` |
| `SEED_DEMO` | `false`; `app.db init` seeds labeled demo rows when `true` |
| `RENDER_API_KEY` / `RENDER_WORKFLOW_SLUG` | Private credentials/identifier for the one-shot trigger only |

## Deployment rehearsal and load test

```sh
python3 scripts/local_stack.py
docker compose --env-file _workspace/compose.env -p open-casting up -d --build
./scripts/test_stack.sh  # isolated PostgreSQL schemas and Valkey test namespaces
.venv/bin/python scripts/validate_blueprint.py
RATE_LIMIT_IP=1000000 docker compose --env-file _workspace/compose.env -p open-casting -f compose.yaml -f loadtest/runtime.yaml up -d --build app
./loadtest/run.sh after  # 225 s, k6 limited to 2 CPUs
RATE_LIMIT_IP=300 docker compose --env-file _workspace/compose.env -p open-casting up -d app
docker compose --env-file _workspace/compose.env -p open-casting down
```

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for measured load results, the knee, Pro/Hobby Blueprint settings, workflow scheduling, monitoring, recovery and costs. `render.yaml` is validated against the official public JSON schema without making account API calls. Workflows require real-workspace registration before the trigger can be used. No deployment happens from these local checks.

## Features and routes

- `/`: today's three daily missions plus any active sponsored missions.
- `/missions/{id}`: Don't Say ㄹ (eight Korean categories), Mind Match (ten majority questions), or One-Minute Ore Hunt (10×10 grid, 25 digs).
- `/leaderboard`: top 100, your rank, and weekly sums of best records per mission. Synthetic seed rows and reports carry visible demo labels. Mind Match scores stay provisional until mission close. Ranking read projections may be up to three seconds old.
- `/casting`: finish at least one mission in the current ISO week (Korea time) to apply. Best records are attached automatically.
- `/studio`: password-protected applications, record/status filters, manual shortlist/invite/decline actions, safe CSV exports, mission statistics, sponsored builder and short links.
- `/studio/reports/{id}`: unique devices, runs, completion, average score/time, short-link visits and daily CSV. Completion includes failed/timed-out runs with a saved result. Average time/score use finished runs.
- `/v/{code}`: count a video-link visit and redirect to its mission.
- `/sponsor`, `/faq`: sponsor offering, report-field preview, contact information and guardrails.
- `/healthz`: database and cache status. `/metrics`: Prometheus request counts, latency histogram and run totals per template.

Korean is the default; the English toggle covers the full UI. All UI copy lives in equal-key dictionaries at `app/static/i18n/{ko,en}.json`. User-authored mission titles and Korean word-game answers are content and are not machine-translated.

Rules live in `app/engine.py`, independent of HTTP and persistence. Timing and score decisions use the server clock. The client draws timers and sends only answers or cell coordinates. A board is never returned before that run ends. Server-only random seeds prevent reconstructing the board from a public mission ID. Initial/final ㄹ and compound final consonants are detected after Unicode normalization.

M1 uses text input only. Browser speech recognition is optional in the spec and is intentionally omitted because default Web Speech implementations can send audio off-device. The app never asks for microphone access; response policy disables microphone and camera.

## Jobs

These functions have no request dependency and can be called repeatedly:

```sh
.venv/bin/python -m app.jobs rotate_daily_missions
.venv/bin/python -m app.jobs rotate_daily_missions 2026-11-06
.venv/bin/python -m app.jobs close_due_missions
.venv/bin/python -m app.jobs purge_expired_applications
.venv/bin/python -m app.jobs build_sponsor_report MISSION_ID
```

The running local app invokes rotation, closing and purging on startup and every 30 seconds. Expired application rows are also purged before studio listing/export. Final majority scores are recomputed exactly once per closed mission, with all tied choices qualifying. Do not set up an external scheduler for the local demo.

## Guardrails

- No money, goods, coupons, valuable rewards, payments, paid retries or paid random items. Three free attempts per device per mission instance; daily missions rotate at midnight in Korea.
- Ranking badges are display only. Any finished mission this week permits a casting application, even with zero points. Casting is the creator's manual decision, separate from recorded events.
- Every sponsored mission screen has a fixed **광고 · Sponsored by {name}** label, including its leaderboard and report.
- Play uses a signed anonymous device cookie and public nickname. Applications require age 만 14+; only the birth year is asked, so the year must make the applicant 15 this calendar year. Birth year is checked and never stored. Only email or Discord contact is accepted, with consent. Applications and contacts are deleted after 30 days (at most one maintenance interval later while running).
- Studio authentication uses scrypt, expiring signed HttpOnly SameSite cookies, login limits, same-origin JSON mutations, bounded inputs, sanitized images and formula-safe CSV. Contacts, passwords and answers are excluded from structured request logs and validation errors.
- Original CSS/SVG graphics only. No third-party game textures, logos, creator likenesses or voices. Uploaded logos must be owned by the studio user. No external analytics or web fonts.

The cookie is an anonymous device identity, not strong identity verification. Clearing cookies changes it; IP throttles still apply. Legal approval for public launch is not implied by this prototype.

## Check

```sh
pytest -q
.venv/bin/python scripts/capture.py
python3 ~/.codex/skills/arka-design/scripts/check.py http://127.0.0.1:PORT
```

The test suite covers consonants, category validation/reuse, server timing, deterministic ore boards/points/distance/dig caps, majority ties and close idempotence, atomic attempt caps, 429 limits, casting age/consent/retention, authentication/CSV/CSRF, ad labels, image validation, report/link counts, seed flags and translation parity. Tests use temporary databases and synthetic inputs only.

The browser script uses Playwright Chromium, real UI interactions and an isolated synthetic server with a random one-run studio password. It captures 390px/1280px home, all three missions at start/mid/result, leaderboards, casting, studio, builder, links, sponsored report, FAQ and English home. It checks layout with arka-design's checker and writes `_workspace/shots/` plus `_workspace/browser-results.json`. It closes its browser and its own server in `finally`.

M2 adds local deployment configuration, Render Workflows SDK wiring, CI and load tests. Public deployment, payments and GitHub push remain separate approval steps. See [docs/DESIGN.md](docs/DESIGN.md) for design choices and the verification loop.
