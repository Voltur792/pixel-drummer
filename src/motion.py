"""Continuous musical movement. Transients never reset head/body phase."""
import math


class MotionClock:
    def __init__(self):
        self.beats = 0.
        self.period = .6
        self.last = None

    def advance(self, now, features):
        dt = 0 if self.last is None else min(.1, max(0., now-self.last))
        self.last = now
        target = max(.30, min(1., float(features.get('period', .6))))
        # Prefer a calm 60–150 BPM pulse over hi-hat subdivisions/double tempo.
        while target < .4: target *= 2
        confidence = features.get('confidence', 0)
        if confidence > .3:
            self.period += (target-self.period)*min(1, dt*.8)
        self.beats += dt/self.period
        if confidence>.35:
            reference=(now-float(features.get('epoch',now)))/target
            error=(reference-self.beats+.5)%1-.5
            if abs(error)<.25:self.beats+=error*min(.05,dt*.4)
        return self.beats

    def pose(self, instrument):
        cycle = self.beats if instrument == 'drums' else self.beats/2
        return int(cycle*16)%192

    def head_pose(self):
        return int((self.beats/2 % 1)*32)%32


def vocal_active(features):
    return bool(features.get('music') and features.get('tag_ready') and
                features.get('vocal', 0) >= .12)


def body_sway(pose):
    return round(2*math.sin(pose/32*2*math.pi))


def playing_pose(clock,instrument,features):
    # Classification controls accents and vocals, never freezes the body or
    # the accompaniment when a mixed/quiet song isn't confidently identified.
    return clock.pose(instrument) if features.get('music') else 0


def instrument_activity(instrument, features):
    if instrument == 'microphone': return vocal_active(features)
    if not features.get('music'): return False
    if not features.get('tag_ready'): return True
    key = {'guitar':'guitar', 'keyboard':'keyboard', 'drums':'drums'}[instrument]
    return features.get(key, 0) >= .10 or (instrument == 'drums' and features.get('bass', 0) > .22)
