"""Exercise read-only desktop play and the real mouse handler in an isolated GUI."""
import json
import os
from pathlib import Path
import sys
import time
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from src.renderer import Companion


def pump(app,seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        app.processEvents();time.sleep(.01)


app=QApplication([])
with TemporaryDirectory(prefix='pixel-desktop-check-') as directory:
    owner=Companion(directory,os.getpid(),'desktop-check',demo=True)
    owner.mode='walk';owner.visible=False
    pump(app,1.5)
    desk=owner.desktop
    assert desk.observer.snapshot() and not desk.observer.error
    windows=desk.surfaces(time.monotonic())
    assert windows,'No exposed usable window edge'
    assert desk.climb(time.monotonic())
    target=owner.walker.waypoints[-1]
    # Position near the chosen edge so this regression does not traverse the
    # user's entire desktop; the actual renderer performs the remaining hop.
    owner.walker.position=(target[0],target[1]+120)
    owner.walker.set_route([target])
    pump(app,1.1)
    assert desk.phase=='perched',desk.phase
    desk.perch_until=time.monotonic()-1
    pump(app,.15)
    assert desk.perch is None
    owner.walker.stop()
    assert desk.borrow(3)
    origin=desk.borrowed[0]['origin']
    owner.walker.position=(origin[0]-24,origin[1]+52)
    owner.walker.stop()
    pump(app,.1)
    assert desk.phase=='running' and len(desk.borrowed)==3
    # Real Qt event dispatch reaches Companion.mousePressEvent (no OS input).
    QTest.mousePress(owner,Qt.MouseButton.LeftButton,pos=QPoint(128,128))
    assert not desk.borrowed and len(desk.flights)==3
    QTest.mouseRelease(owner,Qt.MouseButton.LeftButton,pos=QPoint(128,128))
    pump(app,1.3)
    assert not desk.flights
    assert desk.borrow(1)
    desk.tick(time.monotonic(),True)
    assert not desk.borrowed
    owner.audio.stop_event.set();owner.audio.tags.stop_event.set();desk.observer.stop_event.set()
    owner.timer.stop();owner.hide();owner.concert.hide()
    print(json.dumps(dict(window_edges=len(windows),climb=True,perch=True,descent=True,
                          three_copies=True,mouse_catch=True,animated_return=True,
                          music_returns_copy=True),indent=2))
