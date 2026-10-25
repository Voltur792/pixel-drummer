import math
import hashlib
import tomllib
from pathlib import Path
import unittest
import numpy as np
from PIL import Image
from src.rhythm import Analyzer, BeatClock, InstrumentChooser
from src.stage import Screen, Stage, Walker, route
from src.motion import body_sway

ROOT=Path(__file__).resolve().parents[1]


class RhythmTests(unittest.TestCase):
    def test_detected_attacks_follow_pcm_timestamps_and_stop_on_silence(self):
        sr=48000
        expected=np.arange(.5,8,.5)
        pcm=np.zeros(sr*10)
        rng=np.random.default_rng(9)
        for stamp in expected:
            start=round(stamp*sr)
            t=np.arange(2400)/sr
            burst=(.4*np.sin(2*math.pi*90*t)+.04*rng.standard_normal(len(t)))*np.exp(-t*80)
            pcm[start:start+len(t)]=burst
        analyzer=Analyzer()
        hits=[]
        for start in range(0,len(pcm),480):
            hit=analyzer.feed(pcm[start:start+480],(start+480)/sr)
            if hit:hits.append(hit.time)
        self.assertEqual(len(hits),len(expected))
        errors=np.abs(np.array(hits)-expected)
        self.assertLess(float(np.max(errors)),.015)
        self.assertAlmostEqual(60/analyzer.clock.period,120,delta=1)
        self.assertFalse(analyzer.music)

    def test_stereo_antiphase_does_not_disappear(self):
        a=Analyzer()
        signal=np.sin(np.arange(480)*.15)*.2
        a.feed(np.column_stack((signal,-signal)),1)
        self.assertGreater(a.rms,.1)

    def test_clock_reacquires_after_tempo_change_and_handles_subdivision(self):
        clock=BeatClock()
        for stamp in np.arange(0,6,.5):clock.onset(float(stamp))
        self.assertAlmostEqual(clock.period,.5,delta=.01)
        for stamp in np.arange(6,24,.4):clock.onset(float(stamp))
        self.assertAlmostEqual(clock.period,.4,delta=.015)
        self.assertGreater(clock.confidence,.6)
        self.assertLess(abs(clock.phase(clock.epoch)-round(clock.phase(clock.epoch))),.001)

    def test_instrument_selection_requires_stability_and_dwell(self):
        chooser=InstrumentChooser()
        guitar=dict(mids=.65,highs=.18,bass=.17,confidence=.3,tonality=.01)
        self.assertEqual(chooser.choose(guitar,0),'drums')
        self.assertEqual(chooser.choose(guitar,5),'drums')
        self.assertEqual(chooser.choose(guitar,7),'guitar')
        voice=dict(mids=.8,highs=.03,bass=.17,confidence=.2,tonality=.09,tag_ready=True,vocal=.8)
        chooser.choose(voice,8)
        self.assertEqual(chooser.choose(voice,15),'guitar')
        self.assertEqual(chooser.choose(voice,29),'microphone')
        self.assertEqual(chooser.choose(voice,30,'drums'),'drums')


class StageTests(unittest.TestCase):
    def test_music_stop_and_instrument_switch_have_put_away_transitions(self):
        stage=Stage()
        self.assertEqual(stage.update(10,True,'drums'),'take_out')
        self.assertEqual(stage.transition_frame(10),0)
        self.assertEqual(stage.update(12,True,'drums'),'play')
        self.assertEqual(stage.update(13,True,'guitar'),'put_away')
        self.assertEqual(stage.instrument,'drums')
        self.assertEqual(stage.update(15,True,'guitar'),'take_out')
        self.assertEqual(stage.instrument,'guitar')
        self.assertEqual(stage.update(17,False,'guitar'),'put_away')
        self.assertEqual(stage.update(19,False,'guitar'),'idle')

    def test_walks_across_negative_coordinates_and_unequal_floor_without_jump(self):
        a=Screen('left',-1920,0,1920,1080,1039)
        b=Screen('right',0,0,2560,1440,1391)
        walker=Walker((-300,1039))
        walker.set_route(route(walker.position,a,b))
        previous=walker.position
        saw_air=False
        for i in range(7000):
            moving=walker.advance(i/60,1/60)
            distance=math.dist(previous,walker.position)
            self.assertLess(distance,10)
            saw_air |= walker.airborne
            previous=walker.position
            if not moving:break
        self.assertTrue(saw_air)
        self.assertTrue(b.contains(walker.position))
        self.assertEqual(walker.position[1],b.floor)
        self.assertLess(i,6999)

    def test_stopping_walk_freezes_position(self):
        walker=Walker((40,100))
        walker.set_route([(400,100)])
        walker.advance(1,.1)
        point=walker.position
        walker.stop()
        self.assertFalse(walker.advance(10,.1))
        self.assertEqual(walker.position,point)


class ArtTests(unittest.TestCase):
    def test_native_hide_heartbeat_restarts_distinct_clips_with_timed_recovery(self):
        graph=tomllib.loads((ROOT/'src/resources/assets/pack/animpacks/pixel-band-proxy/animpack.toml').read_text(encoding='utf-8'))
        states=[graph['states']['stage_hidden_'+side] for side in ('a','b')]
        self.assertNotEqual(states[0]['clip'],states[1]['clip'])
        clips={clip['name']:clip for clip in graph['clips']}
        self.assertNotEqual(clips[states[0]['clip']]['file'],clips[states[1]['clip']]['file'])
        for state in states:
            self.assertFalse(state['loop'])
            self.assertIn(dict(on='clip_finished',to='idle'),state['transitions'])
            # Outlasts a hidden window's one-a-minute timer, still ends on its own.
            self.assertEqual(clips[state['clip']]['frames']/clips[state['clip']]['fps'],144)
        self.assertEqual(graph['states']['default'],'idle')
    def test_authentic_idle_and_walk_are_copied_without_repainting(self):
        native_hashes={'idle':'797c28186438a2aa5de9faa5beeac93b75b6dccb4978dc936f7a37372157471e',
                       'walk':'5dfa85e9aab3dfb538fdacb7cc6d33855b7eb279da55f635c52378d7d67165e7'}
        for name,digest in native_hashes.items():
            self.assertEqual(hashlib.sha256((ROOT/f'src/resources/assets/band/{name}.png').read_bytes()).hexdigest(),digest)

    def test_loop_geometry_and_intro_contact_match_for_every_instrument(self):
        heads=Image.open(ROOT/'src/resources/assets/band/heads.png').convert('RGBA')
        for instrument in ('drums','guitar','microphone','keyboard'):
            loop=Image.open(ROOT/f'src/resources/assets/band/{instrument}-loop.png').convert('RGBA')
            intro=Image.open(ROOT/f'src/resources/assets/band/{instrument}-in.png').convert('RGBA')
            self.assertEqual(loop.size,(1024,768))
            last=intro.crop((15*64,64,16*64,128))
            first=loop.crop((0,0,64,64))
            composed=first.copy();composed.alpha_composite(heads.crop((0,0,64,64)))
            self.assertTrue(last.tobytes()==composed.tobytes(),instrument)
            poses=set()
            for i in range(16):
                frame=loop.crop((i*64,0,(i+1)*64,64))
                poses.add(frame.tobytes())
                if instrument=='drums':self.assertTrue(frame.crop((0,48,64,64)).tobytes()==first.crop((0,48,64,64)).tobytes())
            self.assertGreater(len(poses),5)

    def test_face_uses_original_colours_and_preserves_eye_pixels(self):
        base=Image.open(ROOT/'src/resources/assets/band/idle.png').convert('RGBA').crop((0,0,64,64))
        colours=set(base.crop((21,15,45,32)).get_flattened_data())
        sheet=Image.open(ROOT/'src/resources/assets/band/heads.png').convert('RGBA')
        for i in range(16):
            cell=sheet.crop((i*64,0,(i+1)*64,64))
            region=cell.crop((22,16,44,32))
            self.assertTrue(set(region.get_flattened_data()).issubset(colours))
        # Nod changes the head's position, never the instrument's lower pixels.
        self.assertNotEqual(sheet.crop((21,0,45,34)).tobytes(),sheet.crop((8*64+21,0,8*64+45,34)).tobytes())

    def test_visible_heel_lift_keeps_other_foot_on_the_floor(self):
        sheet=Image.open(ROOT/'src/resources/assets/band/guitar-loop.png').convert('RGBA')
        base=sheet.crop((0,0,64,64));lift=sheet.crop((4*64,0,5*64,64))
        dx=body_sway(4)
        self.assertEqual(base.getpixel((29,51)),lift.getpixel((29+dx,49)))
        self.assertGreater(lift.getpixel((34+dx,51))[3],0)
        self.assertEqual(lift.getpixel((29+dx,51))[3],0)

    def test_keyboard_keys_are_on_player_side_of_control_panel(self):
        sheet=Image.open(ROOT/'src/resources/assets/band/keyboard-loop.png').convert('RGBA')
        frame=sheet.crop((0,0,64,64))
        self.assertEqual(frame.getpixel((16,39))[:3],(238,232,242))
        self.assertEqual(frame.getpixel((16,42))[:3],(189,83,109))


if __name__=='__main__':unittest.main()
