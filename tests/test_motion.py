import unittest
import numpy as np
from src.motion import MotionClock, vocal_active, instrument_activity, playing_pose, body_sway
from src.rhythm import InstrumentChooser
from src.audio_tags import SoundTags, vocal_evidence


class MotionTests(unittest.TestCase):
    def test_dense_attacks_cannot_restart_or_accelerate_head_motion(self):
        clock=MotionClock();previous=0
        for i in range(1000):
            # Double-tempo estimate and a rapidly shifting onset epoch.
            features=dict(period=.30,confidence=.8,epoch=i*.013,hits=[dict(time=i*.016)])
            beats=clock.advance(i*.016,features)
            self.assertGreaterEqual(beats,previous)
            self.assertLess(beats-previous,.045)
            previous=beats
        self.assertGreaterEqual(clock.period*2,1.19)

    def test_instrumental_tonal_music_does_not_enable_mouth_or_auto_microphone(self):
        features=dict(music=True,tag_ready=True,vocal=.01,keyboard=.8,guitar=.02,
                      mids=.7,tonality=.1,confidence=.6)
        self.assertFalse(vocal_active(features))
        self.assertFalse(instrument_activity('microphone',features))
        chooser=InstrumentChooser();chooser.choose(features,0)
        self.assertEqual(chooser.choose(features,7),'keyboard')
        self.assertTrue(instrument_activity('keyboard',features))

    def test_yamnet_silence_and_tone_do_not_report_singing(self):
        model=SoundTags()
        for waveform in (np.zeros(16000,dtype=np.float32),
                         (.1*np.sin(2*np.pi*440*np.arange(16000)/16000)).astype(np.float32)):
            scores=model.classify(waveform)
            self.assertTrue(scores['tag_ready'])
            self.assertLess(scores['vocal'],.12)

    def test_missing_or_stale_classifier_keeps_microphone_closed(self):
        self.assertFalse(vocal_active(dict(music=True,vocal=.9,tag_ready=False)))

    def test_low_instrument_confidence_cannot_freeze_accompaniment_or_body(self):
        features=dict(music=True,tag_ready=True,guitar=.0001,keyboard=.0001,drums=.0001,vocal=0.)
        clock=MotionClock()
        clock.beats=1
        for instrument in ('drums','guitar','keyboard','microphone'):
            first=playing_pose(clock,instrument,features)
            clock.beats+=1
            self.assertNotEqual(first,playing_pose(clock,instrument,features))
        self.assertFalse(vocal_active(features))
        self.assertEqual(playing_pose(clock,'guitar',dict(music=False)),0)
        self.assertEqual(body_sway(8),2)
        self.assertEqual(body_sway(24),-2)

    def test_spoken_vocals_need_music_evidence_but_instrumental_does_not_sing(self):
        for speech,music,expected in ((.16,.17,True),(.9,.01,False),(.01,.9,False)):
            values=vocal_evidence(dict(vocal=.003,speech=speech,music_tag=music))
            values.update(music=True,tag_ready=True)
            self.assertEqual(vocal_active(values),expected)


if __name__=='__main__':unittest.main()
