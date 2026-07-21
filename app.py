"""Step 3: thin FastAPI wrapper over GameSession.

In-memory sessions only (dict keyed by session id, no DB/auth/persistence --
out of scope per Step 3 spec). Dev-mode matchup draw: uniform random
archetype x §3.7's realistic-weighted deficit distribution x a uniform pick
from that deficit's grid-validated viable (time_budget, start_yardline)
combo (see matchup_grid.json / build_matchup_grid.py). No real daily-seed
infra yet -- every /session/start draws a fresh random matchup.
"""
import json
import random
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game_session import GameSession

with open("matchup_grid.json") as f:
    _GRID = json.load(f)

_ARCHETYPES = _GRID["archetypes"]
_DEFICIT_WEIGHTS = _GRID["deficit_weights"]
_VIABLE_COMBOS = _GRID["viable_combos_by_deficit"]

# §3.7's locked 4-tier roster -- the only combos with a validated mean
# win% benchmark. Dev-mode draws can land on other non-dead combos from the
# extended grid (matchup_grid.json) that were never assigned a named tier
# or a benchmark number; the client shows "no locked-tier benchmark" for those.
LOCKED_TIERS = {
    (3, 30, 65): {"name": "Easy", "mean_win_pct": 79.3},
    (1, 60, 50): {"name": "Medium", "mean_win_pct": 54.7},
    (3, 30, 50): {"name": "Hard", "mean_win_pct": 21.7},
    (1, 60, 35): {"name": "Longshot", "mean_win_pct": 4.2},
}

app = FastAPI()
SESSIONS: dict[str, dict] = {}  # session_id -> {"session": GameSession, "matchup": {...}}
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


def draw_matchup():
    archetype_name = random.choice(list(_ARCHETYPES.keys()))
    tendency = _ARCHETYPES[archetype_name]["tendency"]
    disguise_rate = _ARCHETYPES[archetype_name]["disguise_rate"]

    deficits, weights = zip(*_DEFICIT_WEIGHTS.items())
    deficit = int(random.choices(deficits, weights=weights, k=1)[0])

    combo = random.choice(_VIABLE_COMBOS[str(deficit)])
    return {
        "archetype": archetype_name,
        "tendency": tendency,
        "disguise_rate": disguise_rate,
        "deficit": deficit,
        "time_budget": combo["time_budget"],
        "start_yardline": combo["start_yardline"],
    }


class PlayRequest(BaseModel):
    play: str


class KickChoiceRequest(BaseModel):
    go_for_two: bool


@app.post("/session/start")
def start_session():
    matchup = draw_matchup()
    session_id = str(uuid.uuid4())
    gs = GameSession(
        tendency=matchup["tendency"],
        disguise_rate=matchup["disguise_rate"],
        start_yardline=matchup["start_yardline"],
        time_budget=matchup["time_budget"],
        deficit=matchup["deficit"],
    )
    state = gs.start()
    SESSIONS[session_id] = {"session": gs, "matchup": matchup}
    tier = LOCKED_TIERS.get((matchup["deficit"], matchup["time_budget"], matchup["start_yardline"]))
    return {
        "session_id": session_id,
        "matchup": {
            "archetype": matchup["archetype"],
            "deficit": matchup["deficit"],
            "time_budget": matchup["time_budget"],
            "start_yardline": matchup["start_yardline"],
            "tier": tier,  # null if this combo isn't one of the 4 locked/benchmarked tiers
        },
        "state": state,
    }


def _get_session(session_id: str) -> GameSession:
    entry = SESSIONS.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown session_id")
    return entry["session"]


@app.post("/session/{session_id}/play")
def submit_play(session_id: str, body: PlayRequest):
    gs = _get_session(session_id)
    if gs.done:
        raise HTTPException(status_code=409, detail="drive is already over")
    if gs.pending_kick_choice:
        raise HTTPException(status_code=409, detail="deficit=7 kick-vs-2pt decision pending, call /kick-choice first")
    outcome = gs.call_play(body.play)
    return outcome


@app.post("/session/{session_id}/kick-choice")
def submit_kick_choice(session_id: str, body: KickChoiceRequest):
    gs = _get_session(session_id)
    if not gs.pending_kick_choice:
        raise HTTPException(status_code=409, detail="no kick-vs-2pt decision pending")
    outcome = gs.resolve_kick_choice(body.go_for_two)
    return outcome


@app.get("/session/{session_id}/state")
def get_state(session_id: str):
    gs = _get_session(session_id)
    return gs._state()
