# Ralph loop prompt

You are working on this repository under a strict agent harness. **This prompt is the entire iteration brief — do not ask the user mid-iteration.** If you need a product decision, write it to `SPEC.md` under `## Questions` and exit with `RALPH_BLOCKED`.

## Step 0 — Load context

1. Read `AGENTS.md` end to end. Those rules override your defaults.
2. Read `SPEC.md` end to end. It is the source of truth.
3. Skim recent commits (`git log --oneline -20`) so you know what already shipped.

## Step 1 — Pick one task

Find the **first** unchecked `- [ ]` item under `## Tasks` in `SPEC.md`. That is your only job this iteration. Do not batch tasks.

Special tokens in SPEC.md:
- A line starting with `🛑 USER TEST GATE` means STOP. Print `RALPH_USER_GATE` and exit; the user runs a manual test before the next iteration.
- If `## Tasks` has no unchecked items, print `RALPH_ALL_DONE` and exit.

## Step 2 — TDD

1. Write a failing test under `tests/` first. Mirror the `src/health/` path.
2. Run `uv run pytest tests/<path>::<test_name> -x` and confirm it fails for the right reason (not import error, not collection error).
3. Implement the **minimum** code in `src/health/` to make the test pass.

## Step 3 — Verify gate (AGENTS.md §2)

Run all four, in order. They must all exit 0:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

If a command fails: fix the source code, not the test. Do not weaken the test to make it pass. Do not add `# type: ignore` / `# noqa` without a real reason.

If the same task has failed the gate twice in a row (check `git log`), STOP, write to `## Blockers` in SPEC.md, exit `RALPH_BLOCKED`.

## Step 4 — Update SPEC.md

Flip the `- [ ]` for the task you just completed to `- [x]`. If the implementation diverged from the spec, append a one-line `_(note: …)_` underneath.

## Step 5 — Commit

```bash
git add -A
git commit -m "<type>(<scope>): <subject>"
```

`type` ∈ {feat, fix, test, refactor, docs, chore}. `scope` matches the SPEC.md task prefix (`ingest`, `db`, `metrics`, `report`, `plan`, `cli`, `coach`, `harness`). Imperative subject, ≤ 60 chars, no trailing period.

Never `--amend`, never `--no-verify`, never force-push.

## Step 6 — Exit

Print one of these as the **last line** of your output:

- `RALPH_DONE_ITERATION` — task completed cleanly, loop can continue.
- `RALPH_USER_GATE` — hit a manual test gate, user action required.
- `RALPH_BLOCKED` — gate failed twice or a product question is pending.
- `RALPH_ALL_DONE` — no unchecked tasks remain.

## Rules of engagement

- **One task per iteration.** Don't get clever.
- **No scope creep.** If you spot a refactor opportunity, write it as a new SPEC.md task; don't do it now.
- **No new dependencies** unless the SPEC.md task explicitly requires it. Adding a dep is its own task.
- **Files > 200 LOC**: split before adding more code (AGENTS.md §4).
- **Never edit `AGENTS.md`** from inside the loop. The user owns that file.
- **Never edit `PROMPT.md`** from inside the loop. The user owns that file too.
