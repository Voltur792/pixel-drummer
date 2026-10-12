"""Extract unmodified built-in PNGs and TOML from the installed avatar engine.

Local development only. Never patches the executable or redistributes its art.
"""
from pathlib import Path
import hashlib
import json
import struct
import zlib
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
EXE = Path.home() / 'AppData/Local/Programs/Astra/astra-avatar-engine.exe'
OUT = ROOT / 'assets/native-source'
OUT.mkdir(parents=True, exist_ok=True)
binary = EXE.read_bytes()
signature = b'\x89PNG\r\n\x1a\n'
position = 0
records = []
while True:
    position = binary.find(signature, position)
    if position < 0:
        break
    cursor = position + 8
    try:
        width, height = struct.unpack('>II', binary[position + 16:position + 24])
        if not (64 <= width <= 2048 and 64 <= height <= 2048):
            raise ValueError('not a sprite')
        while True:
            length = struct.unpack('>I', binary[cursor:cursor + 4])[0]
            kind = binary[cursor + 4:cursor + 8]
            payload = binary[cursor + 8:cursor + 8 + length]
            crc = struct.unpack('>I', binary[cursor + 8 + length:cursor + 12 + length])[0]
            if zlib.crc32(kind + payload) != crc:
                raise ValueError('bad CRC')
            cursor += length + 12
            if kind == b'IEND':
                break
        data = binary[position:cursor]
        name = f'{len(records):02d}-{width}x{height}.png'
        (OUT / name).write_bytes(data)
        records.append({'name': name, 'offset': position, 'sha256': hashlib.sha256(data).hexdigest()})
    except (ValueError, struct.error):
        pass
    position += 8

anchor = binary.index(b'[states.sit_walk]')
start = binary.rfind(b'[animations]', 0, anchor)
end = binary.index(b'\0', start)
(OUT / 'builtin.toml').write_bytes(binary[start:end])
(OUT / 'provenance.json').write_text(json.dumps({'executable_sha256': hashlib.sha256(binary).hexdigest(), 'images': records}, indent=2))

sheet = Image.new('RGB', (800, ((len(records) + 3) // 4) * 165), '#333044')
draw = ImageDraw.Draw(sheet)
for index, record in enumerate(records):
    sprite = Image.open(OUT / record['name']).convert('RGBA').crop((0, 0, 64, 64)).resize((128, 128), Image.Resampling.NEAREST)
    x, y = (index % 4) * 200, (index // 4) * 165
    sheet.paste(sprite, (x + 30, y + 22), sprite)
    draw.text((x + 8, y + 4), record['name'], fill='white')
sheet.save(OUT / 'contact.png')
print(f'Extracted {len(records)} unmodified PNGs and native TOML into {OUT}')
