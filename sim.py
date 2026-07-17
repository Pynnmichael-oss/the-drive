import random

PLAYS = ["RUN", "PASS_SHORT", "PASS_DEEP"]
KEYS  = ["KEY_RUN", "KEY_SHORT", "KEY_DEEP"]

BEATS = {"RUN": "KEY_RUN", "PASS_SHORT": "KEY_SHORT", "PASS_DEEP": "KEY_DEEP"}
GOOD_VS = {"RUN": "KEY_DEEP", "PASS_SHORT": "KEY_RUN", "PASS_DEEP": "KEY_RUN"}

def matchup(play, true_key):
    if BEATS[play] == true_key:
        return "bad"
    if GOOD_VS[play] == true_key:
        return "good"
    return "neutral"

def resolve_yards(play, true_key, yard_line=0):
    m = matchup(play, true_key)
    turnover = False
    if play == "RUN":
        mean, sd = {"good": (8, 4), "neutral": (4, 3), "bad": (1, 3)}[m]
        yards = random.gauss(mean, sd)
        if m == "bad" and random.random() < 0.04:
            turnover = True
    elif play == "PASS_SHORT":
        mean, sd = {"good": (7, 3), "neutral": (4, 3), "bad": (1, 3)}[m]
        yards = random.gauss(mean, sd)
    else:
        mean, sd = {"good": (11, 7), "neutral": (3, 6), "bad": (-4, 6)}[m]
        yards = random.gauss(mean, sd)
        if m == "bad" and random.random() < 0.22:
            turnover = True
        elif m == "neutral" and random.random() < 0.08:
            turnover = True
    if yard_line >= 80:  # red zone: less field to work with, defense compresses
        yards *= 0.55
    return round(max(yards, -5)), turnover

def true_key_for_situation(down, distance, tendency):
    w = dict(tendency)
    if down <= 2 and distance >= 7:
        w["KEY_RUN"] *= 1.4
    if distance <= 3:
        w["KEY_RUN"] *= 1.3
    if down >= 3 and distance >= 7:
        w["KEY_DEEP"] *= 1.5
        w["KEY_RUN"] *= 0.6
    total = sum(w.values())
    r, cum = random.random() * total, 0
    for k, val in w.items():
        cum += val
        if r <= cum:
            return k
    return "KEY_SHORT"

def show_signal(true_key, disguise_rate):
    if random.random() > disguise_rate:
        return true_key
    return random.choice([k for k in KEYS if k != true_key])

# §7.5: formation visual schema. Generated from the SHOWN key (post-disguise),
# never the true key -- the player only ever sees what the defense is
# presenting, disguised or not, and finds out the true key at reveal. This is
# a pure rendering-layer addition: play-calling strategies (context_blind,
# trusts_signal, etc.) keep consuming the plain "KEY_RUN"-style string from
# show_signal exactly as before, so nothing balance-tested in §4/§7 is at risk.
#
# Field values below are flavor/creative, not math -- there's no "correct"
# box count for a given look. Retune freely; nothing else depends on the
# specific numbers, only on shell/box_count/safety_depth existing as fields.
FORMATION_PROFILES = {
    "KEY_RUN": {
        "box_count_range": (8, 9),
        "shell_choices": [("no_shell", 0.4), ("single_high", 0.6)],
        "safety_depth_shallow_range": (5, 8),
        "safety_depth_deep_range": (10, 12),
        "blitz_look_rate": 0.5,
    },
    "KEY_SHORT": {
        "box_count_range": (6, 7),
        "shell_choices": [("single_high", 0.7), ("two_high", 0.3)],
        "safety_depth_shallow_range": (4, 7),
        "safety_depth_deep_range": (10, 13),
        "blitz_look_rate": 0.1,
    },
    "KEY_DEEP": {
        "box_count_range": (5, 6),
        "shell_choices": [("two_high", 0.75), ("single_high", 0.25)],
        "safety_depth_shallow_range": (6, 9),
        "safety_depth_deep_range": (12, 16),
        "blitz_look_rate": 0.05,
    },
}

def formation_for_signal(shown_key):
    """Renderable formation fields for the UI, built from the shown (possibly
    disguised) key. Returns a dict; does NOT feed back into play resolution."""
    profile = FORMATION_PROFILES[shown_key]
    box_count = random.randint(*profile["box_count_range"])

    shells, weights = zip(*profile["shell_choices"])
    shell = random.choices(shells, weights=weights, k=1)[0]
    safety_count = {"no_shell": 0, "single_high": 1, "two_high": 2}[shell]

    if shell == "no_shell":
        safety_depths = []
    elif shell == "single_high":
        safety_depths = [random.randint(*profile["safety_depth_deep_range"])]
    else:  # two_high
        lo, hi = profile["safety_depth_deep_range"]
        safety_depths = [random.randint(lo, hi), random.randint(lo, hi)]

    robber_shown = shell == "single_high" and random.random() < 0.3
    if robber_shown:
        safety_depths.append(random.randint(*profile["safety_depth_shallow_range"]))

    return {
        "box_count": box_count,
        "shell": shell,
        "safety_count": safety_count,
        "safety_depths_yards": safety_depths,
        "blitz_look": random.random() < profile["blitz_look_rate"],
    }

FG_RANGE_YARDLINE = 65
FG_MAKE_RATE = 0.88

# §7.3: single source of truth for PAT rate -- scenario.py imports this rather
# than redefining it, so the base game and scenario mode can never drift apart
# on what "high PAT rate" means.
PAT_MAKE_RATE = 0.94

def run_drive(strategy, tendency, disguise_rate):
    yard_line, down, distance = 20, 1, 10
    plays_run, log = 0, []
    while True:
        plays_run += 1
        true_key = true_key_for_situation(down, distance, tendency)
        signal = show_signal(true_key, disguise_rate)
        play = strategy(down, distance, signal)
        yards, turnover = resolve_yards(play, true_key, yard_line)
        log.append((down, distance, signal, true_key, play, yards, turnover))

        if turnover:
            return {"points": -2, "yards": sum(l[5] for l in log), "plays": plays_run, "log": log}
        yard_line += yards
        if yard_line >= 100:
            made_pat = random.random() < PAT_MAKE_RATE
            points = 6 + (1 if made_pat else 0)
            return {"points": points, "yards": sum(l[5] for l in log), "plays": plays_run, "log": log}
        if yards >= distance:
            down, distance = 1, 10
        else:
            distance -= yards
            down += 1
            if down > 4:
                if yard_line >= FG_RANGE_YARDLINE and random.random() < FG_MAKE_RATE:
                    return {"points": 3, "yards": sum(l[5] for l in log), "plays": plays_run, "log": log}
                return {"points": 0, "yards": sum(l[5] for l in log), "plays": plays_run, "log": log}
        if plays_run >= 20:
            return {"points": 0, "yards": sum(l[5] for l in log), "plays": plays_run, "log": log}

def perfect_reader(down, distance, signal):
    beater = {"KEY_RUN": "PASS_SHORT", "KEY_SHORT": "RUN", "KEY_DEEP": "RUN"}
    good_play = [p for p, k in GOOD_VS.items() if k == signal]
    return good_play[0] if good_play else beater[signal]

def trusts_signal(down, distance, signal):
    return perfect_reader(down, distance, signal)

def always_run(down, distance, signal): return "RUN"
def always_short(down, distance, signal): return "PASS_SHORT"
def always_deep(down, distance, signal): return "PASS_DEEP"
def random_pick(down, distance, signal): return random.choice(PLAYS)

def situational_naive(down, distance, signal):
    if distance <= 3: return "RUN"
    if down >= 3 and distance >= 7: return "PASS_DEEP"
    return "PASS_SHORT"
