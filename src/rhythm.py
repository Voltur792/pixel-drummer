"""Causal audio analysis. All timestamps are seconds on a monotonic clock.

No audio is stored. A beat estimate is a prediction, never a claim that an
ambiguous recording has a uniquely correct musical beat.
"""
from collections import deque
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class Hit:
    time: float
    kind: str
    strength: float


class BeatClock:
    def __init__(self):
        self.onsets = deque(maxlen=48)
        self.period = 0.5
        self.epoch = 0.0
        self.confidence = 0.0
        self.last_fit = -math.inf
        self.errors = deque(maxlen=64)
        self.flux_history = deque(maxlen=800)
        self.last_flux_fit = -math.inf
        self.flux_locked = False

    def observe_flux(self, flux, timestamp, duration=.01):
        self.flux_history.append(float(flux))
        if len(self.flux_history)<300 or timestamp-self.last_flux_fit<.5:
            return
        self.last_flux_fit=timestamp
        envelope=np.log1p(np.array(self.flux_history)*4)
        envelope-=np.mean(envelope)
        power=float(np.dot(envelope,envelope))
        if power<.01:
            self.confidence*=.9
            return
        size=1<<(2*len(envelope)-1).bit_length()
        transform=np.fft.rfft(envelope,size)
        correlation=np.fft.irfft(transform*np.conj(transform),size)[:len(envelope)]
        low=max(1,round(.30/duration));high=min(len(envelope)//3,round(1.0/duration))
        peaks=[lag for lag in range(low,high) if correlation[lag]>=correlation[lag-1] and correlation[lag]>=correlation[lag+1]]
        if not peaks:return
        def score(lag):
            normalized=correlation[lag]/max(1e-9,power*(1-lag/len(envelope)))
            continuity=.07*abs(math.log(lag*duration/self.period))
            return normalized-continuity
        best=max(peaks,key=score)
        quality=score(best)
        if quality>.17:
            # Parabolic interpolation avoids a tempo constrained to 10ms bins.
            left,centre,right=correlation[best-1:best+2]
            offset=.5*(left-right)/min(-1e-9,left-2*centre+right)
            fitted=(best+max(-.5,min(.5,float(offset))))*duration
            self.period=fitted if not self.flux_locked else self.period*.65+fitted*.35
            self.confidence=min(1,max(0,quality))
            self.flux_locked=True

    def onset(self, timestamp):
        if self.onsets and timestamp - self.onsets[-1] < 0.10:
            return
        if self.onsets and timestamp - self.onsets[-1] > 3:
            self.onsets.clear()
            self.confidence = 0
        self.onsets.append(timestamp)
        if len(self.onsets) == 1:
            self.epoch = timestamp
            return
        times = np.array(self.onsets)
        # IOIs include subdivisions and skipped beats. Score candidates against
        # the entire recent grid, rather than treating every attack as a beat.
        if not self.flux_locked and timestamp - self.last_fit > 0.45 and len(times) >= 4:
            diffs = np.diff(times)
            candidates = sorted({round(float(d * factor), 4)
                                 for d in diffs for factor in (0.5, 1, 2)
                                 if 0.30 <= d * factor <= 1.0})
            if candidates:
                def score(period):
                    phases = (times - times[-1]) / period
                    error = np.abs(phases - np.round(phases))
                    coverage = min(1.0, period / max(float(np.median(diffs)), .001))
                    continuity = .025 * abs(math.log(period / self.period))
                    return float(np.mean(np.minimum(error, .25))) + .045 * (1-coverage) + continuity
                best = min(candidates, key=score)
                error = score(best)
                self.period = best
                self.confidence = max(0.0, min(1.0, (1-error/.15) * min(1, len(times)/8)))
                # Re-anchor on a measured attack, so an old epoch cannot drift
                # through a tempo change. Phase zero is an actual transient.
                self.epoch = timestamp
                self.last_fit = timestamp
        elif self.confidence > .3:
            expected = self.epoch + round((timestamp-self.epoch)/self.period)*self.period
            error = timestamp-expected
            if abs(error) < self.period*.22:
                self.errors.append(abs(error))
                self.epoch += error*.5

    def phase(self, now):
        return (now-self.epoch)/self.period


class Analyzer:
    """10 ms hops; spectral flux plus amplitude attacks, three hit bands."""
    def __init__(self, sample_rate=48000, hop=480):
        self.sr, self.hop = sample_rate, hop
        self.window = np.hanning(2048)
        self.buffer = np.zeros(2048)
        self.previous = np.zeros(1025)
        self.frequencies = np.fft.rfftfreq(2048, 1/sample_rate)
        self.fluxes = deque(maxlen=100)
        self.clock = BeatClock()
        self.hits = deque(maxlen=64)
        self.last_hit = -math.inf
        self.last_audible = -math.inf
        self.active_since = None
        self.rms = 0.0
        self.previous_rms = 0.0
        self.energy = np.zeros(3)
        self.music = False
        self.tonality = 0.0
        self.centroid = 0.0

    def feed(self, samples, end_time):
        samples = np.asarray(samples, dtype=float)
        if samples.ndim > 1:
            # Do not average opposite-phase stereo to silence.
            channel = int(np.argmax(np.mean(samples*samples, axis=0)))
            samples = samples[:, channel]
        n = len(samples)
        if not n:
            return None
        self.buffer = np.concatenate((self.buffer, samples))[-2048:]
        magnitude = np.abs(np.fft.rfft(self.buffer*self.window))
        delta = np.maximum(0, magnitude-self.previous)
        flux = float(np.sqrt(np.mean(delta*delta)))
        baseline = float(np.median(self.fluxes)) if self.fluxes else 0
        self.fluxes.append(flux)
        self.clock.observe_flux(flux,end_time,n/self.sr)
        rms = float(np.sqrt(np.mean(samples*samples)))
        bands = [(30, 250), (250, 2400), (2400, 15000)]
        energy = np.array([float(np.sum(magnitude[(self.frequencies>=lo)&(self.frequencies<hi)]**2)) for lo,hi in bands])
        self.energy = .96*self.energy + .04*energy
        positive = magnitude[2:]
        self.tonality = float(np.max(positive)/(np.sum(positive)+1e-9))
        self.centroid = float(np.dot(magnitude,self.frequencies)/(np.sum(magnitude)+1e-9))
        if rms > .003:
            self.last_audible = end_time
            if self.active_since is None:
                self.active_since = end_time
        if end_time-self.last_audible > 1.8:
            self.active_since = None
            self.music = False
            self.clock.confidence *= .98
        elif self.active_since is not None:
            recent_hits = sum(end_time-h.time < 3 for h in self.hits)
            # Reject isolated notification sounds; sustained tonal passages are
            # allowed even before a reliable tempo becomes available.
            self.music = end_time-self.active_since > .8 and (recent_hits>=3 or end_time-self.active_since>2.5)
        attack = rms > max(.006, self.previous_rms*1.45)
        spectral_attack = flux > max(.03, baseline*2.3)
        hit = None
        if rms>.003 and (attack or spectral_attack) and end_time-self.last_hit>.115:
            # Locate the transient within this hop, not at an arbitrary UI poll.
            crossing = np.flatnonzero(np.abs(samples)>max(.012, self.previous_rms*2))
            offset = int(crossing[0]) if len(crossing) else n//2
            stamp = end_time-(n-offset)/self.sr
            flux_bands = [float(np.sum(delta[(self.frequencies>=lo)&(self.frequencies<hi)])) for lo,hi in bands]
            kind = ('kick','snare','cymbal')[int(np.argmax(flux_bands))]
            hit = Hit(stamp, kind, min(1.0, max(.25, rms*7)))
            self.hits.append(hit)
            self.last_hit = stamp
            self.clock.onset(stamp)
        self.previous, self.previous_rms, self.rms = magnitude, rms, rms
        return hit

    def snapshot(self, now):
        total = float(np.sum(self.energy))+1e-9
        return dict(music=self.music, rms=self.rms, bpm=60/self.clock.period,
                    confidence=self.clock.confidence, epoch=self.clock.epoch,
                    period=self.clock.period, hits=[h.__dict__ for h in self.hits if now-h.time<.65],
                    bass=float(self.energy[0]/total), mids=float(self.energy[1]/total),
                    highs=float(self.energy[2]/total), tonality=self.tonality,
                    centroid=self.centroid)


class InstrumentChooser:
    """Conservative spectral heuristic, not vocal separation or genre tagging."""
    def __init__(self):
        self.current = 'drums'
        self.candidate = None
        self.candidate_since = 0
        self.last_change = -math.inf

    def choose(self, features, now, override='auto'):
        if override in ('drums','guitar','microphone','keyboard'):
            self.current = override
            return override
        if features.get('tag_ready') and features.get('vocal',0)>.14:
            wanted = 'microphone'
        elif features.get('tag_ready') and features.get('keyboard',0)>.20 and features.get('keyboard',0)>features.get('guitar',0):
            wanted = 'keyboard'
        elif features.get('tag_ready') and features.get('guitar',0)>.18:
            wanted = 'guitar'
        elif features.get('confidence',0)>.65 and features.get('bass',0)>.22:
            wanted = 'drums'
        elif features.get('mids',0)>.45 and features.get('highs',0)>.09:
            wanted = 'guitar'
        elif features.get('tonality',0)>.035 and features.get('mids',0)>.25:
            wanted = 'keyboard'
        else:
            wanted = 'drums'
        if wanted != self.candidate:
            self.candidate, self.candidate_since = wanted, now
        delay = 2 if self.current=='microphone' and wanted!='microphone' else 6
        if now-self.candidate_since >= delay and (now-self.last_change >= 16 or self.current=='microphone' and wanted!='microphone'):
            self.current, self.last_change = wanted, now
        return self.current
