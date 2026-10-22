"""Transparent local scene. Audio + paint clocks stay in this process.

Only the default output's loopback is opened, never a physical microphone.
Parent/lease checks and a local stop command prevent orphan companions.
"""
import argparse
from collections import deque
import ctypes
import json
import math
import os
from pathlib import Path
import random
import threading
import time
import warnings

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QMenu, QWidget
from .rhythm import Analyzer, InstrumentChooser
from .stage import Screen, Stage, Walker, route
from .ipc import atomic_json
from .audio_tags import TagWorker
from .motion import MotionClock, vocal_active, instrument_activity, body_sway, playing_pose
from .concert import ConcertWindow
from .desktop_play import DesktopPlay
from .music_effects import draw_effects
from .platform_support import capabilities, process_alive, recording_source

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'src/resources/assets/band'


class Loopback(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True,name='speaker-loopback')
        self.lock=threading.Lock()
        self.stop_event=threading.Event()
        self.value=Analyzer().snapshot(time.monotonic())
        self.value.update(audio_ready=False,audio_error=None)
        self.tags=TagWorker();self.tags.start()

    def snapshot(self):
        with self.lock:
            value=dict(self.value)
        value.update(self.tags.snapshot(time.monotonic()))
        return value

    def run(self):
        while not self.stop_event.is_set():
            try:
                import soundcard as sc
                mic=recording_source(sc)
                analyzer=Analyzer()
                check_device=time.monotonic()
                pending=None
                tag_buffer=np.zeros(0,dtype=np.float32);last_tag=0
                # Shared mode keeps other applications' output available. All
                # channels avoid SoundCard's documented Windows mono issue.
                with mic.recorder(samplerate=48000,blocksize=960,channels=None) as rec:
                    while not self.stop_event.is_set():
                        with warnings.catch_warnings():
                            warnings.simplefilter('ignore',category=RuntimeWarning)
                            pcm=rec.record(numframes=None)
                        now=time.monotonic()
                        mono=pcm[:,int(np.argmax(np.mean(pcm*pcm,axis=0)))] if pcm.ndim>1 else pcm
                        tag_buffer=np.concatenate((tag_buffer,mono))[-48000:]
                        if len(tag_buffer)>=48000 and now-last_tag>=1:
                            last_tag=now
                            taps=np.arange(-24,25);kernel=np.sinc(taps/3)*np.hanning(49);kernel/=kernel.sum()
                            self.tags.submit(np.convolve(tag_buffer,kernel,mode='same')[::3].astype(np.float32),now)
                        pending=pcm if pending is None else np.concatenate((pending,pcm))
                        # Drain the available packet, not a queue of fixed-size
                        # reads whose delivery delay can accumulate. Place each
                        # 10ms analysis hop on this packet's local sample clock.
                        processed=(len(pending)//480)*480
                        for offset in range(0,processed,480):
                            chunk=pending[offset:offset+480]
                            end=now-(len(pending)-offset-len(chunk))/48000
                            analyzer.feed(chunk,end)
                        pending=pending[processed:]
                        snapshot=analyzer.snapshot(now)
                        snapshot.update(audio_ready=True,audio_error=None,
                                        packet_ms=round(len(pcm)/48,2))
                        with self.lock:
                            self.value=snapshot
                        if now-check_device>3:
                            check_device=now
                            if recording_source(sc).id!=mic.id:
                                break
            except Exception as exc:
                with self.lock:
                    self.value.update(music=False,audio_ready=False,audio_error=f'{type(exc).__name__}: {exc}')
                self.stop_event.wait(2)


def sheets(name):
    image=QImage(str(ART/name))
    if image.isNull():
        raise RuntimeError(f'Не удалось загрузить спрайты: {name}')
    return [image.copy(x,y,64,64) for y in range(0,image.height(),64)
            for x in range(0,image.width(),64)]


class Companion(QWidget):
    def __init__(self, data, parent_pid, session, demo=False):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool|
                         Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('Nayu — Pixel Band')
        self.resize(256,256)
        self.data,self.parent_pid,self.session=Path(data),parent_pid,session
        self.demo=demo
        self.audio=Loopback()
        self.audio.start()
        self.idle,self.walk,self.fly=sheets('idle.png'),sheets('walk.png'),sheets('fly.png')
        self.loops={i:sheets(i+'-loop.png') for i in ('drums','guitar','microphone','keyboard')}
        self.heads=sheets('heads.png')
        self.motion=MotionClock();self.pose_index=0
        self.intros={i:sheets(i+'-in.png') for i in self.loops}
        self.stage=Stage();self.chooser=InstrumentChooser()
        self.features=self.audio.snapshot()
        self.started=self.last_frame=time.monotonic()
        self.last_status=self.last_control=0
        self.lease=self.started
        self.mode,self.instrument='auto','auto'
        self.visible=False
        self.platform_features=capabilities()
        self.roam=self.platform_features['screen_walking']
        self.effects=True
        self.head=True
        self.control_revision=None
        self.drag_offset=None
        self.walk_at=self.started+8
        self.visited=[]
        self.effect_history=deque(maxlen=64)
        self.last_effect_time=-math.inf
        self.presentation_errors=deque(maxlen=64)
        self.last_beat=None
        self.last_note_beat=None
        self.last_screen=None
        self.requested_route=None
        self.mask_cache={}
        self.screen_defs=self.screens()
        primary=QApplication.primaryScreen()
        geo=primary.availableGeometry()
        self.walker=Walker((geo.x()+geo.width()*.65,geo.y()+geo.height()-1))
        self.frame=self.idle[0]
        self.concert=ConcertWindow(self)
        self.desktop=DesktopPlay(self)
        self.timer=QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        QApplication.instance().screenAdded.connect(lambda _:self.refresh_screens())
        QApplication.instance().screenRemoved.connect(lambda _:self.refresh_screens())
        for screen in QApplication.screens():
            screen.availableGeometryChanged.connect(lambda _:self.refresh_screens())
        self.tick()

    def screens(self):
        result=[]
        for s in QApplication.screens():
            g=s.geometry(); a=s.availableGeometry()
            result.append(Screen(s.name(),g.x(),g.y(),g.width(),g.height(),a.y()+a.height()-1))
        return result

    def refresh_screens(self):
        self.screen_defs=self.screens()
        self.walker.stop()
        if not any(s.contains(self.walker.position) for s in self.screen_defs):
            s=self.screen_defs[0]
            self.walker.position=(s.x+s.width/2,s.floor)

    def read_control(self,now):
        path=self.data/'control.json'
        try:
            control=json.loads(path.read_text(encoding='utf-8'))
        except (FileNotFoundError,ValueError,OSError):
            return
        if control.get('session')!=self.session:
            return
        self.lease=control.get('lease',self.lease)
        if control.get('stop'):
            QApplication.quit()
            return
        self.visible=bool(control.get('visible',False))
        self.mode=control.get('mode','auto')
        self.instrument=control.get('instrument','auto')
        self.roam=bool(control.get('roam',True)) and self.platform_features['screen_walking']
        self.effects=bool(control.get('effects',True))
        revision=control.get('revision')
        if revision!=self.control_revision:
            self.control_revision=revision
            if isinstance(control.get('position'),list) and len(control['position'])==2:
                point=tuple(map(float,control['position']))
                if any(s.contains(point) for s in self.screen_defs):
                    self.walker.position=point
                    self.walker.stop()
            target=control.get('walk_to')
            if target is not None and self.screen_defs:
                self.requested_route=self.screen_defs[int(target)%len(self.screen_defs)]
            if control.get('preview'):
                self.grab().save(str(self.data/'scene-preview.png'))
                if self.concert.isVisible():self.concert.grab().save(str(self.data/'concert-preview.png'))
            if control.get('desktop_event') in ('window','icon','three'):
                self.desktop.request=control['desktop_event']

    def parent_alive(self):
        if not self.parent_pid: return True
        if os.name != 'nt': return process_alive(self.parent_pid)
        # Own parent-process liveness only; no inspection/control of other apps.
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        handle=kernel.OpenProcess(0x1000,False,self.parent_pid)
        if not handle: return False
        code=ctypes.c_ulong()
        ok=kernel.GetExitCodeProcess(ctypes.c_void_p(handle),ctypes.byref(code))
        kernel.CloseHandle(ctypes.c_void_p(handle))
        return bool(ok and code.value==259)

    def tick(self):
        now=time.monotonic(); dt=min(.1,now-self.last_frame); self.last_frame=now
        if now-self.last_control>.15:
            self.last_control=now
            self.read_control(now)
            if not self.demo and (now-self.lease>12 or not self.parent_alive()):
                QApplication.quit()
                return
        self.features=self.audio.snapshot()
        if now-self.started<.5:
            self.features['music']=False
        forced=self.mode in ('slow','mid','fast')
        music=(self.features.get('music',False) or forced) and self.mode!='walk'
        if forced:
            self.features.update(period=60/{'slow':85,'mid':116,'fast':150}[self.mode],epoch=self.started,confidence=1)
            self.features['music']=True
        self.motion.advance(now,self.features)
        desktop_active=self.desktop.tick(now,music)
        instrument=self.chooser.choose(self.features,now,self.instrument)
        state=self.stage.update(now,music,instrument)
        if state in ('take_out','play','put_away'):
            if self.walker.waypoints:
                # Land a paused hop before setting up the kit.
                self.walker.stop()
                containing=[s for s in self.screen_defs if s.x<=self.walker.position[0]<s.right]
                s=containing[0] if containing else self.screen_defs[0]
                self.walker.position=(self.walker.position[0],s.floor)
            if state=='play':
                self.frame=self.performance(now)
            else:
                self.frame=self.intros[self.stage.instrument][self.stage.transition_frame(now)]
            self.walk_at=now+10
        else:
            if self.requested_route is not None:
                current=min(self.screen_defs,key=lambda s:abs(s.x+s.width/2-self.walker.position[0]))
                self.walker.set_route(route(self.walker.position,current,self.requested_route))
                self.requested_route=None
            if self.roam and self.mode!='concert' and not desktop_active and not self.drag_offset and now>=self.walk_at and not self.walker.waypoints:
                current=min(self.screen_defs,key=lambda s:abs(s.x+s.width/2-self.walker.position[0]))
                others=[s for s in self.screen_defs if s.name!=current.name]
                if others:
                    # Choose adjacent displays first, so a route doesn't cross
                    # an unrelated desktop gap when an intermediate exists.
                    adjacent=[s for s in others if abs(s.x-current.right)<4 or abs(s.right-current.x)<4
                              or (s.x<current.right and s.right>current.x)]
                    others=adjacent or others
                    target=min(others,key=lambda s:abs(s.x+s.width/2-self.walker.position[0]))
                    recent=self.visited[-2:]
                    choices=[s for s in others if s.name not in recent]
                    if choices: target=min(choices,key=lambda s:abs(s.x+s.width/2-self.walker.position[0]))
                    self.walker.set_route(route(self.walker.position,current,target))
                else:
                    x=current.x+random.uniform(.2,.8)*current.width
                    self.walker.set_route([(x,current.floor)])
                self.walk_at=now+random.uniform(14,24)
            moving=self.walker.advance(now,dt,speed=185 if self.desktop.phase=='running' else 110) if self.roam and self.mode!='concert' and not self.drag_offset else False
            self.stage.state='walk' if moving else 'idle'
            seq=self.fly if self.walker.airborne else self.walk if moving else self.idle
            self.frame=seq[int(now*(12 if self.walker.airborne else 10 if moving else 8))%len(seq)]
        x,y=self.walker.position
        self.move(round(x-128),round(y-208))
        screen=next((s.name for s in self.screen_defs if s.contains((x,y))),None)
        if screen and screen!=self.last_screen:
            self.last_screen=screen
            self.visited.append(screen)
            self.visited=self.visited[-12:]
        concert_active=self.concert.tick(self.mode=='concert',now,music)
        self.setVisible(self.visible and not concert_active)
        self.update()
        if now-self.last_status>.5:
            self.last_status=now
            safe={k:v for k,v in self.features.items() if k!='hits'}
            status=dict(version='0.5.1',session=self.session,pid=os.getpid(),heartbeat=now,
                        ready=True,visible=self.visible,state=self.stage.state,instrument=self.stage.instrument,
                        position=[round(x,1),round(y,1)],screen=screen,visited=self.visited,
                        screens=[s.__dict__ for s in self.screen_defs],audio=safe,
                        render_interval_ms=round(dt*1000,2),
                        hit_presentation_ms=list(self.presentation_errors))
            status['concert']=dict(active=concert_active,performers=4 if concert_active else 0)
            status['concert']['poses']={i:playing_pose(self.motion,i,self.features) for i in self.loops} if concert_active else {}
            status['concert']['effect_events']=len(self.concert.effects) if concert_active else 0
            status['vocal_active']=vocal_active(self.features)
            status['desktop']=dict(phase=self.desktop.phase,borrowed=len(self.desktop.borrowed),icons_seen=len(self.desktop.observer.snapshot()),
                                   observer_error=self.desktop.observer.error,surfaces=len(self.desktop.windows),events=self.desktop.events[-8:])
            status['motion']=dict(period=round(self.motion.period,3),head_cycle_seconds=round(self.motion.period*2,3))
            status['platform_features']=self.platform_features
            atomic_json(self.data/'renderer-status.json',status)

    def performance(self,now):
        period=self.motion.period
        beat=self.motion.beats
        hits=self.features.get('hits',[])
        if not hits and self.mode in ('slow','mid','fast'):
            stamp=self.started+math.floor(beat)*period
            hits=[dict(time=stamp,kind='snare',strength=.7)]
        latest=max(hits,key=lambda h:h['time']) if hits else None
        # Audio attacks trigger effects. They never reset the movement clock.
        active=bool(self.features.get('music')) and (self.stage.instrument!='microphone' or vocal_active(self.features))
        active=active or self.mode in ('slow','mid','fast')
        index=playing_pose(self.motion,self.stage.instrument,self.features)
        if self.stage.instrument=='drums' and latest and latest['kind']=='cymbal' and 0<=now-latest['time']<.08:
            # Phrase 3 starts on the left cymbal. It matches the effect anchor.
            index=128+index%16
        for hit in hits:
            if hit['time']>self.last_effect_time:
                self.last_effect_time=hit['time']
                # Don't replay attacks that happened during the take-out
                # transition, or report them as delayed playing-frame events.
                if active and 0<=now-hit['time']<.08:
                    self.effect_history.append(dict(hit,instrument=self.stage.instrument))
                    self.presentation_errors.append(round((now-hit['time'])*1000,2))
        self.pose_index=index
        note_beat=int(beat)
        if note_beat!=self.last_note_beat:
            self.last_note_beat=note_beat
            if active and self.stage.instrument!='drums':
                self.effect_history.append(dict(time=now,kind='note',instrument=self.stage.instrument,side=note_beat))
        return self.loops[self.stage.instrument][index]

    def draw_performer(self,painter,frame,instrument,pose,playing=True):
        painter.drawImage(0,0,frame)
        if not playing:return
        open_mouth=instrument=='microphone' and vocal_active(self.features) and int(self.motion.beats*4)%3!=0
        hp=(self.motion.head_pose() if self.features.get('music') else 0)+(32 if open_mouth else 0)
        sway=body_sway(pose) if instrument!='drums' else 0
        painter.drawImage(sway,0,self.heads[hp])
        if instrument=='microphone':
            painter.setPen(QColor('#51465d'));painter.drawEllipse(35,29,5,3)
            painter.setPen(QColor('#eee8f2'));painter.drawLine(36,30,38,30)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
        painter.scale(4,4)
        if self.stage.state in ('idle','walk') and self.walker.direction<0:
            painter.translate(64,0);painter.scale(-1,1)
        self.draw_performer(painter,self.frame,self.stage.instrument,self.pose_index,self.stage.state=='play')
        self.desktop.draw(painter)
        # Only the occupied pixels intercept mouse input, not a 256px square.
        # Region is updated at most once per frame and includes the instruments.
        mirrored=self.stage.state in ('idle','walk') and self.walker.direction<0
        carrying=self.desktop.phase in ('running','carrying')
        key=(self.frame.cacheKey(),mirrored,self.stage.state=='play',carrying)
        region=self.mask_cache.get(key)
        if region is None:
            region=QRegion()
            for y in range(64):
                run=None
                for x in range(65):
                    opaque=x<64 and self.frame.pixelColor(x,y).alpha()>0
                    if opaque and run is None: run=x
                    if not opaque and run is not None:
                        a,b=run,x
                        if mirrored:a,b=64-b,64-a
                        region|=QRegion(QRect(a*4,y*4,(b-a)*4,4));run=None
            if self.stage.state=='play':
                # Allow particles outside opaque sprite pixels to be painted.
                region|=QRegion(QRect(5*4,20*4,54*4,34*4))
                region|=QRegion(QRect(19*4,0,28*4,36*4))
            if carrying:region|=QRegion(QRect(17*4,35*4,31*4,14*4))
            self.mask_cache[key]=region
        self.setMask(region)
        if self.effects and self.stage.state=='play':
            draw_effects(painter,self.stage.instrument,self.effect_history,time.monotonic(),
                         accent=instrument_activity(self.stage.instrument,self.features))
        painter.end()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.desktop.caught()
            self.drag_offset=event.globalPosition().toPoint()-self.pos()
            self.walker.stop()
        elif event.button()==Qt.MouseButton.RightButton:
            menu=QMenu(self)
            for value,label in [('auto','Инструмент: автоматически'),('drums','Барабаны'),('guitar','Электрогитара'),('microphone','Микрофон'),('keyboard','Синтезатор')]:
                action=menu.addAction(label)
                action.triggered.connect(lambda checked=False,v=value:self.local_control(instrument=v))
            roam=menu.addAction('Прогулки между экранами')
            roam.setCheckable(True);roam.setChecked(self.roam)
            roam.setEnabled(self.platform_features['screen_walking'])
            roam.triggered.connect(lambda checked:self.local_control(roam=checked))
            effects=menu.addAction('Волны и частицы')
            effects.setCheckable(True);effects.setChecked(self.effects)
            effects.triggered.connect(lambda checked:self.local_control(effects=checked))
            menu.addSeparator()
            menu.addAction('Собрать группу на сцене').triggered.connect(lambda:self.local_control(mode='concert'))
            for label,kind in [('Прогуляться по окну','window'),('Поиграть с копиями иконок','icon')]:
                action=menu.addAction(label)
                action.setEnabled(self.platform_features['desktop_events'])
                action.triggered.connect(lambda checked=False,k=kind:self.local_control(mode='walk',desktop_event=k))
            menu.addAction('Вернуть обычную Nayu').triggered.connect(lambda:self.local_control(mode='restore',stop=True))
            menu.exec(event.globalPosition().toPoint())

    def local_control(self,**changes):
        # An action request is consumed by the owning plugin. Don't race the
        # plugin's leased control file or lose a menu change on its next poll.
        atomic_json(self.data/'renderer-request.json',dict(changes,session=self.session,time=time.monotonic()))

    def mouseMoveEvent(self,event):
        if self.drag_offset is not None:
            pos=event.globalPosition().toPoint()-self.drag_offset
            self.walker.position=(pos.x()+128,pos.y()+208)

    def mouseReleaseEvent(self,event):
        self.drag_offset=None
        self.walk_at=time.monotonic()+12


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',required=True)
    parser.add_argument('--parent',type=int,default=0)
    parser.add_argument('--session',required=True)
    parser.add_argument('--demo',action='store_true')
    args=parser.parse_args()
    app=QApplication([])
    app.setQuitOnLastWindowClosed(False)
    widget=Companion(args.data,args.parent,args.session,args.demo)
    app.aboutToQuit.connect(widget.audio.stop_event.set)
    app.aboutToQuit.connect(widget.audio.tags.stop_event.set)
    app.aboutToQuit.connect(widget.desktop.observer.stop_event.set)
    code=app.exec()
    atomic_json(Path(args.data)/'renderer-status.json',dict(session=args.session,ready=False,stopped=True,heartbeat=time.monotonic()))
    return code


if __name__=='__main__':
    raise SystemExit(main())
