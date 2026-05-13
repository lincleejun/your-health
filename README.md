# health

Personal health data analysis. Pulls Garmin Connect data into a local SQLite database, computes training-load and physiology KPIs, generates daily and weekly Markdown reports, and scores adherence to a YAML-defined fitness plan.

Built with a [Ralph loop](https://ghuntley.com/ralph/) — see `AGENTS.md` for the agent harness rules and `SPEC.md` for the task checklist.

## Quick start

```bash
uv sync
cp .env.example config/.env       # fill in Garmin credentials
cp config/plan.example.yaml config/plan.yaml
uv run health ingest --days 7
uv run health report weekly
```

## Commands

| Command | What it does |
|---|---|
| `health ingest --days N` | Pull the last N days from Garmin Connect (idempotent). |
| `health report daily --date YYYY-MM-DD` | One-day Markdown report under `data/reports/`. |
| `health report weekly --week YYYY-Www` | Weekly KPI + trend + adherence report. |
| `health plan check --week YYYY-Www` | Plan adherence score only. |

Reports are plain Markdown so they pipe nicely into an LLM, Telegram, or email.

## Scheduling

This project does not schedule itself. Wire `health ingest` and `health report` into `cron` / `launchd` / Actions however you like.

## Layout

```
src/health/
  ingest/   Garmin → SQLite (idempotent UPSERTs)
  db/       Schema + connection helper
  metrics/  CTL / ATL / ACWR / HRV / RHR / zone distribution
  report/   Markdown rendering
  plan/     plan.yaml loader + adherence scoring
  cli.py    Typer entrypoint
```

## Not in scope (yet)

Apple Health import, HTML reports, LLM-generated coaching, web UI. See `AGENTS.md` §6.

## License

MIT
