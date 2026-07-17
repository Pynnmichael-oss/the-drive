# Daily Football Drive — Design Doc & Working Agreement

Status: engine logic validated via simulation. No UI, no daily-content pipeline, no app scaffolding yet. This document is the source of truth — nothing here should be silently changed by a coding session without updating this doc.

---

## 1. The pitch

A Wordle/Coffee-Golf-style daily game: one football drive per day, same matchup for every player worldwide, single attempt, shareable score. Core hook is **reading a defense correctly**, not gambling on hidden odds — every outcome should be traceable back to a decision the player made.

**Single mode (§7.4/consolidation).** There is one Daily Drive, not a "base mode" plus a separate "scenario mode." Every day's matchup bundles four things, all randomized together but identical for every player that day: **opponent archetype**, **starting deficit**, **time budget**, and **starting field position**. Today's draw is picked from the locked 4-tier roster in §3.7 (Easy/Medium/Hard/Longshot) — that's the only set validated as neither dead nor trivial; expanding to a wider continuous daily-generator space is a possible future follow-up, not yet built. The flat, no-deficit "base game" described in `sim.py`/§4 still exists as an internal validation testbed (confirming reading-the-signal beats naive strategies, computing archetype par) — it's not itself a mode the player ever sees.

---

## 2. Core loop (as the player experiences it)

1. Once per drive: told **today's full matchup** — opponent identity (archetype name + flavor) *and* the day's deficit, time budget, and starting field position, together, upfront (e.g. "Down 3, 0:30 on the clock, ball on the opponent's 35").
2. Every single play, independently:
   - Engine rolls a fresh **true defensive key** for that down (weighted by archetype + situation).
   - Player is shown a **signal** — correlated with the true key, but disguised at a rate specific to that archetype — rendered as a formation (§3.4/§7.5), not a text label.
   - Player picks **Run / Pass Short / Pass Deep**.
   - Immediate reveal: true key, whether it was disguised, yards gained, why it worked or didn't. Field position, down/distance, and clock update immediately.
3. Drive continues (multiple sets of downs, resetting on conversion) until it resolves via touchdown, turnover, turnover-on-downs, field goal, or clock expiration (§3.7).
4. If a touchdown lands exactly at deficit=7, the player makes the real kick-vs-2pt call themselves (§3.8).
5. Result is WIN/TIE/LOSS against the day's deficit; a TIE goes to overtime (§3.9).
6. **Single attempt per day. No retries.** (Repeat attempts would let players memorize the true-key sequence, collapsing the entire read/disguise mechanic into memorization.)
7. Tendencies and disguise patterns are **never explicitly taught** — players learn them by playing over days, the same way Coffee Golf never tells you club physics directly.

---

## 3. Engine mechanics (validated)

### 3.1 The core matchup triangle
Three offensive plays, three defensive "keys" (what the defense is set up to stop). Each play has one bad matchup (the key that beats it) and one good matchup (a key it exploits); the third relationship is neutral.

| Play | Beaten by | Good against |
|---|---|---|
| Run | `KEY_RUN` | `KEY_DEEP` |
| Pass Short | `KEY_SHORT` | `KEY_RUN` |
| Pass Deep | `KEY_DEEP` | `KEY_RUN` |

### 3.2 Yardage model (per play, per matchup quality)
Gaussian(mean, sd), rounded, floored at -5 yards:

| Play | Good | Neutral | Bad | Turnover risk |
|---|---|---|---|---|
| Run | (8, 4) | (4, 3) | (1, 3) | 4% fumble on bad matchup |
| Pass Short | (7, 3) | (4, 3) | (1, 3) | none |
| Pass Deep | (11, 7) | (3, 6) | (-4, 6) | 22% INT on bad, 8% INT on neutral |

**Red zone compression**: inside the opponent's 20 (yard_line ≥ 80), all yardage results are multiplied by 0.55. This is realistic (less field for the offense to work with) and was necessary to fix an overtime balance bug (see §6).

### 3.3 Situational true-key weighting
The true defensive key is drawn from the archetype's tendency weights, adjusted by situation:
- Down ≤2 and distance ≥7: `KEY_RUN` weight ×1.4
- Distance ≤3: `KEY_RUN` weight ×1.3
- Down ≥3 and distance ≥7: `KEY_DEEP` weight ×1.5, `KEY_RUN` weight ×0.6

### 3.4 Signal / disguise
The shown signal equals the true key, except with probability `disguise_rate` (archetype-specific), in which case a random other key is shown instead.

**Balance guardrail (hard-won, do not violate):** archetypes cannot combine high tendency skew (one key dominant) with high disguise — that combination lets a naive fixed-play spam strategy beat actual defense-reading. Rule of thumb validated in testing: if max tendency weight is more than ~1.6× the others, cap disguise around 0.30. Balanced archetypes can run disguise up to ~0.45 safely.

**Formation visual schema (§7.5, resolved).** `formation_for_signal(shown_key)` in `sim.py` generates renderable fields from the **shown** key (post-disguise, never the true key — the player only ever sees what's presented, and finds out the true key at reveal). Pure rendering-layer addition: `show_signal` still returns the same plain `"KEY_RUN"`-style string it always did, and every play-calling strategy (`context_blind`, `trusts_signal`, etc.) is untouched.

Fields: `box_count` (int), `shell` (`no_shell` / `single_high` / `two_high`), `safety_count` (deep safeties, excludes any shallow "robber" look), `safety_depths_yards` (list), `blitz_look` (bool). Per-key profiles (flavor/creative, not balance-tested — retune freely):

| Signal | Box count | Shell mix | Blitz look% |
|---|---|---|---|
| `KEY_RUN` | 8–9 | 60% single-high / 40% no-shell | ~49% |
| `KEY_SHORT` | 6–7 | 70% single-high / 30% two-high | ~10% |
| `KEY_DEEP` | 5–6 | 75% two-high / 25% single-high | ~5% |

### 3.5 Drive structure
- Start: **80 yards from the end zone** (own 20).
- Full drive — down resets to 1 on every conversion, not capped at one set of 4.
- Ends on: touchdown (yard_line ≥ 100), turnover (INT/fumble), or turnover-on-downs (failed 4th down).
- Safety cap: 20 plays (rarely binds once the engine resolves naturally — under 2% of drives hit it).
- **Touchdown scoring (§7.3, updated):** the base daily drive has no deficit, so it always auto-kicks — a touchdown is worth 6 + a real PAT roll at `PAT_MAKE_RATE` (94%), giving 7 most of the time and 6 the rest, rather than a flat 7. `PAT_MAKE_RATE` now lives in `sim.py` as the single source of truth; `scenario.py` imports it rather than redefining it, so the base game and the deficit=7 kick-vs-gamble decision (§3.8) can never drift apart on what "high PAT rate" means. The 2-point-conversion fork itself is untouched and stays scenario-mode-only (there's no deficit to gamble against in the base game).

### 3.6 Field goal
On turnover-on-downs (or clock expiration — see §3.7), if yard_line ≥ 65 (opponent's 35 or closer): 88% chance of 3 points instead of 0.

### 3.7 Clock / deficit scenario layer
Each scenario adds: starting deficit (how many points behind), a time budget, and a starting field position (can differ from the default 80-yard start — this is a deliberate daily-variety lever).

**Clock cost per play:**
- Run: 27 seconds (always — ball stays in play)
- Pass, completed (yards > 0): 17 seconds
- Pass, incomplete (yards ≤ 0): 5 seconds (clock stops)

If clock hits 0: drive ends immediately. If in field goal range at that moment, attempt the kick (same 65-yard threshold, 88% rate) rather than defaulting to zero — this was a real bug we caught and fixed (see §6).

**Result evaluation:** WIN if points scored > deficit, TIE if equal, LOSS if less (TIE goes to overtime, §3.9).

**Locked scenario roster (§7.4).** Four difficulty tiers, each `(deficit, time_budget, start_yardline)`, validated against all 8 archetypes using the deployed `context_blind` strategy (TIE outcomes credited at each archetype's own OT win rate, N=20,000/archetype):

| Tier | Deficit | Time | Start | Mean effective win% | Range across 8 archetypes |
|---|---|---|---|---|---|
| Easy | 3 | 0:30 | opp 35 (yard_line 65) | 79.3% | 74.6–81.5% |
| Medium | 1 | 1:00 | midfield (yard_line 50) | 54.7% | 46.4–62.0% |
| Hard | 3 | 0:30 | midfield (yard_line 50) | 21.7% | 16.5–25.8% |
| Longshot | 1 | 1:00 | own 35 (yard_line 35) | 4.2% | 2.1–7.0% |

Found by grid search over deficit ∈ {1,3,4,7,8} × time ∈ {20,30,45,60,90,120}s × start ∈ {20,35,50,65,80}, screened for tight cross-archetype spread (no tier should be trivial for one archetype and a wall for another), then re-validated at higher N. **Every earlier example scenario with `deficit >= 4` combined with a short time budget and a deep start (e.g. down 8/0:30/own45, down 8/1:30/own40, down 7/1:30/own40, and the explicit "control: too hard?" config at down 8/0:45/own20) came back at 0.0% for every single archetype and strategy in the grid** — these aren't "Very Hard," they're dead/impossible content and are cut from the roster rather than kept as a difficulty tier. If a "genuinely brutal but not impossible" tier is wanted later, the Longshot row above is the template to build from (small deficit, tight time, non-trivial distance).

**Realistic deficit generator (follow-up, supersedes the fixed 4-tier pick for daily variety).** The 4-tier roster above is still the validated *set of safe combos* — it's just no longer sampled uniformly. Real NFL margin-of-victory data (BetMGM/Covers/Eldorado, 2000–2025 era) shows scoring differentials are not remotely uniform: 3 points is the most common margin by far (~15%), 7 is next (~9%), 4/6 form a solid second tier, 1/2 sit around 4.6% each (rarer than 3/7 but not negligible), and 5 is a genuine "dead number" (~1–2%, rarer than even 9 or 12).

**Hard cap at deficit 8.** This engine scores at most once per drive (TD+2pt = 8 max), so a deficit of 9+ is not just hard, it's *mathematically un-tie-able* — no sequence of plays wins or ties. Real NFL margins of 10/14/etc. are common but structurally impossible here, so the realistic weights are truncated to 1–8 and renormalized:

| Deficit | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Daily weight | 9.2% | 9.2% | 30.1% | 11.0% | 3.0% | 13.1% | 18.3% | 6.0% |

Given the sampled deficit, `(time_budget, start_yardline)` is drawn uniformly from that deficit's grid-validated non-dead combos (extended the original grid search to cover all of deficit 1–8, not just {1,3,4,7,8}, N=1,500/archetype/combo). **New finding from that extension:** deficit 4–6 have far fewer viable combos (4–5 each, all needing a generous 90–120s clock) than deficit 7–8 (11 each) — because `context_blind`'s deep-shot gamble (§7.7) only gates on `deficit >= 7`. Deficits 4–6 don't get that assist, so they're structurally harder to make winnable on a short clock than the "worse" deficits of 7–8. Not fixed here — flagging it as a real candidate follow-up (extend the gamble gate down to `deficit >= 4`?) rather than silently patching engine behavior that's already locked and tested.

### 3.8 PAT vs. 2-point conversion
After a touchdown (worth 6 before the extra point):
- **Deficit ≤ 6**: auto-kick PAT (94% success rate). Guaranteed win either way — no reason to risk it.
- **Deficit = 8**: forced to go for 2 (48% success rate). Kicking here mathematically guarantees a loss (7 < 8), so there's no real choice.
- **Deficit = 7**: **real player decision.** Kick for a near-certain tie (94%) and take it to overtime, or gamble on 2 points (48%) for an immediate win.
  - **Validated conclusion: kicking is statistically better across every skill level tested**, including a random-button-masher (69.6% effective win rate via kick vs. 48% via gambling). This matches real NFL/college analytics. **Decision: keep this realistic rather than artificially rebalance it toward a coinflip** — part of the skill test is knowing kicking is usually correct, and gambling remains available for players who want it anyway.

### 3.9 Overtime
Triggered on a TIE result. College-style: start at the opponent's 25 (yard_line = 75), no clock, sudden death — first score of any kind wins, any turnover/turnover-on-downs outside field goal range loses. Uses the same play-calling engine and red-zone compression as the main drive.

---

## 4. Locked opponent archetype roster (8)

Each is a `(tendency weights, disguise_rate)` pair. Par = average points a skilled "reads the signal" strategy scores against that archetype, now computed under the PAT-adjusted touchdown scoring from §3.5 (6 + PAT roll, not a flat 7), at N=200,000 trials for a tight estimate. **RE-BAKED AND LOCKED (§7.3):**

| Archetype | Run / Short / Deep weights | Disguise | Par (locked) |
|---|---|---|---|
| Blitz-heavy run stuffer | 2.0 / 1.0 / 0.7 | 0.15 | 4.75 |
| Vanilla base 4-3 | 1.0 / 1.0 / 1.0 | 0.20 | 4.54 |
| Bend-don't-break prevent | 0.8 / 1.0 / 2.0 | 0.35 | 4.42 |
| Robber coverage | 0.8 / 1.2 / 1.4 | 0.30 | 4.10 |
| Amoeba front | 1.2 / 1.5 / 0.7 | 0.22 | 3.67 |
| Aggressive disguised blitz | 1.8 / 1.0 / 0.9 | 0.28 | 3.67 |
| Zone/underneath spy | 1.0 / 2.0 / 0.8 | 0.25 | 3.24 |
| Disguise-heavy trickster | 1.0 / 1.0 / 1.0 | 0.45 | 2.67 |

All 8 re-validated at the higher trial count: reading the signal beats every naive strategy (always-run, always-pass-short, always-pass-deep, random, situational-only-ignoring-signal) in every archetype, with a healthy margin — unchanged from the original finding, just confirmed under the corrected scoring and a tighter confidence interval. Values shifted down by 0.01–0.07 pts from the original provisional table (the PAT roll occasionally costs a point that the old flat-7 TD never did); no archetype's ranking or the reads-signal guarantee changed.

**Note on what "par" is for (post-consolidation, §1):** this table is an internal validation benchmark — it confirms reading-the-signal is a genuinely dominant strategy before the game ever ships, using the flat no-deficit engine as a clean testbed. It is **not** what the player sees day to day, since every shipped Daily Drive runs through the deficit/clock scenario layer instead. The player-facing benchmark is §3.7's locked scenario roster (mean effective win% and per-archetype range for Easy/Medium/Hard/Longshot) — that's the "par" a given day's result should be judged against.

---

## 5. Explicitly locked decisions

- Single attempt per day, no retries.
- Tendencies/disguise patterns learned through play, never taught in-app.
- Field goal added for stalled drives (§3.6).
- Fixed 80-yard start for the base game; variable field position is a deliberate lever for scenario mode (§3.7).
- Stopwatch tracks total time-to-complete as a secondary shareable stat — **does not** limit decision time. No pressure timer on individual plays.
- Formation should be shown visually (top-of-screen), not as plain text — signal data now carries renderable fields (box count, safety depth, shell type) via `formation_for_signal()`, not just a flat key label (§3.4, §7.5).
- Kick-vs-gamble at deficit-7 stays realistic/kick-favored rather than artificially rebalanced (§3.8).
- Context-aware clock heuristic (avoid running when clock is tight) is cut — cross-archetype testing showed it's not a consistent skill lever (§7.1).
- `context_blind` (scenario mode) gambles Pass Deep on signal `KEY_RUN` specifically when `deficit >= 7`, reusing the §3.8 threshold. Base full-drive game (`sim.py`) is untouched by this — the gate can't fire without a scenario deficit (§7.7).
- Base-game touchdowns roll a real PAT (94% at `PAT_MAKE_RATE`, defined once in `sim.py`) instead of a flat 7 points. No 2pt fork in the base game — that stays scenario-mode-only, gated on deficit (§7.3).
- Scenario mode ships with a 4-tier roster (Easy/Medium/Hard/Longshot, §3.7), grid-searched and validated across all 8 archetypes. The old ad-hoc example scenarios with `deficit >= 4` + short clock + deep start are cut — confirmed dead/impossible, not "hard" (§7.4).
- **Single game mode, not two.** There's no separate "base game" the player plays — the shipped Daily Drive is always the deficit/clock/start-yardline scenario layer, with the opponent archetype bundled into the same daily draw. All four (archetype, deficit, time, start) are randomized together but shared across every player that day. The old flat-scoring `sim.py` engine survives only as an internal validation testbed for §4's naive-strategy guarantee, not as something the player ever sees (§1).

---

## 6. Bugs we found and fixed (keep for context — these are the kind of failure mode to keep testing for)

1. **Deep-pass spam dominance**: initial yardage/turnover tuning let "always throw deep" beat actual defense-reading. Fixed by reducing deep-pass explosiveness and making turnovers cost more than a stalled drive (-2 instead of 0).
2. **Skew × disguise stacking**: an archetype that was simultaneously the most tendency-driven and the most disguised broke the balance again, even after fix #1. Led to the guardrail rule in §3.4.
3. **Arbitrary play cap masking real outcomes**: original 12-play cap was hit by 63% of drives, meaning most results were being artificially truncated rather than resolved by football logic. Raised to 20; now rarely binds.
4. **Clock expiration eating free field goals**: when the clock hit 0, the drive scored 0 even if sitting in field goal range, because the FG-on-stall logic only checked on turnover-on-downs, not clock expiration. Fixed.
5. **Overtime was a near-auto-win (97.6%)**: 25 yards with up to 10 plays and full down-resets was far too generous for "sudden death." Red-zone compression (§3.2) brought it down to ~74–95% depending on skill, which is still high but is now traceable to a real, understood cause rather than a hidden bug — and is arguably realistic (real college OT possessions do score at a high rate; that's why it exists).

---

## 7. Open questions (do not let these get silently dropped)

1. ~~Context-aware clock heuristic never proved itself.~~ **RESOLVED (negative result, locked).** Cross-archetype testing (all 8, all 5 tested scenario configs) confirms this is not a genuine skill lever: `context_aware` sometimes beats `context_blind` and sometimes loses to it, with no consistent pattern by archetype or scenario. Per §8.5, reporting this plainly rather than continuing to hunt for a heuristic that makes it work — **decision: cut the context-aware clock mechanic** rather than keep tuning it. (Superseded by item 7 below, which found a different, real lever in the same area.)
2. ~~The scenario layer has only been tested against a single flat tendency.~~ **RESOLVED for OT and kick-vs-gamble; scenario win/tie/loss rates also validated.** All 8 archetypes tested:
   - **OT win rate**: 89.9–94.6% (skilled) / 68.6–79.6% (random) across the full roster — consistent with the flat-default 94.3% finding in §6.5. Locked.
   - **Kick-vs-gamble at deficit=7**: confirmed archetype-independent — it's a fixed post-TD coin flip (94% kick / 48% gamble) that never touches defensive tendency or disguise. The existing kick-favored conclusion needed no further cross-archetype testing and is locked as-is.
   - **Scenario win/tie/loss rates** (5 tested configs × 8 archetypes): behavior is consistent across the roster — genuinely unwinnable scenarios (e.g. down 8/0:30/own45) stay ~100% loss for every archetype and strategy; winnable ones scale sensibly with archetype disguise/skew. See item 7 for a real strategy-logic finding this surfaced.
3. ~~Par values in §4 are provisional~~ **RESOLVED, locked.** The real gap wasn't drift between two engines — the base daily drive was scoring touchdowns as a flat 7, while scenario mode always rolled a real PAT. **Decision: base game touchdowns now roll a real PAT too** (6 + success at `PAT_MAKE_RATE`, kept high at 94%), with `PAT_MAKE_RATE` moved into `sim.py` as the single source of truth and imported by `scenario.py` — one number, two consumers, can't drift apart again. The base game still has no deficit, so it always auto-kicks; the deficit=7 kick-vs-gamble decision (§3.8) is untouched and stays scenario-mode-only, since there's nothing to gamble against without a deficit. Par table re-baked at N=200,000 under the corrected scoring (§4) — values shifted down by 0.01–0.07 pts, no archetype's ranking changed, reads-the-signal still beats every naive strategy in all 8.
4. ~~Daily deficit/time/starting-field-position combinations are not a finished roster.~~ **RESOLVED, locked.** Grid-searched and validated a 4-tier roster (Easy/Medium/Hard/Longshot) against all 8 archetypes — see §3.7. The earlier one-off examples weren't actually a difficulty spread; every `deficit >= 4` + short-clock + deep-start combo tested came back 0.0% for every archetype, including the config explicitly flagged "(control: too hard?)" — confirmed too hard, and cut rather than kept.
5. ~~Signal data schema for the formation visual is undefined.~~ **RESOLVED, locked.** `formation_for_signal()` added to `sim.py` (§3.4) — generates box count, shell type, safety depths, and blitz-look flag from the shown (post-disguise) key. Pure rendering-layer addition, verified to leave `show_signal`'s contract and every play-calling strategy untouched. Field *values* are flavor/creative and freely retunable; only the presence of the fields was the actual open question.
6. ~~Par computation method for production~~ **RESOLVED, locked: precompute.** The full set is 8 base-game par values + 4 scenario tiers × 8 archetypes = 40 numbers total — trivially small and static (nothing here depends on the individual player, only on archetype/tier). Live computation would mean running thousands of Monte Carlo trials per request for numbers that never change between requests; precompute is the obvious choice, not a close call. Baked into `par_baked.json`, regenerated whenever `sim.py`/`scenario.py`/the archetype roster changes.
7. ~~`context_blind` never selects Pass Deep for any signal.~~ **RESOLVED, locked.** Confirmed by direct test: for signal `KEY_RUN`, the tie-break between Pass Short and Pass Deep (both "good" matchups) always resolves to Pass Short; for `KEY_SHORT`/`KEY_DEEP` there's only one viable play anyway. Fine for the base game, but it meant "skilled" play was structurally incapable of the big plays needed to escape the short-clock deficit scenarios in item 2.
   - **Change made:** `context_blind` now gambles Pass Deep on signal `KEY_RUN` when `deficit >= 7` — reusing the existing forced-gamble threshold from §3.8, not a new one.
   - **Validated:** base full-drive game untouched when the gate can't fire (no deficit in that mode), so §4's par values and naive-strategy guarantee are unaffected.
   - **Two variants tested, one rejected:** an unconditional "always gamble" version breaks the §3.4 skew/disguise guardrail (beats reads-the-signal in low-disguise, high-skew Blitz-heavy: 4.93 vs 4.79 pts) — rejected as a base-game default. A clock-only gate (`clock<=30s`, no deficit check) was also rejected: it fires too broadly, trading safe ties for rare wins even when tying into OT (~90%+ win rate) is the better outcome, and flips sign by archetype the same way item 1's heuristic did.
   - **Net effect of the adopted (deficit-gated) version:** previously-100%-loss desperate scenarios gain modest real win/tie equity (0.2–2.2%), with no measurable cost to any scenario where the gate doesn't fire.

---

## 8. How we work (read this before writing code)

This project has been built by simulating every mechanic before trusting it, and that discipline has caught a real, game-breaking bug at nearly every step. Keep doing this:

1. **Never mark something "locked" without a Monte Carlo test to back it up.** A design decision that sounds right is not the same as one that's been simulated.
2. **Test against the full roster, not the default case.** Multiple bugs in this doc (§6.2, and open question §7.2) only appeared when checked against archetypes other than the balanced default. A feature that works in isolation may not survive contact with the extremes.
3. **When you fix a bug, check whether you actually fixed it or just moved it.** (See §6.5 — reducing the OT win rate from 97.6% to 94.3% looked like a fix but barely changed the underlying conclusion; the real fix required understanding *why* it was still easy, not just nudging a number.)
4. **When a design choice has a genuine fork with no obviously correct answer, stop and ask — don't silently pick one.** Several sections of this doc exist because a fork got surfaced instead of resolved unilaterally.
5. **Report results plainly, including bad ones.** A simulation that disproves your own idea (like the context-aware clock heuristic) is more valuable than one that confirms it. Don't reach for a rationalization — say what the data showed.
6. **Baby steps.** Implement the smallest testable slice, validate it, report the actual numbers, and only then propose the next step.
7. **Keep this document current.** Anything decided gets logged as locked (with the reasoning/data that justified it); anything unresolved gets logged as an open question. Nothing should be decided implicitly inside code with no trace in this doc.
