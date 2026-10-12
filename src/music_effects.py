"""Small crisp notes, impact waves and particles shared by both renderers."""
import math
from PySide6.QtGui import QColor


def draw_effects(painter,instrument,events,now,accent=False):
    for event in events:
        if event.get('instrument')!=instrument:continue
        age=now-event['time'];kind=event.get('kind','snare')
        lifetime=.85 if kind=='note' else .38
        if not 0<=age<lifetime:continue
        x,y={'guitar':(31,41),'keyboard':(32,39),'microphone':(33,28)}.get(instrument,(23,38))
        if instrument=='drums':x,y=(15,36) if kind=='cymbal' else (32,45) if kind=='kick' else (23,38)
        colour=QColor('#eddda9' if instrument=='drums' else '#8cb9c7' if instrument=='keyboard' else '#d8a4c6')
        colour.setAlpha(round((255 if accent else 210)*(1-age/lifetime)))
        painter.setPen(colour)
        if kind=='note':
            direction=-1 if event.get('side',0)%2 else 1
            nx=x+direction*round(3+age*7);ny=y-5-round(age*17)
            # A 4x6 source-pixel eighth note: stem, flag and solid note head.
            painter.fillRect(nx,ny+4,2,2,colour)
            painter.fillRect(nx+2,ny,1,5,colour)
            painter.fillRect(nx+3,ny,1,2,colour)
            painter.fillRect(nx-2,ny+2,1,1,colour)
            continue
        radius=1+round(age*22)
        painter.drawLine(x-radius,y-1,x-1,y-radius//2)
        painter.drawLine(x-1,y-radius//2,x+1,y-radius//2)
        painter.drawLine(x+1,y-radius//2,x+radius,y-1)
        for direction in (-1,1):
            painter.fillRect(x+direction*(radius+2),y-radius-2,1,1,colour)
            painter.fillRect(x+direction*radius,y-3-round(age*14),1,1,colour)
        if instrument=='drums' and kind=='cymbal' and age<.18:
            dy=round(math.sin(age*95)*math.exp(-age*12))
            painter.drawLine(x-4,y+dy,x+4,y+dy)
