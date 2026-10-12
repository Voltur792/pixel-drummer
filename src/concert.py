"""Four original-sized performers enter and leave a single pixel stage."""
import math
from collections import deque
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QRegion
from PySide6.QtWidgets import QWidget, QMenu
from .motion import instrument_activity, playing_pose, vocal_active
from .music_effects import draw_effects

INSTRUMENTS=('drums','guitar','microphone','keyboard')
FLOOR_Y=79
ACTOR_Y=FLOOR_Y-51  # Original resting boot pixel; taps leave one foot here.


class ConcertWindow(QWidget):
    def __init__(self,owner):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool|
                         Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.owner=owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('Nayu — музыкальная сцена')
        self.resize(1088,384)
        self.started=None;self.leaving=None;self.now=0;self.music=False
        self.drag_offset=None
        self.effects=deque(maxlen=96);self.last_hit=-math.inf;self.last_note=None
        self.setMask(QRegion(QRect(28,76,1032,288)))

    def tick(self,requested,now,music):
        self.now,self.music=now,music
        if requested and self.started is None:
            self.started=now;self.leaving=None
            self.effects.clear();self.last_hit=now;self.last_note=None
            x,y=self.owner.walker.position
            screen=next((s for s in self.owner.screen_defs if s.contains((x,y))),self.owner.screen_defs[0])
            self.move(round(min(screen.right-1088,max(screen.x,x-544))),round(min(screen.floor-360,max(screen.y,y-320))))
        if self.started is None:return False
        if music and now-self.started>3.8 and self.leaving is None:
            for hit in self.owner.features.get('hits',[]):
                if hit['time']>self.last_hit:
                    self.last_hit=hit['time']
                    if 0<=now-hit['time']<.10:
                        self.effects.append(dict(hit,instrument='drums'))
            beat=int(self.owner.motion.beats)
            if beat!=self.last_note:
                self.last_note=beat
                for instrument in ('guitar','keyboard','microphone'):
                    if instrument!='microphone' or vocal_active(self.owner.features):
                        self.effects.append(dict(time=now,instrument=instrument,kind='note',side=beat))
                # Keep the kit visibly alive on the musical pulse even when
                # no strong attack was detected in this beat.
                if now-self.last_hit>.35:
                    self.effects.append(dict(time=now,instrument='drums',kind=('kick','snare','cymbal','snare')[beat%4]))
        if requested:self.leaving=None
        elif self.leaving is None:self.leaving=now
        if self.leaving is not None and now-self.leaving>2:
            self.hide();self.started=None;self.leaving=None
            return False
        self.setVisible(self.owner.visible);self.update()
        return True

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
        painter.scale(4,4)
        painter.fillRect(7,79,258,9,QColor('#382f50'))
        painter.fillRect(7,79,258,2,QColor('#a47da2'))
        painter.fillRect(10,88,252,3,QColor('#211c36'))
        for x in (9,251):
            painter.fillRect(x,60,12,19,QColor('#332c43'))
            painter.setPen(QColor('#82718f'));painter.drawEllipse(x+2,62,7,7);painter.drawEllipse(x+2,71,7,6)
        age=max(0,self.now-self.started)
        for number,instrument in enumerate(INSTRUMENTS):
            target=43+number*61
            entry=min(1,max(0,(age-number*.25)/1.65))
            leaving=0 if self.leaving is None else min(1,(self.now-self.leaving)/1.8)
            moving=entry<1 or self.leaving is not None
            origin=-30 if number%2==0 else 290
            centre=origin+(target-origin)*entry
            centre=centre+(origin-centre)*leaving
            painter.save();painter.translate(round(centre-32),ACTOR_Y)
            pose=self.owner.motion.pose(instrument)
            if moving:
                frame=self.owner.walk[int(self.now*9)%len(self.owner.walk)]
                left=(entry<1 and origin>target) or (self.leaving is not None and origin<target)
                if left:painter.translate(64,0);painter.scale(-1,1)
                self.owner.draw_performer(painter,frame,instrument,0,False)
            elif age<3.8:
                index=min(31,max(0,int((age-1.65-number*.25)*24)))
                self.owner.draw_performer(painter,self.owner.intros[instrument][index],instrument,0,False)
            else:
                active=self.music and instrument_activity(instrument,self.owner.features)
                pose=playing_pose(self.owner.motion,instrument,self.owner.features) if self.music else 0
                self.owner.draw_performer(painter,self.owner.loops[instrument][pose],instrument,pose,True)
                if self.music and self.owner.effects:
                    draw_effects(painter,instrument,self.effects,self.now,accent=active)
            painter.restore()
        painter.end()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.drag_offset=event.globalPosition().toPoint()-self.pos()
        elif event.button()==Qt.MouseButton.RightButton:
            menu=QMenu(self)
            menu.addAction('Убрать сцену — автоматический режим').triggered.connect(lambda:self.owner.local_control(mode='auto',instrument='auto'))
            menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self,event):
        if self.drag_offset is not None:self.move(event.globalPosition().toPoint()-self.drag_offset)

    def mouseReleaseEvent(self,event):self.drag_offset=None
