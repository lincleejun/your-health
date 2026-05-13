# SPEC — personal health data analysis

Source of truth for the Ralph loop. Each iteration picks the first unchecked `- [ ]` under `## Tasks`, builds it under the rules in `AGENTS.md`, then flips it to `- [x]`.

## Goal

Pull a year of Garmin Connect data into a local SQLite database, compute training-load + physiology KPIs, render daily / weekly Markdown reports, and score adherence to a YAML-defined fitness plan. CLI-first, no scheduler — external `cron` / `launchd` drives it.

## Non-goals (MVP)

Apple Health, HTML/Plotly reports, LLM coach, web UI, multi-user. See `AGENTS.md` §6.

## Architecture

```
src/health/
├── ingest/        Garmin Connect → SQLite (idempotent UPSERTs)
├── db/            SQLite schema + connection helper
├── metrics/       CTL / ATL / ACWR / HRV / RHR / zone distribution
├── report/        Daily + weekly Markdown renderers
├── plan/          plan.yaml loader + weekly adherence scoring
└── cli.py         Typer entrypoint
```

Data flow: `ingest` writes raw + lightly-normalised rows; `metrics` reads only from DB and emits derived series; `report` and `plan` consume DB + metrics. No module reaches across — `db` is the only shared dependency.

## Data model (target)

| Table | Grain | Key columns |
|---|---|---|
| `activities` | one row per workout | `activity_id` PK, `start_ts`, `sport`, `duration_s`, `distance_m`, `avg_hr`, `training_load`, `aerobic_te`, `anaerobic_te`, `raw_json` |
| `daily_summary` | one row per day | `date` PK, `steps`, `resting_hr`, `body_battery_min`, `body_battery_max`, `stress_avg`, `calories_active`, `raw_json` |
| `sleep` | one row per night | `date` PK, `total_sleep_s`, `deep_s`, `light_s`, `rem_s`, `awake_s`, `sleep_score`, `raw_json` |
| `hrv` | one row per day | `date` PK, `weekly_avg`, `last_night_avg`, `status`, `raw_json` |
| `body_composition` | one row per measurement day | `date` PK, `weight_kg`, `body_fat_pct`, `muscle_mass_kg`, `raw_json` |
| `ingest_runs` | one row per `health ingest` call | `id` PK, `started_at`, `finished_at`, `days_requested`, `rows_written`, `error` |

`raw_json` columns preserve the full Garmin response so we can re-derive new fields without re-pulling.

## Tasks

Order matters — earlier tasks unblock later ones.

### Foundation
- [x] **harness-01**: Add `tests/conftest.py` with an in-memory SQLite fixture (`db_conn`) and a fixtures dir under `tests/fixtures/garmin/`.
- [x] **db-01**: `src/health/db/schema.sql` covering all six tables above. Use `INTEGER PRIMARY KEY` for surrogate ids; store `raw_json` as `TEXT`. Add indices on `start_ts` (activities) and `date` columns.
- [x] **db-02**: `src/health/db/conn.py` exposing `connect(path: Path) -> sqlite3.Connection` (foreign keys on, row_factory=Row), `initialize(conn)` to run schema, and a `transaction(conn)` context manager.

### Ingest (priority — unblocks user testing)
- [x] **ingest-01**: `src/health/ingest/models.py` — Pydantic models for `Activity`, `DailySummary`, `Sleep`, `HrvDay`, `BodyComposition`. Each has a `from_garmin(payload: dict) -> Self` classmethod tolerant of missing fields.
- [x] **ingest-02**: `src/health/ingest/garmin.py` — thin wrapper around `garminconnect.Garmin`. Persists OAuth tokens to `GARMIN_TOKEN_DIR` so we don't re-login every run. Exposes `fetch_day(date)` returning a typed bundle and `fetch_activities(start, end)`.
- [x] **ingest-03**: `src/health/ingest/store.py` — UPSERT functions per table (`ON CONFLICT ... DO UPDATE`). Idempotent: re-ingesting the same date overwrites cleanly.
- [x] **ingest-04**: `src/health/ingest/runner.py` — `ingest_range(conn, client, start, end)` orchestrates per-day pulls, writes `ingest_runs` row, catches per-day errors so one bad day doesn't kill the run.
- [x] **cli-01**: `src/health/cli.py` — Typer app with `health ingest --days N [--start YYYY-MM-DD]`. Loads `.env`, opens DB (creates if missing), runs ingest, prints summary table via `rich`.
- [ ] **🛑 USER TEST GATE**: User runs `uv run health ingest --days 7` against their Garmin account and confirms data lands in `data/health.db`. **Loop must STOP and print `RALPH_USER_GATE` here.**

### Metrics (parallelisable after ingest)
- [x] **metrics-01**: `src/health/metrics/load.py` — CTL (42d EWMA), ATL (7d EWMA), ACWR (ATL/CTL). Input: `activities` rows. Output: dict keyed by date.
- [x] **metrics-02**: `src/health/metrics/physiology.py` — 7d/28d trends for RHR, HRV weekly_avg, sleep total. Flag anomalies (>1 SD from 28d mean).
- [x] **metrics-03**: `src/health/metrics/activity.py` — weekly mileage by sport, HR zone time-in-zone (uses athlete max/resting HR from `plan.yaml`).

### Report (parallelisable after metrics)
- [x] **report-01**: `src/health/report/render.py` — Markdown template helpers (KPI table, trend bullets, sparkline ASCII).
- [x] **report-02**: `src/health/report/daily.py` — one-day card: yesterday's activity, sleep, HRV, body battery, vs 7d mean.
- [x] **report-03**: `src/health/report/weekly.py` — KPI dashboard (load, physiology, activity), week-over-week trend, top anomalies.
- [x] **cli-02**: Add `health report daily` and `health report weekly` subcommands. Writes to `data/reports/{daily,weekly}/<date>.md`.

### Plan adherence (parallelisable after report)
- [x] **plan-01**: `src/health/plan/schema.py` — Pydantic model for `plan.yaml`.
- [x] **plan-02**: `src/health/plan/loader.py` — load + validate plan.
- [x] **plan-03**: `src/health/plan/adherence.py` — compare a week's activities/sleep/load against `weekly_targets`. Output a per-target score (0–100), an overall weighted score, and a list of misses with deltas.
- [x] **report-04**: Wire adherence into `health report weekly` (append a `## Plan Adherence` section).
- [x] **cli-03**: `health plan check --week YYYY-Www` standalone command.

### Polish
- [ ] **docs-01**: Refresh `README.md` with the actual CLI behaviour once it stabilises.
- [ ] **chore-01**: Add `Makefile` (or `justfile`) with `make verify` running the full verify gate.

## Questions

_(Loop appends here when blocked on product decisions. User answers, then loop resumes.)_

## Blockers

_(Loop appends here when the verify gate has been failing on the same task for ≥2 iterations.)_
