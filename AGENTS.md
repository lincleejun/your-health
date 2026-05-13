# Agent Harness — hard rules

This file is loaded by every Ralph loop iteration. **These are constraints, not suggestions.** If you cannot satisfy them, STOP and write the blocker into `SPEC.md` under `## Blockers`.

## 1. Workflow per iteration

Each iteration does **exactly one** unchecked task from `SPEC.md`. Order:

1. Read `SPEC.md`. Find the first unchecked `- [ ]` item under `## Tasks`.
2. **TDD** — write a failing test in `tests/` first. Run `uv run pytest -x` and confirm it fails for the expected reason.
3. Implement the minimum code in `src/health/` to make the test pass.
4. Run the **verify gate** (section 2). All four commands must exit 0.
5. Update `SPEC.md`: flip the `[ ]` to `[x]`. Add one-line note if the implementation diverged from the spec.
6. Commit with a conventional message (section 3).
7. Print `RALPH_DONE_ITERATION` on the last line of your output so the loop runner can parse it.

If `SPEC.md` has no unchecked items, print `RALPH_ALL_DONE` and exit.

## 2. Verify gate — MANDATORY before every commit

Run these four commands in order. If any one fails, **fix the code, not the test, and do not commit until all pass**:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Never bypass:
- No `# type: ignore` without a `# reason:` comment naming the upstream issue.
- No `# noqa` without a specific rule code and a reason.
- No `--no-verify` on commits.
- No skipping a test (`pytest.skip`) without a `# blocker:` link to a SPEC.md Blocker entry.

If the gate has been failing for **2 iterations in a row** on the same task, STOP. Write the blocker to `SPEC.md` and exit with `RALPH_BLOCKED`.

## 3. Commits

- One iteration = one commit. No batched commits.
- Conventional commit format: `<type>(<scope>): <subject>` where:
  - `type` ∈ {`feat`, `fix`, `test`, `refactor`, `docs`, `chore`}
  - `scope` ∈ {`ingest`, `db`, `metrics`, `report`, `plan`, `cli`, `coach`, `harness`}
- Subject in imperative, ≤ 60 chars, no period.
- Body (optional): why, not what.
- **Never** amend commits across iterations.
- **Never** force-push.

## 4. Code rules

- Python 3.11+, type-annotate every public function.
- Files in `src/health/` ≤ 200 LOC. If a file grows past that, split it before adding more.
- No `print()` in library code; use the `logging` module. CLI may use `rich`.
- All time is `datetime` with explicit timezone or `date`. Never naive datetimes.
- All DB writes go through `src/health/db/conn.py`. No ad-hoc `sqlite3.connect()` elsewhere.
- Garmin API responses are validated through Pydantic models before hitting the DB.

## 5. Tests

- `tests/` mirrors `src/health/` structure.
- Every module needs at least one test that exercises the happy path with a fixture (no live Garmin calls in tests — mock the client).
- Place Garmin response fixtures under `tests/fixtures/garmin/` as JSON files.
- DB tests use an in-memory SQLite (`:memory:`).

## 6. Out of scope (do not build until SPEC.md adds them)

- Apple Health import
- HTML reports
- LLM coach module (`src/health/coach/`)
- Web UI of any kind
- Multi-user / auth

## 7. Reference repos (do not copy code — read for inspiration only)

- `leonzzz435/garmin-ai-coach` — KPI taxonomy, three-layer (metrics / physiology / activity) analysis structure, plan.yaml shape. See `CLAUDE.md` (local, gitignored) for notes.
- `cyberjunky/python-garminconnect` — Garmin SDK. Use the published `garminconnect` PyPI package; do not vendor.

## 8. When in doubt

Ask the user via a `## Questions` block in `SPEC.md` and exit `RALPH_BLOCKED`. Do not guess on product behavior.
