"""Occasional window climbing and visual shortcut borrowing."""
import math
import random
import time
from PySide6.QtCore import Qt, QFileInfo, QTimer, QRect
from PySide6.QtGui import QPainter, QRegion
from PySide6.QtWidgets import QWidget, QFileIconProvider, QApplication
from .desktop import window_surfaces, desktop_shortcuts, IconObserver


def logical_point(point):
    x,y=point
    screens=QApplication.screens()
    screen=next((s for s in screens if s.geometry().x()<=x<s.geometry().x()+s.geometry().width()*s.devicePixelRatio()
                 and s.geometry().y()<=y<s.geometry().y()+s.geometry().height()*s.devicePixelRatio()),screens[0])
    g=screen.geometry();ratio=screen.devicePixelRatio()
    return g.x()+(x-g.x())/ratio,g.y()+(y-g.y())/ratio


class FlyingIcon(QWidget):
    def __init__(self,image,start,end):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool|
                         Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(48,48);self.image=image;self.start,self.end=start,end
        self.began=time.monotonic();self.finished=False
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(16)
        self.tick();self.show()

    def tick(self):
        p=min(1,(time.monotonic()-self.began)/1.2);smooth=p*p*(3-2*p)
        x=self.start[0]+(self.end[0]-self.start[0])*smooth
        y=self.start[1]+(self.end[1]-self.start[1])*smooth-35*math.sin(math.pi*p)
        self.move(round(x-24),round(y-24));self.update()
        if p>=1:self.timer.stop();self.hide();self.finished=True;self.deleteLater()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
        painter.drawImage(QRect(0,0,48,48),self.image);painter.end()


class DesktopPlay:
    def __init__(self,owner):
        self.owner=owner;self.observer=IconObserver();self.observer.start()
        self.sources=desktop_shortcuts();self.icon_provider=QFileIconProvider()
        self.next_event=time.monotonic()+random.uniform(55,100)
        self.perch=None;self.perch_rect=None;self.perch_until=0
        self.phase=None;self.borrowed=[];self.return_at=0;self.flights=[]
        self.rare_after=time.monotonic()+300;self.windows=[];self.last_windows=0
        self.request=None;self.events=[]

    def surfaces(self,now):
        if now-self.last_windows>1:
            self.last_windows=now
            self.windows=[]
            for window in window_surfaces():
                left,top=logical_point((window.left,window.top));right,bottom=logical_point((window.right,window.bottom))
                if any(s.y+100<top<s.floor-120 and s.x<right and left<s.right for s in self.owner.screen_defs):
                    self.windows.append((window.handle,left,top,right,bottom))
        return self.windows

    def return_icons(self):
        if not self.borrowed:return
        x,y=self.owner.walker.position
        for i,item in enumerate(self.borrowed):
            self.flights.append(FlyingIcon(item['image'],(x+(i-1)*32,y-52),item['origin']))
        self.events.append('icons_returned');self.borrowed=[];self.phase=None
        self.owner.walker.stop();self.owner.walk_at=time.monotonic()+12

    def caught(self):
        self.return_icons();self.perch=None;self.phase=None
        self.next_event=time.monotonic()+random.uniform(70,130)

    def borrow(self,count):
        candidates=[]
        for item in self.observer.snapshot():
            name=item['name'].casefold()
            source=self.sources.get(name) or self.sources.get(name.removesuffix('.lnk'))
            if source is None:continue
            image=self.icon_provider.icon(QFileInfo(str(source))).pixmap(32,32).toImage()
            if not image.isNull():candidates.append(dict(image=image,origin=logical_point((item['x'],item['y']))))
        if not candidates or (count==3 and len(candidates)<3):return False
        self.borrowed=random.sample(candidates,min(count,len(candidates)))
        self.phase='pickup';self.perch=None
        x,y=self.borrowed[0]['origin']
        self.owner.walker.set_route([(x-24,y+52)])
        self.owner.walk_at=time.monotonic()+100000
        self.return_at=math.inf if count==3 else time.monotonic()+25
        self.events.append('three_icons' if count==3 else 'one_icon')
        return True

    def climb(self,now):
        windows=self.surfaces(now)
        if not windows:return False
        px,py=self.owner.walker.position
        nearest=sorted(windows,key=lambda w:abs((w[1]+w[3])/2-px)+abs(w[2]-py))[:2]
        handle,left,top,right,bottom=random.choice(nearest)
        x=random.uniform(left+100,right-100)
        self.perch=handle;self.perch_rect=(left,top,right,bottom);self.perch_until=math.inf
        self.phase='climb';self.owner.walker.set_route([(x,self.owner.walker.position[1]),(x,top)])
        self.owner.walk_at=now+100000;self.events.append('window_climb')
        return True

    def tick(self,now,music):
        self.flights=[flight for flight in self.flights if not flight.finished]
        if music or self.owner.mode=='concert' or not self.owner.roam:
            self.return_icons()
            if self.perch is not None:
                self.perch=None;self.phase=None
            return False
        if self.owner.drag_offset is not None:return True
        if self.perch is not None:
            match=next((w for w in self.surfaces(now) if w[0]==self.perch),None)
            if match is None or now>=self.perch_until:
                self.perch=None;self.phase=None
                s=next((s for s in self.owner.screen_defs if s.x<=self.owner.walker.position[0]<s.right),self.owner.screen_defs[0])
                self.owner.walker.set_route([(self.owner.walker.position[0],s.floor)])
                self.owner.walk_at=now+15
            elif not self.owner.walker.waypoints:
                _,left,top,right,bottom=match
                self.owner.walker.position=(min(right-80,max(left+80,self.owner.walker.position[0]+left-self.perch_rect[0])),top)
                if self.phase=='climb':self.perch_until=now+random.uniform(15,25)
                self.perch_rect=(left,top,right,bottom);self.phase='perched'
            return True
        if self.borrowed:
            if now>=self.return_at:self.return_icons();return False
            if not self.owner.walker.waypoints:
                self.phase='running' if len(self.borrowed)==3 else 'carrying'
                current=next((s for s in self.owner.screen_defs if s.contains(self.owner.walker.position)),self.owner.screen_defs[0])
                ordered=sorted(self.owner.screen_defs,key=lambda s:s.x)
                index=ordered.index(current)
                targets=[ordered[i] for i in (index-1,index+1) if 0<=i<len(ordered)] or [current]
                target=random.choice(targets)
                from .stage import route
                self.owner.walker.set_route(route(self.owner.walker.position,current,target))
            return True
        if self.request or now>=self.next_event:
            event=self.request or random.choice(['window','icon','window','three' if now>=self.rare_after else 'icon'])
            self.request=None;self.next_event=now+random.uniform(70,130)
            if event=='window':return self.climb(now)
            if event in ('icon','three'):
                if event=='three':self.rare_after=now+600
                return self.borrow(3 if event=='three' else 1)
        return False

    def draw(self,painter):
        if self.phase not in ('running','carrying'):return
        for i,item in enumerate(self.borrowed):
            x=25+(i-1)*8 if len(self.borrowed)>1 else 35
            painter.drawImage(QRect(x,36,12,12),item['image'])
