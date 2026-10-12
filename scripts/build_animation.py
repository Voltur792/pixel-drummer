"""Deterministic 64px animation, preserving the original Nayu's head and body.

The user explicitly chose programmatic assembly from the installed native art.
Only arms/sticks and a new stationary kit are authored here. Runtime idle/walk/
sleep/etc use Astra's compiled-in sheets, without copying or repainting them.
"""
from pathlib import Path
import hashlib
import json
import math
import tomllib
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/native-source'
PACK = ROOT / 'src/resources/assets/pack'
SPRITES = PACK / 'characters/pixel-drummer-nayu/sprites'
SPRITES.mkdir(parents=True, exist_ok=True)
BASE = Image.open(SOURCE / '00-320x128.png').convert('RGBA').crop((0, 0, 64, 64))
OUTLINE = '#51465d'
STEEL = '#9b99b1'
WHITE = '#eee8f2'
SKIN = '#e9c2c4'
GOLD = '#dac68e'


def kit():
    """One stationary kit shared byte-for-byte by every performance frame."""
    im = Image.new('RGBA', (64, 64))
    d = ImageDraw.Draw(im)
    # Back stands and stool. The floor/contact row is 51, matching native idle.
    for x in (15, 50):
        d.line((x, 39, x, 50), fill=OUTLINE, width=2)
        d.line((x, 40, x, 49), fill=STEEL)
        d.line((x, 47, x - 4, 51), fill=OUTLINE)
        d.line((x, 47, x + 4, 51), fill=OUTLINE)
    d.rectangle((29, 43, 36, 45), fill=OUTLINE)
    # Main bass drum, snare and two small toms.
    d.ellipse((24, 39, 41, 51), fill=OUTLINE)
    d.ellipse((26, 40, 40, 50), fill=STEEL)
    d.ellipse((27, 41, 39, 49), fill='#e6e0eb')
    d.ellipse((28, 42, 38, 48), fill='#d4cede')
    d.rectangle((25, 41, 26, 47), fill='#716981')
    d.rectangle((38, 43, 40, 45), fill=OUTLINE)
    for box in ((18, 38, 28, 43), (35, 36, 45, 41)):
        x0, y0, x1, y1 = box
        d.rectangle(box, fill=OUTLINE)
        d.rectangle((x0 + 1, y0 + 2, x1 - 1, y1 - 1), fill='#858097')
        d.rectangle((x0 + 1, y0 + 1, x1 - 1, y0 + 2), fill=WHITE)
        d.point((x0 + 2, y1 - 1), fill=WHITE)
        d.point((x1 - 2, y1 - 1), fill=WHITE)
    # Cymbals stay fixed: no whole-kit wobble or generated shape changes.
    for x in (15, 50):
        d.polygon([(x - 7, 38), (x - 3, 36), (x, 35), (x + 3, 36), (x + 7, 38)], fill=OUTLINE)
        d.line((x - 5, 37, x + 5, 37), fill=GOLD)
        d.line((x - 3, 36, x + 3, 36), fill='#f1dfaf')
        d.point((x, 35), fill=WHITE)
    return im


KIT = kit()


def arm(im, side, lift, target, wrist=0):
    """A sleeve pivots below the face; hair/face are restored after drawing."""
    d = ImageDraw.Draw(im)
    if side == 'left':
        shoulder = (27, 35)
        hand = (round(24 - 3 * lift), round(39 - 5 * lift))
        tip = (round(target[0] - 2 * lift), round(target[1] - 9 * lift))
        elbow = (24, 37)
    else:
        shoulder = (38, 35)
        hand = (round(40 + 3 * lift), round(38 - 4 * lift))
        tip = (round(target[0] + 2 * lift), round(target[1] - 9 * lift))
        elbow = (41, 36)
    hand = (hand[0] + round(wrist), hand[1])
    tip = (tip[0] + round(2 * wrist), tip[1])
    d.line((shoulder, elbow, hand), fill=OUTLINE, width=5)
    d.line((shoulder, elbow, hand), fill=WHITE, width=3)
    d.line((hand, tip), fill=OUTLINE, width=2)
    d.line((hand, tip), fill='#e1c3a6', width=1)
    d.point(hand, fill=SKIN)


def performance(index):
    # 3 phrases x 4 beats x 16 phases = 192 frames. The first phrase is a basic
    # alternating groove, then a tom fill, then alternating cymbal accents.
    phrase, phase = divmod(index, 64)
    beat, step = divmod(phase, 16)
    left_pattern = ((23, 38), (23, 38), (23, 38), (15, 36))
    right_pattern = ((40, 36), (40, 36), (50, 36), (50, 36))
    if phrase == 1:
        left_pattern = ((23, 38), (27, 39), (23, 38), (27, 39))
        right_pattern = ((38, 36), (43, 36), (38, 36), (43, 36))
    elif phrase == 2:
        left_pattern = ((15, 36), (23, 38), (15, 36), (23, 38))
        right_pattern = ((50, 36), (40, 36), (50, 36), (40, 36))
    # Strike at phase 0; smooth recovery then quicker downstroke. The opposite
    # arm is half a beat behind, so the silhouette never flips abruptly.
    def lift(t):
        return (1 - math.cos(2 * math.pi * (t % 16) / 16)) / 2
    im = BASE.copy()
    im.alpha_composite(KIT)
    arm(im, 'left', lift(step), left_pattern[beat], math.sin(2 * math.pi * step / 16))
    arm(im, 'right', lift(step + 8), right_pattern[beat], math.sin(2 * math.pi * (step + 8) / 16))
    # Invariant: every native pixel above the jacket remains EXACTLY original.
    im.paste(BASE.crop((21, 0, 45, 34)), (21, 0))
    return im


def entrance(index):
    im = BASE.copy()
    d = ImageDraw.Draw(im)
    # Reach for the case, open it, pull out the bass drum, unfold the stands,
    # then lift the sticks. No body zoom, no character replacement silhouette.
    if index < 10:
        d.rectangle((26, 44, 39, 50), fill=OUTLINE)
        d.rectangle((27, 45, 38, 49), fill='#858097')
        d.rectangle((30, 43, 34, 44), fill=OUTLINE)
        reach = min(1, index / 6)
        d.line(((27, 35), (24, 38), (round(25 + 4 * reach), round(39 + 5 * reach))), fill=OUTLINE, width=5)
        d.line(((27, 35), (24, 38), (round(25 + 4 * reach), round(39 + 5 * reach))), fill=WHITE, width=3)
        if index >= 6:
            d.polygon(((26, 44), (26 - (index - 6), 41), (39 - (index - 6), 41), (39, 44)), fill=STEEL)
    elif index < 24:
        p = (index - 10) / 13
        # The rigid kit emerges from the case as one object. No random frame
        # changes, resampling or alpha fades. After frame 23 it is stationary.
        dy = round((1 - p) * 10)
        visible = KIT.copy()
        mask = Image.new('RGBA', (64, 64))
        mask.alpha_composite(visible, (0, dy))
        mask.paste((0, 0, 0, 0), (0, 52, 64, 64))
        im.alpha_composite(mask)
        d = ImageDraw.Draw(im)
        d.line(((27, 35), (24, 38), (22, 42)), fill=OUTLINE, width=5)
        d.line(((27, 35), (24, 38), (22, 42)), fill=WHITE, width=3)
    else:
        im.alpha_composite(KIT)
        arm(im, 'left', 0, (23, 38))
        arm(im, 'right', (index - 24) / 7, (40, 36))
    im.paste(BASE.crop((21, 0, 45, 34)), (21, 0))
    return im


def atlas(frames, filename):
    columns = 16
    im = Image.new('RGBA', (64 * columns, 64 * math.ceil(len(frames) / columns)))
    for i, frame in enumerate(frames):
        im.paste(frame, ((i % columns) * 64, (i // columns) * 64))
    im.save(SPRITES / filename)


frames = [performance(i) for i in range(192)]
intro = [entrance(i) for i in range(32)]
# Start/end contact lines match idle and sit, so geometry doesn't move the pet.
atlas(frames, 'drums-native-loop.png')
atlas(intro, 'drums-native-in.png')
atlas(list(reversed(intro)), 'drums-native-out.png')

# Use the original compiled graph, keeping all native idle/walk/drag/sleep,
# weather overlays and behaviour names. Replace only the six dance states.
original = (SOURCE / 'builtin.toml').read_text(encoding='utf-8')
parsed = tomllib.loads(original)
lines = ['# Native Nayu graph; only musical performances are replaced.']
def value(v):
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, str): return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list): return '[' + ', '.join(value(x) for x in v) + ']'
    return str(v)
def fields(table):
    for k, v in table.items():
        if not isinstance(v, dict) and not (isinstance(v, list) and v and isinstance(v[0], dict)):
            lines.append(f'{k} = {value(v)}')
    lines.append('')
parsed['animations']['name'] = 'Nayu — автоматические барабаны'
for clip in parsed['clips']:
    if clip['name'].startswith('dance_'):
        band = clip['name'].split('_')[1]
        clip.update(file='sprites/drums-native-loop.png', frames=192, seat=52,
                    fps={'slow': 22.6667, 'mid': 30.9333, 'fast': 40.0}[band])
parsed['clips'].extend([
    dict(name='drums_in', file='sprites/drums-native-in.png', frames=32, fps=24, seat=52, loop=False),
    dict(name='drums_out', file='sprites/drums-native-out.png', frames=32, fps=24, seat=52, loop=False),
])
for name, state in parsed['states'].items():
    if isinstance(state, dict) and 'dance_' in name:
        state.update(start='drums_in', end='drums_out')
        for transition in state.get('transitions', []):
            if transition['on'].startswith('music_') and transition['on'] != 'music_stop':
                transition['cut'] = True
for band in ('slow', 'mid', 'fast'):
    parsed['states']['solo_' + band] = {
        'clip': 'dance_' + band, 'loop': True, 'start': 'drums_in', 'end': 'drums_out',
        'transitions': [{'on': 'dragged', 'to': 'drag'}, {'on': 'drag_end', 'to': 'idle'}],
    }
for section in ('animations', 'sprite', 'overlay'):
    lines.append(f'[{section}]'); fields(parsed[section])
for section in ('clips', 'overlay_clips'):
    for clip in parsed[section]:
        lines.append(f'[[{section}]]'); fields(clip)
for section in ('states', 'overlays'):
    lines.append(f'[{section}]')
    for k, v in parsed[section].items():
        if not isinstance(v, dict): lines.append(f'{k} = {value(v)}')
    lines.append('')
    for name, state in parsed[section].items():
        if not isinstance(state, dict): continue
        lines.append(f'[{section}.{name}]'); fields(state)
        for subkey, subvalue in state.items():
            if isinstance(subvalue, list) and subvalue and isinstance(subvalue[0], dict):
                for row in subvalue:
                    lines.append(f'[[{section}.{name}.{subkey}]]'); fields(row)
destination = PACK / 'animsets/pixel-drummer-beats/animset.toml'
destination.write_text('\n'.join(lines), encoding='utf-8')
tomllib.loads(destination.read_text(encoding='utf-8'))

# Reviewable preview at the actual native scale, with original beside drummer.
preview = Image.new('RGBA', (512, 256), '#353047')
preview.alpha_composite(BASE.resize((256, 256), Image.Resampling.NEAREST))
preview.alpha_composite(frames[0].resize((256, 256), Image.Resampling.NEAREST), (256, 0))
preview.save(ROOT / 'assets/native-comparison.png')
gif = [im.resize((256, 256), Image.Resampling.NEAREST) for im in intro + frames[:64] + list(reversed(intro))]
gif[0].save(ROOT / 'assets/native-animation.gif', save_all=True, append_images=gif[1:], duration=42, loop=0, disposal=2)
(ROOT / 'assets/native-build.json').write_text(json.dumps({
    'base_sha256': hashlib.sha256(BASE.tobytes()).hexdigest(),
    'frames': 192, 'entrance_frames': 32, 'exit_frames': 32, 'frame_size': 64,
    'native_scale': 4, 'head_identical_all_frames': all(im.crop((21, 0, 45, 34)).tobytes() == BASE.crop((21, 0, 45, 34)).tobytes() for im in frames + intro),
    'kit_sha256': hashlib.sha256(KIT.tobytes()).hexdigest(),
}, indent=2))
print('Built 192 performance frames + 32 entrance + 32 exit, native 64px scale4')
