# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Daily Drive" — a single-drive football signal-reading game. The defense shows a (possibly disguised) formation; the player reads it and calls a play. Engine logic was built and Monte-Carlo-validated before any UI existed; `daily-drive-design-doc.md` is the source of truth for game rules and states explicitly that nothing in it "should be silently changed by a coding session without updating this doc."

## Commands

No `requirements.txt` — dependencies live only in a project-local, gitignored `.venv`.

```bash
# one-time setup
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn
.venv/bin/pip install playwright  # only needed for in-browser client checks

# run the server (serves the client at http://127.0.0.1:8000/)
.venv/bin/uvicorn app:app --port 8000

# rebuild matchup_grid.json (Monte Carlo grid search, ~30s, overwrites the file)
python3 build_matchup_grid.py

# ad hoc engine validation (no pytest/test suite exists in this repo)
python3 scenario.py      # win/tie/loss table across the 6 scenarios x 8 archetypes
python3 archetypes.py    # per-archetype strategy comparison (side effects at import time, see below)
python3 validate_step3_http.py  # HTTP layer vs direct-GameSession win/tie/loss comparison
```

## Architecture

Layered, bottom-up, each layer wrapping the one below rather than reimplementing it:

1. **`sim.py`** — base engine. `resolve_yards`, `true_key_for_situation`, `show_signal` (the actual play-resolution math); `formation_for_signal` (pure rendering-layer draw from the *shown* key — never feeds back into resolution); `run_drive` (flat, no-deficit drive used only as an internal strategy-benchmark testbed, not a player-facing mode). `FG_RANGE_YARDLINE`, `FG_MAKE_RATE`, `PAT_MAKE_RATE` are defined here as the single source of truth — `scenario.py` and `game_session.py` import them rather than redefining.

2. **`scenario.py`** — adds the deficit/clock/starting-field-position layer on top of `sim.py`. `run_scenario_drive(strategy, tendency, disguise_rate, start_yardline, time_budget, deficit)` runs a full drive given a strategy *callback* (called once per play). `context_blind` is the deployed non-cheating bot strategy, used throughout for validation. Note: `resolve_touchdown()` forces a 2-point attempt at deficit 7 the same as deficit 8, even though the design doc specifies deficit=7 should be a real human kick-vs-2pt decision — `game_session.py` works around this rather than changing `resolve_touchdown` itself (see below).

3. **`archetypes.py`** — the 8 opponent archetypes plus a standalone strategy-comparison script. **Has no `__main__` guard — importing this module runs a full simulation as a side effect.** Every other module that needs the archetype roster keeps its own inlined copy rather than importing from here (see the comment in `scenario.py`'s `__main__` block and in `build_matchup_grid.py`). Keep those copies in sync manually if the roster changes.

4. **`game_session.py`** — `GameSession`, a stateful decomposition of `run_scenario_drive`'s loop into `start()` / `call_play(play)` / `resolve_kick_choice(go_for_two)`, for a client that shows the signal and waits for an externally-supplied play instead of calling a strategy callback in a tight loop. Validated by seeded parity checks against `run_scenario_drive` (identical RNG-draw sequence → identical outcomes). Also the one place that intercepts the deficit=7 touchdown case: it pauses (`pending_kick_choice=True`) instead of calling `resolve_touchdown`, and `resolve_kick_choice` resolves it.
   - `formation_for_signal` is called once per new signal and cached (`self._formation`), not recomputed on every state read — it draws from the same global `random` stream, so recomputing it on every read would burn extra draws for no reason.
   - **RNG note**: `sim.py`, `scenario.py`, and `game_session.py` all draw from the shared global `random` module (no per-instance `Random()`). Exact seed-for-seed reproducibility between `run_scenario_drive` and `GameSession` only holds as long as no extra draws are inserted into the sequence (e.g. adding `formation_for_signal` broke bit-exact replay — expected, not a bug). After a change like that, validate the win/tie/loss *distribution* stays consistent at high N rather than trying to re-match seeds exactly.
   - `MAX_PLAYS = 25` is a named constant here but a bare literal in `scenario.py`'s `run_scenario_drive` — known, unresolved duplication.

5. **`build_matchup_grid.py`** — one-off Monte Carlo script, not imported at runtime. Screens every `(deficit, time_budget, start_yardline)` combo per archetype and writes the non-dead ones (viable only if *every* archetype's effective win rate — TIE credited at that archetype's own overtime win rate — is nonzero) to `matchup_grid.json`, along with the deficit sampling weights and archetype roster. Re-run manually whenever the engine or archetype roster changes; `app.py` just reads the cached JSON.

6. **`app.py`** — thin FastAPI wrapper over `GameSession`. In-memory `SESSIONS` dict keyed by UUID (no DB/auth/persistence). `draw_matchup()` implements the dev-mode daily draw: uniform archetype × weighted deficit × uniform pick from that deficit's viable combos in `matchup_grid.json`. Serves the client via `StaticFiles` mount + a `/` route returning `static/index.html`.

7. **`static/index.html`** — single-page vanilla JS/CSS client, no build step, no framework. Talks to `app.py`'s endpoints via `fetch`; all view updates are in-place DOM writes (no full-page reloads/blocking screens).

8. **`validate_step3_http.py`** — kept as a reproducible artifact of the HTTP-layer validation (bot-driven, real requests via FastAPI's `TestClient`, compared against the same bot driving `GameSession` directly).

## Working in this repo

- Treat `daily-drive-design-doc.md` as authoritative for game rules/balance; it's organized by section number (§) which other files' comments reference (e.g. `# §7.3`, `# §3.8`). Cross-check claims against it rather than trusting an unlabeled prior commit — this repo has had commits that claimed completed work while containing no real changes.
- When changing anything in the `sim.py` → `scenario.py` → `game_session.py` chain, re-validate with a Monte Carlo comparison (seeded parity if no new RNG draws were introduced, distributional comparison at N in the thousands if they were) rather than trusting the diff alone.
