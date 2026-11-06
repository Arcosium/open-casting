# Operating Open Casting

This is a local deployment rehearsal, dated 2026-11-06. No Render workspace, GitHub repository, public deployment or paid resource was created.

## Architecture and consistency

```text
Browser -> Render web instances (1 to 3, one uvicorn worker each)
           |-> PostgreSQL 18: runs, votes, casting contacts, short links
           |-> Key Value / Valkey: rate limits and 3-second shared leaderboards
           |-> JSON stdout + authenticated Prometheus /metrics
Render Workflows -> the same four idempotent SQL jobs
Web instances -> 30-second maintenance fallback
```

An answer takes a shared mission lock, followed by an exclusive run lock. Other players can answer concurrently. Closing takes an exclusive mission lock, waits for in-flight answers, and calculates final scores once. Each vote is an atomic SQL upsert. Unique constraints enforce three attempts per device and mission and one casting application per device and week. Mission detail computes timeout views without writing. A shared cache stores one leaderboard per mission, including SHA-256 keyed personal ranks; the API only returns the caller's personal row. Cache population is locked across instances to avoid stampedes.

PostgreSQL pools default to 5 connections plus 5 overflow connections per web instance. Three instances therefore use at most 30 steady-state connections, or 60 while a full replacement overlaps. Workflow processes use 1 connection with no overflow. Reserve capacity for maintenance and administrative access; keep simultaneous workflow runs below 10 and the total below 100. Verify the actual database plan's connection limit before deployment. The fallback loop uses the web pool, not an extra engine.

## Local rehearsal

```bash
python3 scripts/local_stack.py
docker compose --env-file _workspace/compose.env -p open-casting up -d --build
# APP_PORT is printed/recorded in the private env file; default is 8900.
curl http://127.0.0.1:8900/healthz
python -m pytest -q
./scripts/test_stack.sh
python scripts/validate_blueprint.py
```

The helper creates synthetic local credentials in private runtime storage and a Git-ignored symlink. It never reads existing production credentials. Only the app port is published, bound to localhost. PostgreSQL and Valkey remain on the project network. The app is limited to 0.5 CPU and 512 MB RAM; PostgreSQL to 1 CPU/512 MB and Valkey to 0.5 CPU/256 MB. `docker compose -p open-casting down` stops only this project. Keep its volume unless intentionally resetting this synthetic rehearsal database. Never use a global prune or stop other containers.

`python -m app.db init` owns schema creation and optional demo seeding. Web and workflow processes never create tables at startup. The initializer upgrades the pre-launch M1 attempt table in place, preserves rows, and adds a unique attempt index. Back up before upgrading an M1 database. Future post-launch schema changes require Alembic and backward-compatible migrations. Render pre-deploy commands and local Compose initialization run before the web process. Demo rows remain visibly labeled.

## Render deployment and rollback

The schema-validated `render.yaml` provisions a Docker web service, PostgreSQL 18 and Key Value, all on Render's **free** instances in Singapore, with no card on file. Workflows has no free plan, so the Blueprint does not provision one. The Docker image runs as UID 10001. One worker runs per instance. PostgreSQL and Key Value have empty public IP allow lists.

After repository publication and account setup are separately approved:

1. Connect the approved repository to a Blueprint. Supply the scrypt `STUDIO_PASSWORD_HASH` and `METRICS_TOKEN` through Render's secret inputs. Never paste them into YAML or logs. Share the generated `SESSION_SECRET` across web instances.
2. Free web services run one instance and have no pre-deploy step, so `dockerCommand` runs `python -m app.db init` before `app.serve`.
3. Verify both GitHub jobs are required/passing and that `checksPass` gates deployment; this behavior cannot be tested without a connected repository.
4. Confirm the init step finishes in the deploy log, `/healthz` reports `ok: true, cache: redis`, the sponsor labels remain visible and authenticated metrics are scraped.
5. To roll back: open the web service's Events/Deploys page, choose the last known good deploy, select Rollback, confirm, then check health, a mission and studio access. A code rollback does not undo SQL changes. Restore a database backup only through a reviewed recovery procedure.

Free-plan limits (official [free instance docs](https://render.com/docs/free), checked 2026-11-06):

- The web service spins down after 15 minutes without traffic and takes about a minute to wake; open the demo URL once before a judge or creator does.
- Free PostgreSQL expires 30 days after creation, then has a 14-day grace period before Render deletes it. It has no backups. Recreate it (or upgrade it) before expiry; `SEED_DEMO` reseeds the demo rows on the next start.
- Free Key Value is in-memory only. A restart clears cached leaderboards and rate-limit counters, which rebuild on demand.
- Without a card, exceeding the included outbound bandwidth suspends the services for the rest of the month, and exceeding pipeline minutes pauses new builds.

Paid upgrade path: set the web plan to `0.5c-512mb`, PostgreSQL to `0.1c-256mb` and Key Value to `256mb`; replace `dockerCommand` with `preDeployCommand: python -m app.db init`; add CPU autoscaling (70%, min 1/max 3, Pro workspace only) or a budgeted `numInstances`; then add the workflow service and the cron trigger below.

## Render Workflows

Not deployed on the free plan. The code is ready for a paid setup. Official sources checked on 2026-11-06: [introduction](https://render.com/docs/workflows), [Python SDK](https://render.com/docs/workflows-sdk-python), [task definitions](https://render.com/docs/workflows-defining-tasks), [triggering runs](https://render.com/docs/workflows-running), and [limits and pricing](https://render.com/docs/workflows-limits).

`python -m app.workflows` registers `rotate_daily_missions`, `close_due_missions`, `purge_expired_applications`, and `build_sponsor_report` with Render SDK 1.7.0. Each task has a 300-second attempt timeout, up to three retries, and the `flex` compute plan. Only dates, timestamps, mission IDs, aggregate reports and counts enter/leave tasks. Casting contact data is never a task input or result. Local tests call the same registered functions with a synthetic SQL database; no Render API call is made.

Workflows currently has no native scheduling. The documented approach is a Render Cron service that triggers task runs. Once the account exists, set its build command to `pip install -r requirements.txt`, start command to `python -m app.trigger_workflows maintenance`, and schedule to `*/30 * * * *` (UTC). Set private `RENDER_API_KEY` and `RENDER_WORKFLOW_SLUG` on that service. This starts three short tasks every 30 minutes. The in-app 30-second loop already does the same work, so a faster cadence only adds cost: workflow runs are billed per second on the `flex` plan. Check the first day's run cost in the dashboard before keeping the cron enabled. The daily rotation is idempotent and uses Asia/Seoul. Sponsor reports are triggered on demand with `python -m app.trigger_workflows build_sponsor_report <mission-id>`. The cron service is deliberately not provisioned by the main Blueprint until workflow registration and its slug are verified. No host cron or recurring ArcAI task was installed.

The in-app 30-second loop remains enabled whether or not Workflows is configured. Concurrent rotation uses conflict-ignore inserts; closing and contact deletion are safe to repeat. This keeps maintenance working if task registration, the API or scheduling fails.

Render-only checklist: confirm Singapore availability for Workflows and private database connectivity; validate account/plan/credit eligibility; confirm task registration and the workflow slug, cron authorization and UTC triggering, retries and dashboard run history; set a practical run-concurrency budget; prove CPU autoscaling and a rollback. Verify the client-IP header before any load test: with `RATE_LIMIT_IP=3` and fresh cookies, four requests carrying forged `True-Client-IP` and `X-Forwarded-For` values must end in a 429 (forgery ignored), while requests from a second real network still succeed (no single shared bucket). If `True-Client-IP` is absent or forgeable, stop and choose another source before raising traffic. Workflows cannot reach private services inside a network-isolated environment, according to the official limitations. Do not enable that isolation without rechecking connectivity.

## CI/CD and monitoring

GitHub Actions runs SQLite tests and Blueprint schema validation plus a Docker build, followed by tests against PostgreSQL 18 and Valkey 8 services. PostgreSQL tests use a new random schema per fixture, and Redis keys get a random namespace. They never drop a production database or flush a shared cache. No CI service is published or run on this server.

`/healthz` checks SQL and cache, returning HTTP 503 on failure. `/metrics` reports request count/latency by normalized route and run counts by template. Configure `METRICS_TOKEN` to require a Bearer header. JSON request logs contain route, method, status and duration, with no submitted answers, casting contacts, cookies or passwords. Configure Render health/deploy alerts and external p95, 5xx, 429, SQL-connection and memory alerts after the workspace is connected.

Per-device limits stay at 30 API requests/10 seconds; `RATE_LIMIT_IP` defaults to a loose 300/10 seconds for shared networks. IP limits never read `X-Forwarded-For`: Render only appends to it, so its left entry is client-written, and `FORWARDED_ALLOW_IPS='*'` would let any client pick its own rate-limit key. On Render the IP comes from `CLIENT_IP_HEADER=True-Client-IP`, set by Cloudflare in front of Render. Local Compose uses the socket peer. Redis failure makes health fail and API calls fail rather than silently applying independent limits on each instance. Maintain Redis memory headroom because rate-limit keys and cache data share the store.

## Load experiment

The workload runs 50, 100, 200, 400 and 800 VUs for 45 seconds each against one app container. Journeys include home, mission list, a random game, 1-3 second think time, leaderboard, and casting for 10% of journeys. k6's default per-iteration cookie reset represents a new arriving viewer each journey while keeping a private per-VU cookie jar throughout the game. No-rieul answers are valid words without ㄹ. Ore cells never repeat. Each stage ends immediately, so unfinished games are interrupted at its boundary. This is a 225-second HTML/API experiment; k6 does not fetch CSS/JS assets or execute browser JavaScript. It is not a completion-rate estimate or a claim of Render capacity.

Both comparison runs use the same direct uvicorn command with request/access logging disabled, to avoid measuring different launchers. The default Compose/Render runtime retains JSON request logging and is checked separately. This difference from normal operation may improve the measured capacity.

Raise `RATE_LIMIT_IP` only on this isolated stack before the test (the device limiter is unchanged):

```bash
RATE_LIMIT_IP=1000000 docker compose --env-file _workspace/compose.env -p open-casting -f compose.yaml -f loadtest/runtime.yaml up -d app
./loadtest/run.sh after
```

The launcher applies Docker `--cpus 2 --memory 512m` to k6 and records host `uptime` before and after. Every run lasts under five minutes. Raw summaries and logs live under `_workspace/load/<timestamp>-<label>/`. Per-stage request rate is the stage request count divided by 45 seconds, including failed/timed-out requests; a high rate at 100% errors is not useful throughput. Errors count all unexpected HTTP statuses, including 5xx, timeout/status 0 and unexpected 429. The knee is the first stage where p95 exceeds 500 ms or errors exceed 1%.

### Before (20261106-094125-before)

| VUs | req/s | p50 ms | p95 ms | p99 ms | errors % |
|---:|---:|---:|---:|---:|---:|
| 50 | 32.00 | 13.67 | 590.44 | 890.08 | 0.00 |
| 100 | 57.51 | 111.87 | 1252.41 | 1594.58 | 0.00 |
| 200 | 54.87 | 2380.86 | 3857.39 | 4189.65 | 0.00 |
| 400 | 84.84 | 4403.45 | 5000.99 | 5001.35 | 32.87 |
| 800 | 142.22 | 5000.09 | 5002.59 | 5080.10 | 100.00 |

Host load (uptime, before / after):
```text
09:41:25 up 25 days, 19:26,  1 user,  load average: 25.53, 27.23, 21.46
09:45:12 up 25 days, 19:30,  1 user,  load average: 20.04, 25.41, 22.07
```

### After (20261106-094621-after)

| VUs | req/s | p50 ms | p95 ms | p99 ms | errors % |
|---:|---:|---:|---:|---:|---:|
| 50 | 32.67 | 10.79 | 515.89 | 696.63 | 0.00 |
| 100 | 60.38 | 14.20 | 801.31 | 915.88 | 0.00 |
| 200 | 75.33 | 1186.87 | 2390.26 | 2967.12 | 0.00 |
| 400 | 90.00 | 3813.23 | 5000.95 | 5001.30 | 25.53 |
| 800 | 145.20 | 5000.26 | 5001.10 | 5001.51 | 80.06 |

Host load (uptime, before / after):
```text
09:46:21 up 25 days, 19:31,  1 user,  load average: 14.84, 22.75, 21.39
09:50:09 up 25 days, 19:35,  1 user,  load average: 10.96, 16.44, 19.11
```

Both runs first crossed the p95 threshold at 50 VUs (590.44 ms before, 515.89 ms after). At 100 VUs, observed p95 fell from 1252.41 to 801.31 ms; at 200 VUs, observed request rate rose from 54.87 to 75.33/s. The host load also fell between runs, so these differences cannot be attributed entirely to the code. Neither run meets the 500 ms target at the lowest tested concurrency. A single 0.5-CPU instance has not demonstrated support for thousands of simultaneous viewers. Real Render scaling and a production-capacity test remain TODO. k6 exit 99 in each run records threshold failures, not a completed capacity pass. The baseline used the prior SQLAlchemy default pool (5 + 10 overflow); M2 uses the required 5 + 5.

Restore `RATE_LIMIT_IP=300` after a rehearsal and stop only the `open-casting` project. This host also runs live market-data collectors; host load and network conditions confound any before/after comparison. A measured improvement here must not be presented as guaranteed production scaling.

## Maintenance and cost

Enable managed PostgreSQL backups/PITR as supported by the chosen plan and test restores into a separate database. Contacts are deleted after 30 days by both maintenance and studio access safeguards; restored backups must run the purge before being exposed. Keep backups and exports private, restrict studio access and rotate its password/session key on compromise. Review base image and dependency security updates monthly, stage upgrades in this same test stack, run both test backends and a short smoke test, then deploy. The solo owner is on call; production launch needs an alert destination and documented backup operator.

Current deployment: all three services on free instances, $0/month. The $50 participant credit stays unused until paid instances are approved. Paid prices below are from the official [pricing page](https://render.com/pricing) on 2026-11-06, prorated by the second:

| Component | Idle/month | Spike/month or usage |
|---|---:|---:|
| Web: free (current) / 0.5c-512mb | $0 / $7 | free: one instance only; paid: $7 per instance-month for 1-3 instances |
| PostgreSQL: free (current) / 0.1c-256mb | $0 / $6 + $0.30 per GB storage | same |
| Key Value: free (current, 25 MB) / 256mb | $0 / $10 | same |
| Workspace Pro, scheduling service, bandwidth | TODO | TODO |
| Workflows flex | Usage based | $0.20/CPU-hour + $0.05/GB-hour, plus state retention |
| Total | TODO | TODO |

The official workflow pricing page lists state retention at $0.25/GB, retained for 30 days. Actual monthly usage and any credits remain TODO until verified in the real workspace. Never equate a credit award with permanently free hosting.
