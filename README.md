# your-health

A personal health-data analysis toolkit built around the data Garmin already
collects for you. Pulls your Garmin Connect data into a local SQLite database,
turns it into training-load and physiology KPIs, and (eventually) feeds the
result to an LLM "coach" for personalised analysis and plan adjustments.

> **Status — early.** The data-ingestion and metrics layers work end-to-end
> against the Garmin Connect API. Markdown reporting, plan-adherence scoring,
> and the LLM-coach layer are next. Roadmap below.

## What works today

- **Ingest** — `health ingest --days N` pulls daily summary, sleep, HRV,
  body composition, and activities from Garmin Connect into a local SQLite
  database. OAuth tokens are cached locally, so subsequent runs don't hit
  the credential-login endpoint (which is heavily rate-limited).
- **Metrics** — three independent layers computed from the local DB:
  - **Load** — daily training load, 42-day chronic load (CTL), 7-day acute
    load (ATL), and acute-to-chronic ratio (ACWR).
  - **Physiology** — 7-day and 28-day trends for resting HR, HRV, and sleep
    duration, with z-score-based anomaly flagging.
  - **Activity** — ISO-week volume by sport, and HR-zone time-in-zone using
    Karvonen zones derived from your max / resting HR.

## Roadmap

- [ ] Markdown daily + weekly reports rendered from the metrics layer.
- [ ] `plan.yaml`-driven adherence scoring (compare planned vs actual).
- [ ] LLM-coach layer: feed the structured KPIs + adherence to a large
      language model to generate personalised analysis and next-week plan
      adjustments. The whole pipeline is shaped to make this step a simple
      bolt-on once the deterministic layers are stable.
- [ ] Optional: Apple Health import (later — needs a different ingestion path).

## Quick start

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/lincleejun/your-health.git
cd your-health
uv sync

# Garmin credentials — config/.env is gitignored.
cp .env.example config/.env
$EDITOR config/.env

uv run health ingest --days 30
sqlite3 data/health.db "SELECT date, total_sleep_s, sleep_score FROM sleep ORDER BY date DESC LIMIT 7;"
```

The first ingest run logs in with your password and persists OAuth tokens
under `config/.garmin_tokens/`. Every later run resumes from those tokens,
so you only pay the credential-login cost once.

If you hit `HTTP 429` ("Mobile login returned 429 — IP rate limited"),
Garmin has throttled your IP. Wait 15–60 minutes and retry; once a single
successful login is cached, you won't see it again.

## How it's built

This project is built with a [Ralph loop](https://ghuntley.com/ralph/):

- `SPEC.md` is the task checklist — each item is one TDD iteration.
- `AGENTS.md` is the hard agent harness — TDD, full verify gate
  (ruff + ruff-format + mypy + pytest) before every commit, conventional
  commit messages, no skipping hooks.
- `PROMPT.md` is the per-iteration brief the loop pipes to Claude Code.
- `ralph.sh` is the runner. Worktree-based parallel execution is used for
  independent modules.

## Layout

```
src/health/
  ingest/       Garmin Connect → SQLite (idempotent UPSERTs)
  db/           Schema + connection helper
  metrics/      load / physiology / activity (deterministic KPIs)
  cli.py        Typer entrypoint
```

## Privacy

Everything stays on your machine. The CLI talks to Garmin Connect directly
and writes to a local SQLite file. There is no first-party backend, and
nothing is uploaded anywhere by this tool. When the LLM-coach layer lands,
it will be an opt-in step that calls whichever provider you configure with
your own API key.

## Credits & acknowledgements

This project depends on:

- **[Garmin Connect](https://connect.garmin.com)** — the source of all
  health and activity data. This project is **not affiliated with, endorsed
  by, or supported by Garmin Ltd.** "Garmin" and "Garmin Connect" are
  trademarks of Garmin Ltd. or its subsidiaries. All data accessed through
  this tool remains subject to Garmin's
  [Terms of Use](https://www.garmin.com/en-US/legal/garmin-connect-terms-of-use/).
- **[python-garminconnect](https://github.com/cyberjunky/python-garminconnect)**
  by `cyberjunky` — the unofficial Python SDK that this project uses to
  authenticate with Garmin Connect and fetch wellness payloads. MIT-licensed.
- **[garmin-ai-coach](https://github.com/leonzzz435/garmin-ai-coach)** by
  `leonzzz435` — reference for KPI taxonomy (CTL / ATL / ACWR, HRV trends)
  and for the broader idea of feeding Garmin data into an LLM coach. No code
  copied; structural inspiration only.

## Not medical advice

This is a personal tool for self-quantification. Nothing it produces is
medical, training, or nutrition advice. If a metric flags an anomaly, treat
it as a curiosity, not a diagnosis.

## License

[MIT](./LICENSE) © 2026 lincleejun
