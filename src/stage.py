"""Music transitions and desktop routes, independent of Qt for testing."""
from dataclasses import dataclass
import math


class Stage:
    def __init__(self):
        self.state = 'idle'
        self.instrument = 'drums'
        self.next_instrument = 'drums'
        self.entered = 0
        self.duration = 32/24

    def update(self, now, music, instrument):
        self.next_instrument = instrument
        if self.state in ('idle','walk') and music:
            self.instrument = instrument
            self.state, self.entered = 'take_out', now
        elif self.state == 'take_out' and now-self.entered>=self.duration:
            self.state, self.entered = ('play' if music else 'put_away'), now
        elif self.state == 'play' and (not music or instrument!=self.instrument):
            self.state, self.entered = 'put_away', now
        elif self.state == 'put_away' and now-self.entered>=self.duration:
            self.state, self.entered = 'idle', now
            if music:
                self.instrument = instrument
                self.state = 'take_out'
        return self.state

    def transition_frame(self, now):
        index = min(31,max(0,int((now-self.entered)*24)))
        return 31-index if self.state=='put_away' else index


@dataclass(frozen=True)
class Screen:
    name: str
    x: float
    y: float
    width: float
    height: float
    floor: float

    @property
    def right(self):
        return self.x+self.width

    def contains(self, point):
        x,y = point
        return self.x <= x < self.right and self.y <= y < self.y+self.height


def route(start, current, target, margin=48):
    """Foot-point waypoints. Walk to an edge; hop between unequal floor levels.

    Qt screen coordinates are device-independent and can be negative. We don't
    multiply positions by DPR (doing so breaks mixed-DPI desktops).
    """
    if current.name==target.name:
        return [(min(target.right-margin,max(target.x+margin,start[0])),target.floor)]
    if target.x >= current.right-1:
        return [(current.right-margin,current.floor),
                (target.x+margin,target.floor),
                (target.x+target.width*.45,target.floor)]
    if target.right <= current.x+1:
        return [(current.x+margin,current.floor),
                (target.right-margin,target.floor),
                (target.x+target.width*.55,target.floor)]
    # Vertically stacked or offset displays: walk toward the nearest shared
    # horizontal coordinate, then use a visible hop instead of teleportation.
    left=max(current.x,target.x)+margin
    right=min(current.right,target.right)-margin
    crossing=(left+right)/2 if left<=right else target.x+target.width/2
    return [(crossing,current.floor),(crossing,target.floor),
            (target.x+target.width/2,target.floor)]


class Walker:
    def __init__(self, point):
        self.position = tuple(point)
        self.waypoints = []
        self.direction = 1
        self.segment_start = None
        self.segment_origin = self.position
        self.airborne = False

    def stop(self):
        self.waypoints.clear()
        self.segment_start = None
        self.airborne = False

    def set_route(self, points):
        self.waypoints = list(points)
        self.segment_start = None

    def advance(self, now, dt, speed=110):
        if not self.waypoints:
            return False
        end = self.waypoints[0]
        if self.segment_start is None:
            self.segment_start, self.segment_origin = now,self.position
        ox,oy=self.segment_origin
        ex,ey=end
        distance=math.hypot(ex-ox,ey-oy)
        self.direction = 1 if ex>=ox else -1
        self.airborne = abs(ey-oy)>2
        if self.airborne:
            duration=max(.7,distance/280)
            p=min(1,(now-self.segment_start)/duration)
            self.position=(ox+(ex-ox)*p,oy+(ey-oy)*p-24*math.sin(math.pi*p))
            done=p>=1
        else:
            x,y=self.position
            remaining=math.hypot(ex-x,ey-y)
            step=min(remaining,speed*dt)
            self.position=(x+(ex-x)*step/max(remaining,1e-9),y+(ey-y)*step/max(remaining,1e-9))
            done=remaining<=step+.01
        if done:
            self.position=end
            self.waypoints.pop(0)
            self.segment_start=None
            self.airborne=False
        return bool(self.waypoints)
