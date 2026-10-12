"""Render both real widgets with controlled PCM analysis, without OS input."""
import json
import os
from pathlib import Path
import sys
import time
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtGui import QImage, QPainter, QRegion
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication
from src.renderer import Companion
from src.concert import ACTOR_Y, FLOOR_Y


def canvas(widget):
    image=QImage(widget.size(),QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image,QPoint(),QRegion(),widget.RenderFlag.DrawWindowBackground|widget.RenderFlag.DrawChildren|widget.RenderFlag.IgnoreMask)
    return image


app=QApplication([])
with TemporaryDirectory(prefix='pixel-music-visuals-') as directory:
    owner=Companion(directory,os.getpid(),'visual-check',demo=True)
    owner.timer.stop();owner.audio.stop_event.set();owner.audio.tags.stop_event.set()
    owner.desktop.observer.stop_event.set()
    now=time.monotonic()
    owner.features=dict(music=True,tag_ready=True,vocal=0.,guitar=.0001,keyboard=.0001,drums=.0001,hits=[])
    owner.stage.state='play';owner.visible=False
    owner.concert.started=now-5
    pairs=[]
    for beats in (1,1.125,1.25,1.5,1.75,2,2.5):
        owner.motion.beats=beats
        owner.concert.tick(True,now,True)
        pairs.append(canvas(owner.concert))
    for number,instrument in enumerate(owner.loops):
        x=(43+number*61-32)*4
        # Includes body/feet, excludes head and most flying notes.
        assert any(pairs[0].copy(x,(ACTOR_Y+28)*4,256,24*4)!=other.copy(x,(ACTOR_Y+28)*4,256,24*4) for other in pairs[1:]),instrument
    assert ACTOR_Y+51==FLOOR_Y
    assert {e['instrument'] for e in owner.concert.effects}=={'drums','guitar','keyboard'}
    owner.motion.beats=2.5
    for instrument in owner.loops:
        owner.stage.instrument=instrument
        owner.features['vocal']=.16 if instrument=='microphone' else 0.
        owner.features['hits']=[dict(time=now,kind='cymbal',strength=.8)]
        owner.last_effect_time=-float('inf');owner.last_note_beat=None
        owner.frame=owner.performance(now)
        owner.effects=False
        plain=canvas(owner)
        owner.effects=True
        decorated=canvas(owner)
        assert decorated!=plain,instrument+' effects missing in single mode'
    # The exact microphone pose changes only face pixels when voice appears.
    pose=owner.motion.pose('microphone')
    def face(vocal):
        owner.features['vocal']=vocal
        image=QImage(64,64,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image)
        owner.draw_performer(painter,owner.loops['microphone'][pose],'microphone',pose)
        painter.end()
        return image
    assert face(0)!=face(.16)
    owner.features['vocal']=.16
    owner.concert.last_note=None;owner.concert.tick(True,now,True)
    assert any(e['instrument']=='microphone' for e in owner.concert.effects)
    owner.effects=False;plain=canvas(owner.concert)
    owner.effects=True;decorated=canvas(owner.concert)
    for number,instrument in enumerate(owner.loops):
        x=(43+number*61-32)*4
        assert plain.copy(x,ACTOR_Y*4,256,256)!=decorated.copy(x,ACTOR_Y*4,256,256),instrument+' stage effects missing'
    (ROOT/'data').mkdir(exist_ok=True)
    decorated.save(str(ROOT/'data/concert-visual-check-v0.4.1.png'))
    result=dict(all_four_bodies_move=True,boots_touch_stage=True,single_effects_all_four=True,
                concert_effects_all_four=True,mouth_requires_voice=True,low_confidence_keeps_motion=True)
    (ROOT/'data/verification-visuals-v0.4.1.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    owner.hide();owner.concert.hide()
