"""Regression checks for the reported size, wobble and automatic-mode bugs."""
from pathlib import Path
import tomllib
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'src/resources/assets/pack'
SPRITES = PACK / 'characters/pixel-drummer-nayu/sprites'


class AnimationTests(unittest.TestCase):
    def test_native_graph_preserves_daily_behaviour_and_music_brackets(self):
        native = tomllib.loads((PACK / 'animsets/pixel-band-proxy/animset.toml').read_text(encoding='utf-8'))
        current = tomllib.loads((PACK / 'animsets/pixel-drummer-beats/animset.toml').read_text(encoding='utf-8'))
        self.assertEqual(current['sprite'], native['sprite'])
        for state in ('idle', 'sit', 'sit_walk', 'drag', 'sleep', 'greet', 'action'):
            self.assertEqual(current['states'][state], native['states'][state])
        for prefix in ('dance_', 'sit_dance_'):
            for band in ('slow', 'mid', 'fast'):
                state = current['states'][prefix + band]
                self.assertEqual((state['start'], state['end']), ('drums_in', 'drums_out'))
                self.assertTrue(any(t['on'] == 'music_stop' for t in state['transitions']))
        self.assertEqual(current['overlays'], native['overlays'])

    def test_head_is_original_and_lower_kit_never_moves(self):
        original = Image.open(ROOT / 'src/resources/assets/band/idle.png').convert('RGBA')
        atlas = Image.open(SPRITES / 'drums-native-loop.png').convert('RGBA')
        first = atlas.crop((0, 0, 64, 64))
        head = original.crop((21, 0, 45, 34)).tobytes()
        ground = first.crop((0, 43, 64, 64)).tobytes()
        self.assertEqual(atlas.size, (1024, 768))
        masks = set()
        for index in range(192):
            x, y = index % 16 * 64, index // 16 * 64
            frame = atlas.crop((x, y, x + 64, y + 64))
            self.assertEqual(frame.crop((21, 0, 45, 34)).tobytes(), head)
            self.assertEqual(frame.crop((0, 43, 64, 64)).tobytes(), ground)
            masks.add(frame.tobytes())
        # Pixel snapping may duplicate adjacent high-FPS frames, but there must
        # be many genuinely different poses, not 192 copies of four pictures.
        self.assertGreater(len(masks), 40)

    def test_intro_connects_to_loop_and_exit_reverses_intro(self):
        intro = Image.open(SPRITES / 'drums-native-in.png').convert('RGBA')
        loop = Image.open(SPRITES / 'drums-native-loop.png').convert('RGBA')
        outro = Image.open(SPRITES / 'drums-native-out.png').convert('RGBA')
        last = intro.crop((15 * 64, 64, 16 * 64, 128))
        self.assertEqual(last.tobytes(), loop.crop((0, 0, 64, 64)).tobytes())
        for index in range(32):
            opposite = 31 - index
            a = intro.crop((index % 16 * 64, index // 16 * 64, index % 16 * 64 + 64, index // 16 * 64 + 64))
            b = outro.crop((opposite % 16 * 64, opposite // 16 * 64, opposite % 16 * 64 + 64, opposite // 16 * 64 + 64))
            self.assertEqual(a.tobytes(), b.tobytes())


if __name__ == '__main__':
    unittest.main()
