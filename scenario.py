import random
from sim import resolve_yards, true_key_for_situation, show_signal, BEATS, GOOD_VS, PAT_MAKE_RATE

RUN_CLOCK = 27
PASS_COMPLETE_CLOCK = 17
PASS_INCOMPLETE_CLOCK = 5

def clock_cost(play, yards):
    if play == "RUN":
        return RUN_CLOCK
    return PASS_COMPLETE_CLOCK if yards > 0 else PASS_INCOMPLETE_CLOCK

# PAT_MAKE_RATE now imported from sim.py (§7.3) -- single source of truth,
# base game and scenario mode can't drift apart on it.
TWO_PT_MAKE_RATE = 0.48

def resolve_touchdown(deficit):
    # Go for 2 only when a PAT alone can't win/tie (deficit 7) or can't even tie (deficit 8).
    go_for_two = deficit in (7, 8)
    if go_for_two:
        made = random.random() < TWO_PT_MAKE_RATE
        return 6 + (2 if made else 0)
    made = random.random() < PAT_MAKE_RATE
    return 6 + (1 if made else 0)

def run_scenario_drive(strategy, tendency, disguise_rate, start_yardline, time_budget, deficit):
    yard_line, down, distance, clock = start_yardline, 1, 10, time_budget
    plays_run = 0
    points = 0
    while True:
        plays_run += 1
        true_key = true_key_for_situation(down, distance, tendency)
        signal = show_signal(true_key, disguise_rate)
        play = strategy(down, distance, signal, clock, deficit)
        yards, turnover = resolve_yards(play, true_key, yard_line)
        clock -= clock_cost(play, yards)

        if turnover:
            points = -2
            break
        yard_line += yards
        if yard_line >= 100:
            points = resolve_touchdown(deficit)
            break
        if yards >= distance:
            down, distance = 1, 10
        else:
            distance -= yards
            down += 1
            if down > 4:
                points = 3 if (yard_line >= 65 and random.random() < 0.88) else 0
                break
        if clock <= 0:
            points = 3 if (yard_line >= 65 and random.random() < 0.88) else 0
            break
        if plays_run >= 25:
            points = 0
            break
    result = "WIN" if points > deficit else ("TIE" if points == deficit else "LOSS")
    return {"points": points, "plays": plays_run, "clock_left": max(clock, 0), "result": result}

def run_overtime_drive(strategy, tendency, disguise_rate, start_yardline=75):
    yard_line, down, distance = start_yardline, 1, 10
    plays_run = 0
    while True:
        plays_run += 1
        true_key = true_key_for_situation(down, distance, tendency)
        signal = show_signal(true_key, disguise_rate)
        play = strategy(down, distance, signal, 9999, 0)  # no clock pressure in OT
        yards, turnover = resolve_yards(play, true_key, yard_line)
        if turnover:
            return {"result": "LOSS", "plays": plays_run}
        yard_line += yards
        if yard_line >= 100:
            return {"result": "WIN", "plays": plays_run}  # TD wins outright; PAT treated as automatic in sudden death
        if yards >= distance:
            down, distance = 1, 10
        else:
            distance -= yards
            down += 1
            if down > 4:
                if yard_line >= 65 and random.random() < 0.88:
                    return {"result": "WIN", "plays": plays_run}
                return {"result": "LOSS", "plays": plays_run}
        if plays_run >= 10:
            return {"result": "LOSS", "plays": plays_run}

# §7.1: context-aware clock heuristic (avoid running when clock is tight) was
# tested across all 8 archetypes and found to be an inconsistent, non-learnable
# effect (beats context_blind in some archetype/scenario combos, loses in others,
# no pattern). Cut per that finding rather than kept and re-tuned.
#
# §7.7: signal KEY_RUN has two "good" counter-plays (PASS_SHORT, PASS_DEEP); the
# tie-break previously always picked PASS_SHORT, which meant context_blind could
# never throw deep -- fine for the base game, but it made short-clock deficit
# scenarios structurally unwinnable even when a low-probability big play was the
# only real path back. Gated gamble added below, reusing the existing §3.8
# forced-2pt threshold (deficit >= 7) rather than a new one. Validated: base
# full-drive game is unaffected (no deficit there, so the gate never fires);
# an unconditional version and a clock-only gate were both tested and rejected
# (see §7.7 in the design doc for the numbers).
def context_blind(down, distance, signal, clock, deficit):
    good_play = [p for p, k in GOOD_VS.items() if k == signal]
    beater = {"KEY_RUN": "PASS_SHORT", "KEY_SHORT": "RUN", "KEY_DEEP": "RUN"}
    if signal == "KEY_RUN" and deficit >= 7:
        return "PASS_DEEP"
    return good_play[0] if good_play else beater[signal]

if __name__ == "__main__":
    # Per §7.2/§7.7: default test harness now runs the full 8-archetype roster,
    # not just the flat default -- that flat-only test was the gap that hid
    # both the context-aware inconsistency (§7.1) and the missing deep-shot
    # gamble (§7.7) for as long as it did.
    # NOTE: not importing from archetypes.py directly -- that module runs its
    # own full simulation loop at import time (no __main__ guard), so pulling
    # ARCHETYPES from it here would trigger that as a side effect. Inlined
    # instead; keep in sync with archetypes.py if the roster changes.
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
    scenarios = [
        ("Down 8, 0:30, own 45", 8, 30, 45),
        ("Down 3, 0:30, opp 35", 3, 30, 65),
        ("Down 8, 1:30, own 40", 8, 90, 40),
        ("Down 7, 1:30, own 40", 7, 90, 40),
        ("Down 1, 1:00, midfield", 1, 60, 50),
        ("Down 8, 0:45, own 20 (control: too hard?)", 8, 45, 20),
    ]
    N = 8000
    print(f"{'Scenario':24s} {'Archetype':28s} {'Win%':>6s} {'Tie%':>6s} {'Loss%':>6s}")
    for label, deficit, time_budget, start in scenarios:
        for arch_name, (tendency, disguise) in ARCHETYPES.items():
            outcomes = {"WIN": 0, "TIE": 0, "LOSS": 0}
            for _ in range(N):
                r = run_scenario_drive(context_blind, tendency, disguise, start, time_budget, deficit)
                outcomes[r["result"]] += 1
            print(f"{label:24s} {arch_name:28s} {outcomes['WIN']/N*100:6.1f} {outcomes['TIE']/N*100:6.1f} {outcomes['LOSS']/N*100:6.1f}")
