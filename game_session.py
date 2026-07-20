import random
from sim import resolve_yards, true_key_for_situation, show_signal, FG_RANGE_YARDLINE, FG_MAKE_RATE
from scenario import clock_cost, resolve_touchdown

# MAX_PLAYS: scenario.py's run_scenario_drive hardcodes this same cap as a bare
# literal (25) rather than a named constant -- nothing to import it from yet.
MAX_PLAYS = 25


class GameSession:
    """Stateful, one-play-at-a-time version of run_scenario_drive (scenario.py),
    for a client that shows the defensive signal and waits for a human-picked
    play instead of calling a strategy function in a loop."""

    def __init__(self, tendency, disguise_rate, start_yardline, time_budget, deficit):
        self.tendency = tendency
        self.disguise_rate = disguise_rate
        self.deficit = deficit

        self.yard_line = start_yardline
        self.down = 1
        self.distance = 10
        self.clock = time_budget
        self.plays_run = 0
        self.points = 0
        self.done = False
        self.result = None

        self._true_key = None
        self._signal = None

    def _next_signal(self):
        self._true_key = true_key_for_situation(self.down, self.distance, self.tendency)
        self._signal = show_signal(self._true_key, self.disguise_rate)

    def _state(self):
        return {
            "down": self.down,
            "distance": self.distance,
            "yard_line": self.yard_line,
            "clock": max(self.clock, 0),
            "signal": self._signal,
            "done": self.done,
            "result": self.result,
            "points": self.points,
        }

    def start(self):
        self._next_signal()
        return self._state()

    def _finish(self, points):
        self.points = points
        self.done = True
        self.result = "WIN" if points > self.deficit else ("TIE" if points == self.deficit else "LOSS")

    def call_play(self, play):
        if self.done:
            raise RuntimeError("drive is already over")

        self.plays_run += 1
        true_key, signal = self._true_key, self._signal
        yards, turnover = resolve_yards(play, true_key, self.yard_line)
        self.clock -= clock_cost(play, yards)

        outcome = {
            "play": play,
            "true_key": true_key,
            "signal": signal,
            "yards": yards,
            "turnover": turnover,
        }

        if turnover:
            self._finish(-2)
        else:
            self.yard_line += yards
            if self.yard_line >= 100:
                self._finish(resolve_touchdown(self.deficit))
            elif yards >= self.distance:
                self.down, self.distance = 1, 10
            else:
                self.distance -= yards
                self.down += 1
                if self.down > 4:
                    points = 3 if (self.yard_line >= FG_RANGE_YARDLINE and random.random() < FG_MAKE_RATE) else 0
                    self._finish(points)

            if not self.done and self.clock <= 0:
                points = 3 if (self.yard_line >= FG_RANGE_YARDLINE and random.random() < FG_MAKE_RATE) else 0
                self._finish(points)
            elif not self.done and self.plays_run >= MAX_PLAYS:
                self._finish(0)

        if not self.done:
            self._next_signal()

        outcome.update(self._state())
        return outcome
