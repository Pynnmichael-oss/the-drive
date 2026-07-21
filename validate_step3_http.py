"""Step 3 validation, full grid: same 6-scenario x 8-archetype x 200-seed
grid Step 2 validated directly against GameSession (9,600 trials total),
now driven by context_blind entirely over HTTP. Compares the win/tie/loss
distribution per cell (and aggregated) against the same bot driving
GameSession directly, to confirm the HTTP layer doesn't shift outcomes.

Uses TestClient (real HTTP request/response cycle through app.py's actual
routing) with draw_matchup monkeypatched to each fixed scenario/archetype
combo -- the live /session/start endpoint only exposes the random dev-mode
draw, no override, so this is the only way to hit specific cells without
an infeasible number of retries (see prior validation script for the math).
"""
import sys
sys.path.insert(0, "/home/michaelpynn/projects/the-drive")

from fastapi.testclient import TestClient
from scenario import context_blind
import app as app_module
from game_session import GameSession

client = TestClient(app_module.app)

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
SCENARIOS = [
    ("Down 8, 0:30, own 45", 8, 30, 45),
    ("Down 3, 0:30, opp 35", 3, 30, 65),
    ("Down 8, 1:30, own 40", 8, 90, 40),
    ("Down 7, 1:30, own 40", 7, 90, 40),   # deficit=7 -- exercises kick-choice over HTTP
    ("Down 1, 1:00, midfield", 1, 60, 50),
    ("Down 8, 0:45, own 20 (control: too hard?)", 8, 45, 20),
]
N = 200  # matches Step 2's grid check: 6 x 8 x 200 = 9,600


def run_direct(tendency, disguise, start, time_budget, deficit):
    gs = GameSession(tendency, disguise, start, time_budget, deficit)
    state = gs.start()
    while not gs.done:
        if gs.pending_kick_choice:
            state = gs.resolve_kick_choice(go_for_two=True)
            continue
        play = context_blind(gs.down, gs.distance, state["signal"], gs.clock, deficit)
        state = gs.call_play(play)
    return state["result"]


def run_over_http(tendency, disguise, start, time_budget, deficit):
    matchup = {
        "archetype": "fixed-test-config", "tendency": tendency, "disguise_rate": disguise,
        "deficit": deficit, "time_budget": time_budget, "start_yardline": start,
    }
    orig_draw = app_module.draw_matchup
    app_module.draw_matchup = lambda: matchup
    try:
        resp = client.post("/session/start")
    finally:
        app_module.draw_matchup = orig_draw

    body = resp.json()
    session_id, state = body["session_id"], body["state"]

    while True:
        if state["done"]:
            return state["result"]
        if state["pending_kick_choice"]:
            state = client.post(f"/session/{session_id}/kick-choice", json={"go_for_two": True}).json()
            continue
        play = context_blind(state["down"], state["distance"], state["signal"], state["clock"], deficit)
        state = client.post(f"/session/{session_id}/play", json={"play": play}).json()


direct_total = {"WIN": 0, "TIE": 0, "LOSS": 0}
http_total = {"WIN": 0, "TIE": 0, "LOSS": 0}
total_trials = 0

for label, deficit, time_budget, start in SCENARIOS:
    print(f"=== {label} (deficit={deficit}, time={time_budget}, start={start}) ===")
    direct_scenario = {"WIN": 0, "TIE": 0, "LOSS": 0}
    http_scenario = {"WIN": 0, "TIE": 0, "LOSS": 0}
    for arch_name, (tendency, disguise) in ARCHETYPES.items():
        direct_outcomes = {"WIN": 0, "TIE": 0, "LOSS": 0}
        http_outcomes = {"WIN": 0, "TIE": 0, "LOSS": 0}
        for _ in range(N):
            direct_outcomes[run_direct(tendency, disguise, start, time_budget, deficit)] += 1
            http_outcomes[run_over_http(tendency, disguise, start, time_budget, deficit)] += 1
            total_trials += 1

        for k in direct_total:
            direct_total[k] += direct_outcomes[k]
            http_total[k] += http_outcomes[k]
            direct_scenario[k] += direct_outcomes[k]
            http_scenario[k] += http_outcomes[k]

        d_pct = {k: v / N * 100 for k, v in direct_outcomes.items()}
        h_pct = {k: v / N * 100 for k, v in http_outcomes.items()}
        print(f"  {arch_name:28s} direct W/T/L% {d_pct['WIN']:5.1f}/{d_pct['TIE']:5.1f}/{d_pct['LOSS']:5.1f}"
              f"   http W/T/L% {h_pct['WIN']:5.1f}/{h_pct['TIE']:5.1f}/{h_pct['LOSS']:5.1f}")

    ns = N * len(ARCHETYPES)
    ds = {k: v / ns * 100 for k, v in direct_scenario.items()}
    hs = {k: v / ns * 100 for k, v in http_scenario.items()}
    print(f"  --- scenario total (N={ns}) --- direct W/T/L% {ds['WIN']:.1f}/{ds['TIE']:.1f}/{ds['LOSS']:.1f}"
          f"   http W/T/L% {hs['WIN']:.1f}/{hs['TIE']:.1f}/{hs['LOSS']:.1f}")
    print()

print(f"=== GRAND TOTAL (N={total_trials} trials each side, matches Step 2's 6x8x{N}={6*8*N}) ===")
dt_pct = {k: v / total_trials * 100 for k, v in direct_total.items()}
ht_pct = {k: v / total_trials * 100 for k, v in http_total.items()}
print(f"direct (GameSession, in-process): {direct_total}  ->  WIN {dt_pct['WIN']:.2f}% TIE {dt_pct['TIE']:.2f}% LOSS {dt_pct['LOSS']:.2f}%")
print(f"http   (real request/response):   {http_total}  ->  WIN {ht_pct['WIN']:.2f}% TIE {ht_pct['TIE']:.2f}% LOSS {ht_pct['LOSS']:.2f}%")
