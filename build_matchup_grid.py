"""One-off Monte Carlo build script (§3.7 extended grid search) producing
matchup_grid.json: for each deficit 1-8, which (time_budget, start_yardline)
combos are non-dead (not 0.0% effective win rate for every archetype).

Not imported by the server at runtime -- run manually to regenerate the JSON
when the underlying engine or archetype roster changes.

NOTE: not importing ARCHETYPES from archetypes.py -- that module runs its own
full simulation at import time (no __main__ guard, see scenario.py's own
comment on this). Inlined here instead, kept in sync with archetypes.py/
scenario.py's copies.
"""
import json
import random

from scenario import run_scenario_drive, run_overtime_drive, context_blind

ARCHETYPES = {
    "Blitz-heavy run stuffer":   ({"KEY_RUN": 2.0, "KEY_SHORT": 1.0, "KEY_DEEP": 0.7}, 0.15),
    "Bend-dont-break prevent":   ({"KEY_RUN": 0.8, "KEY_SHORT": 1.0, "KEY_DEEP": 2.0}, 0.35),
    "Disguise-heavy trickster":  ({"KEY_RUN": 1.0, "KEY_SHORT": 1.0, "KEY_DEEP": 1.0}, 0.45),
    "Zone/underneath spy":       ({"KEY_RUN": 1.0, "KEY_SHORT": 2.0, "KEY_DEEP": 0.8}, 0.25),
    "Aggressive disguised blitz":({"KEY_RUN": 1.8, "KEY_SHORT": 1.0, "KEY_DEEP": 0.9}, 0.28),
    "Vanilla base 4-3":          ({"KEY_RUN": 1.0, "KEY_SHORT": 1.0, "KEY_DEEP": 1.0}, 0.20),
    "Robber coverage":           ({"KEY_RUN": 0.8, "KEY_SHORT": 1.2, "KEY_DEEP": 1.4}, 0.30),
    "Amoeba front":              ({"KEY_RUN": 1.2, "KEY_SHORT": 1.5, "KEY_DEEP": 0.7}, 0.22),
}

DEFICITS = [1, 2, 3, 4, 5, 6, 7, 8]
TIME_BUDGETS = [20, 30, 45, 60, 90, 120]
START_YARDLINES = [20, 35, 50, 65, 80]

# §3.7's daily weight table (deficit 1-8, renormalized real-NFL-margin weights)
DEFICIT_WEIGHTS = {1: 9.2, 2: 9.2, 3: 30.1, 4: 11.0, 5: 3.0, 6: 13.1, 7: 18.3, 8: 6.0}

N_SCENARIO = 1500  # per archetype per combo, matches §3.7's stated extended-grid N
N_OT = 5000        # per archetype, for the OT win-rate credit used on TIE outcomes


def ot_win_rates():
    rates = {}
    for name, (tendency, disguise) in ARCHETYPES.items():
        wins = sum(
            run_overtime_drive(context_blind, tendency, disguise)["result"] == "WIN"
            for _ in range(N_OT)
        )
        rates[name] = wins / N_OT
    return rates


def effective_win_rate(deficit, time_budget, start, tendency, disguise, ot_rate):
    outcomes = {"WIN": 0, "TIE": 0, "LOSS": 0}
    for _ in range(N_SCENARIO):
        r = run_scenario_drive(context_blind, tendency, disguise, start, time_budget, deficit)
        outcomes[r["result"]] += 1
    return (outcomes["WIN"] + outcomes["TIE"] * ot_rate) / N_SCENARIO


def main():
    random.seed(12345)
    print("computing OT win rates per archetype...")
    ot_rates = ot_win_rates()
    for name, rate in ot_rates.items():
        print(f"  {name:28s} {rate*100:5.1f}%")

    grid = {}
    for deficit in DEFICITS:
        viable = []
        for time_budget in TIME_BUDGETS:
            for start in START_YARDLINES:
                rates = [
                    effective_win_rate(deficit, time_budget, start, tendency, disguise, ot_rates[name])
                    for name, (tendency, disguise) in ARCHETYPES.items()
                ]
                if min(rates) > 0.0:
                    viable.append({"time_budget": time_budget, "start_yardline": start})
        grid[str(deficit)] = viable
        print(f"deficit {deficit}: {len(viable)}/{len(TIME_BUDGETS) * len(START_YARDLINES)} viable combos")

    out = {
        "deficit_weights": DEFICIT_WEIGHTS,
        "viable_combos_by_deficit": grid,
        "archetypes": {name: {"tendency": t, "disguise_rate": d} for name, (t, d) in ARCHETYPES.items()},
        "meta": {"n_scenario": N_SCENARIO, "n_ot": N_OT, "seed": 12345},
    }
    with open("matchup_grid.json", "w") as f:
        json.dump(out, f, indent=2)
    print("wrote matchup_grid.json")


if __name__ == "__main__":
    main()
