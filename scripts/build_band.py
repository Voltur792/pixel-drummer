"""Author small pixel instruments around the unmodified native Nayu pixels.

Explicitly requested deterministic assembly. This is a build tool, not an AI
redraw. Hair/head move by integer pixel translation, never by smooth scaling.
"""
from pathlib import Path
import json
import math
import runpy
import sys
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.motion import body_sway
OUT = ROOT/'src/resources/assets/band'
OUT.mkdir(parents=True,exist_ok=True)
# Rebuild the existing native fallback too; keep its graph and exact-head art.
old = runpy.run_path(str(ROOT/'scripts/build_animation.py'))
BASE, KIT, arm = old['BASE'], old['KIT'], old['arm']
HEAD_BOX=(21,0,45,34)
HEAD=BASE.crop(HEAD_BOX)
BODY=BASE.copy()
BODY.paste((0,0,0,0),HEAD_BOX)
OUTLINE='#51465d'
WHITE='#eee8f2'
SKIN='#e9c2c4'


def head(im, phase, amount=1, mouth=False, sway=0):
    # One source-pixel nod (4 physical pixels at native scale). No resampling
    # of the face; a delayed tuft gives the hair a little follow-through.
    dy=round(amount*(.5+.5*math.cos(phase*2*math.pi)))
    dx=round(amount*.6*math.sin(phase*2*math.pi))
    copy=HEAD.copy()
    tuft_box=(7,8,16,15)
    tuft=copy.crop(tuft_box)
    copy.paste((0,0,0,0),tuft_box)
    lag=round(amount*.7*math.sin((phase-.13)*2*math.pi))
    copy.alpha_composite(tuft,(tuft_box[0]+lag,tuft_box[1]))
    if mouth:
        face=ImageDraw.Draw(copy)
        face.line((10,28,12,28),fill='#824756')
        face.line((11,29,12,29),fill='#d88691')
    im.alpha_composite(copy,(21+dx+sway,dy))
    return im


def guitar_plate():
    im=Image.new('RGBA',(64,64)); d=ImageDraw.Draw(im)
    # Angular electric guitar, slanted neck and silver hardware.
    d.line((27,34,39,45),fill=OUTLINE,width=2)
    d.polygon(((31,39),(36,37),(40,39),(43,37),(47,42),(44,47),(37,48),(30,45)),fill=OUTLINE)
    d.polygon(((32,40),(36,39),(40,41),(43,39),(45,43),(42,46),(37,46),(32,44)),fill='#b5394c')
    d.line((32,41,35,40,38,42),fill='#e26970',width=2)
    d.line((41,45,43,43),fill='#742637',width=2)
    d.line((38,43,53,31),fill=OUTLINE,width=4)
    d.line((38,43,53,31),fill='#ae98bd',width=2)
    d.line((38,43,53,31),fill='#e7dce9')
    d.rectangle((35,42,38,43),fill=WHITE)
    d.rectangle((37,44,39,45),fill=OUTLINE)
    d.line((52,31,55,29),fill=OUTLINE,width=3)
    d.point((53,28),fill=WHITE);d.point((56,30),fill=WHITE)
    centred=Image.new('RGBA',(64,64));centred.alpha_composite(im,(-6,-1))
    return centred


def microphone_plate():
    im=Image.new('RGBA',(64,64));d=ImageDraw.Draw(im)
    d.line((42,33,42,50),fill=OUTLINE,width=2)
    d.line((43,34,43,49),fill='#aaa2ba')
    d.line((42,48,37,51),fill=OUTLINE,width=2)
    d.line((42,48,47,51),fill=OUTLINE,width=2)
    d.line((42,35,37,31),fill=OUTLINE,width=2)
    d.ellipse((34,28,40,32),fill=OUTLINE)
    d.rectangle((35,29,38,30),fill='#c9bdcc')
    d.point((35,29),fill=WHITE)
    return im


def keyboard_plate():
    im=Image.new('RGBA',(64,64));d=ImageDraw.Draw(im)
    d.polygon(((12,37),(51,37),(54,44),(10,44)),fill=OUTLINE)
    d.rectangle((13,38,51,43),fill='#383e62')
    # Keys are on the player's side; controls face the audience at the front.
    d.rectangle((15,38,49,40),fill=WHITE)
    for x in range(18,49,3):d.line((x,38,x,40),fill='#6e6884')
    for x in (18,21,27,30,33,39,42,48):d.line((x,38,x,39),fill='#363146')
    d.line((17,44,44,54),fill=OUTLINE,width=2)
    d.line((46,44,19,54),fill=OUTLINE,width=2)
    d.rectangle((16,42,19,42),fill='#bd536d')
    d.rectangle((43,42,48,42),fill='#8cb9c7')
    return im

GUITAR=guitar_plate(); MIC=microphone_plate(); KEYS=keyboard_plate()
PLATES={'drums':KIT,'guitar':GUITAR,'microphone':MIC,'keyboard':KEYS}

def sway_for(index):
    return body_sway(index)

def posed_body(index):
    body=BODY.copy()
    # Alternate a tiny heel lift. Keep the source boots/legs, merely translate.
    tap=math.sin(index/16*2*math.pi)
    foot_box=(24,46,33,52) if tap>0 else (33,46,41,52)
    lift=round(abs(tap)*2)
    if lift:
        foot=body.crop(foot_box);body.paste((0,0,0,0),foot_box)
        body.alpha_composite(foot,(foot_box[0],foot_box[1]-lift))
    result=Image.new('RGBA',(64,64));result.alpha_composite(body,(sway_for(index),0))
    return result


def frame(instrument,index):
    phase=(index%16)/16
    if instrument=='drums':
        # Recover the old sleeve/stick pixels, remove its original head, and
        # insert an integer-translated original head. Kit stays stationary.
        im=old['performance'](index)
        im.paste((0,0,0,0),HEAD_BOX)
        return im
    sway=sway_for(index)
    im=posed_body(index)
    im.alpha_composite(PLATES[instrument],(sway if instrument=='guitar' else 0,0))
    d=ImageDraw.Draw(im)
    if instrument=='guitar':
        strum=round(2*math.cos(phase*2*math.pi))
        fret=round(math.sin(index/16*math.pi))
        for points in (((27+sway,35),(28+sway,39),(31+sway,41+strum)),((38+sway,35),(40+sway,34),(43+sway+fret,34))):
            d.line(points,fill=OUTLINE,width=5);d.line(points,fill=WHITE,width=3);d.point(points[-1],fill=SKIN)
    elif instrument=='keyboard':
        press=round(math.sin(phase*2*math.pi))
        for points in (((27+sway,35),(24+sway,36),(22+sway,38+press)),((38+sway,35),(41+sway,36),(41+sway,38-press))):
            d.line(points,fill=OUTLINE,width=5);d.line(points,fill=WHITE,width=3);d.point(points[-1],fill=SKIN)
    else:
        gesture=round(2*math.sin(phase*2*math.pi))
        for points in (((27+sway,35),(23+sway,37),(21+sway,34+gesture)),((38+sway,35),(40+sway,35),(39,33))):
            d.line(points,fill=OUTLINE,width=5);d.line(points,fill=WHITE,width=3);d.point(points[-1],fill=SKIN)
    if instrument=='microphone':
        # The microphone is in front of the mouth, not erased by the head crop.
        d=ImageDraw.Draw(im)
        d.ellipse((35,29,40,32),fill=OUTLINE)
        d.line((36,30,38,30),fill=WHITE)
    return im


def intro(instrument,index):
    if instrument=='drums':
        im=old['entrance'](index)
        if index>=24:
            im.paste((0,0,0,0),HEAD_BOX)
            head(im,0,(index-24)/7)
        return im
    im=BODY.copy()
    d=ImageDraw.Draw(im)
    if index<10:
        d.rectangle((28,44,43,50),fill=OUTLINE)
        d.rectangle((29,45,42,49),fill='#858097')
        reach=min(1,index/6)
        points=((38,35),(42,38),(round(42-5*reach),round(40+5*reach)))
        d.line(points,fill=OUTLINE,width=5);d.line(points,fill=WHITE,width=3)
    else:
        dy=round(12*(1-min(1,(index-10)/13)))
        plate=Image.new('RGBA',(64,64))
        plate.alpha_composite(PLATES[instrument],(0,dy))
        plate.paste((0,0,0,0),(0,52,64,64))
        im.alpha_composite(plate)
    head(im,0,0)
    if index>=24:
        # Ease from the retrieved instrument into the initial playing pose.
        finished=frame(instrument,0);head(finished,0)
        if index==31:
            return finished
        # No opacity fades: additional sleeve rows settle into position.
        y=round(43-9*(index-24)/7)
        im.paste(finished.crop((0,y,64,64)),(0,y))
        im.paste((0,0,0,0),HEAD_BOX)
        head(im,0,(index-24)/7)
    return im


def atlas(frames,path):
    im=Image.new('RGBA',(1024,64*math.ceil(len(frames)/16)))
    for i,cell in enumerate(frames):
        im.paste(cell,(i%16*64,i//16*64))
    im.save(path)


def effects(im,instrument,age,kind='snare'):
    if not 0<=age<.32: return im
    d=ImageDraw.Draw(im)
    x,y={'drums':((50,36) if kind=='cymbal' else (23,38)), 'guitar':(31,41),'microphone':(38,29),'keyboard':(32,41)}[instrument]
    r=1+round(age*22)
    colour='#eddda9' if kind=='cymbal' else '#b9a8d6'
    d.line((x-r,y-1,x-1,y-r//2,x+1,y-r//2,x+r,y-1),fill=colour)
    for dx,dy in ((-1,-1),(1,-1),(-1,0),(1,0)):
        px=x+dx*(r+2);py=y+dy*(r+2)-round(age*8)
        d.point((px,py),fill=colour)
    return im


for source,name in [('00-320x128.png','idle.png'),('01-256x128.png','walk.png'),('02-192x128.png','fly.png')]:
    path=ROOT/'assets/native-source'/source
    if not path.exists():
        # Extracted filenames include measured geometry; index remains stable.
        path=next((ROOT/'assets/native-source').glob(source[:3]+'*.png'))
    (OUT/name).write_bytes(path.read_bytes())

loops={}; intros={}
for instrument in PLATES:
    loops[instrument]=[frame(instrument,i) for i in range(192)]
    intros[instrument]=[intro(instrument,i) for i in range(32)]
    atlas(loops[instrument],OUT/f'{instrument}-loop.png')
    atlas(intros[instrument],OUT/f'{instrument}-in.png')
heads=[]
for mouth in (False,True):
    for i in range(32):
        cell=Image.new('RGBA',(64,64));head(cell,i/32,mouth=mouth);heads.append(cell)
atlas(heads,OUT/'heads.png')

# An invisible native character reserves the normal Astra API lifecycle. It is
# only worn after the external renderer is ready; DOM restores on stop/failure.
proxy=ROOT/'src/resources/assets/pack/characters/pixel-band-proxy'
proxy.mkdir(parents=True,exist_ok=True)
anim=ROOT/'src/resources/assets/pack/animpacks/pixel-band-proxy'
(anim/'clips').mkdir(parents=True,exist_ok=True)
for side in ('a','b'):
    # Distinct clip names AND resource paths are necessary. Changing only the
    # state preserves the player's clock when both states reuse the same clip.
    Image.new('RGBA',(1024,576)).save(anim/f'clips/blank-{side}.png')
(proxy/'character.toml').write_text('[character]\nkind="pixel"\nname="Nayu — музыкальная сцена"\nmodel="builtin:nayu-2d"\nanimpack="pixel-band-proxy"\n',encoding='utf-8',newline='\n')
native=(ROOT/'assets/native-source/builtin.toml').read_text(encoding='utf-8')
# Astra 0.2.7 pack schema 5, as its own converter writes it.
native=native.replace('[animations]','[animpack]',1)
native=native.replace('name = "Nayu (2D)"','name = "Nayu stage proxy"\nuid = "user.e1ddc569d2fb8940"')
native=native.replace('file = "sprites/','file = "builtin:nayu-2d-anims/')
# 144 s of nothing: Astra throttles a hidden window's timers to about one tick
# a minute, and the heartbeat must outlast that. A dead plugin still lets the
# ordinary companion come back on her own once the clip runs out.
blank_clips=''
for side in ('a','b'):
    blank_clips+=f'''[[clips]]
name="stage_blank_{side}"
file="clips/blank-{side}.png"
frames=144
seat=52
fps=1

'''
native=native.replace('[states]\n',blank_clips+'[states]\n',1)
for side in ('a','b'):
    state='stage_hidden_'+side
    native+=f'''\n[states.{state}]
clip="stage_blank_{side}"
loop=false
[[states.{state}.transitions]]
on="clip_finished"
to="idle"
'''
(anim/'animpack.toml').write_text(native,encoding='utf-8',newline='\n')

comparison=Image.new('RGBA',(1280,256),'#353047')
comparison.alpha_composite(BASE.resize((256,256),Image.Resampling.NEAREST))
for i,instrument in enumerate(PLATES,1):
    cell=loops[instrument][0].copy();head(cell,0)
    comparison.alpha_composite(effects(cell,instrument,.12).resize((256,256),Image.Resampling.NEAREST),(i*256,0))
comparison.save(ROOT/'assets/band-comparison.png')
preview=[]
for i in range(192):
    row=Image.new('RGBA',(1024,256),'#353047')
    for col,instrument in enumerate(PLATES):
        if i<32: cell=intros[instrument][i].copy()
        elif i<160:
            idx=i-32
            pose=(idx//2 if instrument!='drums' else idx)%192
            cell=effects(loops[instrument][pose].copy(),instrument,(idx%16)/32)
            head(cell,(idx/32)%1,mouth=instrument=='microphone' and idx%12<7,sway=sway_for(pose) if instrument!='drums' else 0)
        else: cell=intros[instrument][191-i].copy()
        row.alpha_composite(cell.resize((256,256),Image.Resampling.NEAREST),(col*256,0))
    preview.append(row)
preview[0].save(ROOT/'assets/band-animation.gif',save_all=True,append_images=preview[1:],duration=45,loop=0,disposal=2)
(OUT/'manifest.json').write_text(json.dumps(dict(frame_size=64,native_scale=4,frames=192,transition_frames=32,head_motion='integer pixel copy',instruments=list(PLATES)),indent=2),encoding='utf-8')
print('Built band: drums, centred red guitar, vocal mouth, keyboard; separate slow head layer')
