"""Render a frame offscreen with audio and desktop observation replaced."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from src import renderer
from src.ipc import atomic_json
from src.rhythm import Analyzer


class RendererTests(unittest.TestCase):
    def test_wayland_scene_draws_without_desktop_or_audio_devices(self):
        app = QApplication.instance() or QApplication([])
        audio = Mock()
        audio.snapshot.return_value = Analyzer().snapshot(time.monotonic())
        desktop = Mock(phase=None, borrowed=[], windows=[], events=[])
        desktop.tick.return_value = False
        desktop.observer.snapshot.return_value = []
        desktop.observer.error = None
        features = dict(desktop_events=False, screen_walking=False, platform='linux', wayland=True)
        with TemporaryDirectory() as tmp, patch.object(renderer, 'Loopback', return_value=audio), patch.object(renderer, 'DesktopPlay', return_value=desktop), patch.object(renderer, 'capabilities', return_value=features):
            atomic_json(Path(tmp) / 'control.json', dict(session='test', lease=time.monotonic(), mode='fast', roam=True, visible=False, revision=1))
            scene = renderer.Companion(tmp, os.getpid(), 'test', demo=True)
            try:
                self.assertFalse(scene.roam)
                self.assertFalse(scene.grab().isNull())
                state = json.loads((Path(tmp) / 'renderer-status.json').read_text('utf-8'))
                self.assertTrue(state['ready'])
                self.assertFalse(state['platform_features']['desktop_events'])
                self.assertFalse(state['platform_features']['screen_walking'])
            finally:
                scene.timer.stop()
                scene.concert.close()
                scene.close()
                scene.deleteLater()
                app.processEvents()
