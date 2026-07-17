import random
from sim import run_drive, perfect_reader, trusts_signal, situational_naive, always_run, always_short, always_deep, random_pick

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

STRATS = [
    ("Reads signal", trusts_signal, False),
    ("Situational-only", situational_naive, False),
    ("Always Run", always_run, False),
    ("Always Pass Short", always_short, False),
    ("Always Pass Deep", always_deep, False),
    ("Random", random_pick, False),
]

N = 8000
for arch_name, (tendency, disguise) in ARCHETYPES.items():
    print(f"\n=== {arch_name} (disguise={disguise}) ===")
    print(f"{'Strategy':22s} {'Avg pts':>8s} {'Avg yds':>8s} {'TO%':>6s}")
    best = None
    for name, strat, cheat in STRATS:
        pts, yds, to = [], [], 0
        for _ in range(N):
            d = run_drive(strat, tendency, disguise)
            pts.append(d["points"]); yds.append(d["yards"])
            if any(l[6] for l in d["log"]): to += 1
        avg_pts = sum(pts) / N
        print(f"{name:22s} {avg_pts:8.2f} {sum(yds)/N:8.1f} {to/N*100:5.1f}%")
        if best is None or avg_pts > best[1]:
            best = (name, avg_pts)
    flag = "OK — Reads signal wins" if best[0] == "Reads signal" else f"*** WARNING: '{best[0]}' beats reading the signal ***"
    print(f"-> Top strategy: {best[0]} ({best[1]:.2f} pts)  [{flag}]")
