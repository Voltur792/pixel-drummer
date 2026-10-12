"""Small local AudioSet classifier. One CPU thread, no audio files or uploads."""
import csv
from pathlib import Path
import queue
import threading
import time
import numpy as np

MODEL = Path(__file__).resolve().parent / 'resources/models'
GROUPS = {
    'vocal': ('Singing', 'Choir', 'Rapping', 'Child singing', 'Vocal music', 'A capella'),
    'guitar': ('Electric guitar', 'Guitar', 'Acoustic guitar', 'Strum'),
    'keyboard': ('Piano', 'Electric piano', 'Synthesizer', 'Keyboard (musical)', 'Electronic organ'),
    'drums': ('Drum kit', 'Drum machine', 'Drum', 'Snare drum', 'Bass drum', 'Hi-hat', 'Cymbal'),
    'speech': ('Speech', 'Shout', 'Screaming'),
    'music_tag': ('Music',),
}


class SoundTags:
    def __init__(self):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        self.session = ort.InferenceSession(str(MODEL/'yamnet.onnx'), options,
                                           providers=['CPUExecutionProvider'])
        with (MODEL/'yamnet_class_map.csv').open(encoding='utf-8') as stream:
            labels = [row['display_name'] for row in csv.DictReader(stream)]
        self.indices = {key: [labels.index(name) for name in names] for key, names in GROUPS.items()}

    def classify(self, waveform):
        began = time.perf_counter()
        scores = self.session.run(['output_0'], {'waveform': np.asarray(waveform, dtype=np.float32)})[0].max(0)
        result = {key: float(np.max(scores[indices])) for key, indices in self.indices.items()}
        result = vocal_evidence(result)
        result.update(tag_ready=True, tag_ms=round((time.perf_counter()-began)*1000, 2))
        return result


def vocal_evidence(result):
    result=dict(result)
    result['singing']=result.get('vocal',0.)
    # Rap/spoken or harsh vocals may be labelled speech/shout rather than
    # singing. Require the classifier's music evidence for this fallback.
    result['vocal']=max(result['singing'],min(result.get('speech',0.),result.get('music_tag',0.)))
    return result


class TagWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name='local-music-tags')
        self.pending = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.value = dict(tag_ready=False, vocal=0., guitar=0., keyboard=0., drums=0.)

    def submit(self, waveform, timestamp):
        try: self.pending.put_nowait((waveform.copy(), timestamp))
        except queue.Full: pass

    def snapshot(self, now):
        with self.lock: value = dict(self.value)
        if now-value.get('tag_time', 0)>2.5:
            value.update(vocal=0., guitar=0., keyboard=0., drums=0., tag_ready=False)
        return value

    def run(self):
        try:
            classifier = SoundTags()
            while not self.stop_event.is_set():
                try: waveform, stamp = self.pending.get(timeout=.5)
                except queue.Empty: continue
                result = classifier.classify(waveform)
                result['tag_time'] = stamp
                with self.lock: self.value = result
        except Exception as error:
            with self.lock: self.value.update(tag_ready=False, tag_error=str(error))
