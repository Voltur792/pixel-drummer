"""Prevent importing Windows APIs or recording a physical input by default."""
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from src import platform_support as support


class PlatformTests(unittest.TestCase):
    def test_linux_and_macos_character_pack_paths(self):
        with TemporaryDirectory() as tmp, patch.object(Path, 'home', return_value=Path(tmp)):
            with patch.object(support.sys, 'platform', 'linux'), patch.dict(os.environ, {'XDG_CONFIG_HOME': str(Path(tmp) / 'cfg')}, clear=True):
                self.assertEqual(support.config_directory(), Path(tmp) / 'cfg' / 'astra')
            with patch.object(support.sys, 'platform', 'darwin'), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(support.config_directory(), Path(tmp) / 'Library' / 'Application Support' / 'com.astra.astra')

    def test_scene_scale_follows_astra_avatar_size(self):
        with TemporaryDirectory() as tmp:
            settings = Path(tmp) / 'settings.json'
            settings.write_text('{"companion": {"settings": {"windowSize": "390"}}}', encoding='utf-8')
            self.assertAlmostEqual(support.avatar_scale(settings), 2.6)
            settings.write_text('{"companion": {"settings": {"windowSize": 600}}}', encoding='utf-8')
            self.assertEqual(support.avatar_scale(settings), 4)
            settings.write_text('{"companion": {"enabled": true}}', encoding='utf-8')
            self.assertEqual(support.avatar_scale(settings), 4)
            self.assertEqual(support.avatar_scale(Path(tmp) / 'missing.json'), 4)

    def test_wayland_disables_screen_walking_but_xcb_override_does_not(self):
        with patch.object(support.sys, 'platform', 'linux'), patch.dict(os.environ, {'XDG_SESSION_TYPE': 'wayland'}, clear=True):
            self.assertFalse(support.capabilities()['screen_walking'])
            self.assertFalse(support.capabilities()['desktop_events'])
            with patch.dict(os.environ, {'QT_QPA_PLATFORM': 'xcb'}):
                self.assertTrue(support.capabilities()['screen_walking'])

    def test_non_windows_desktop_backend_imports_without_winreg(self):
        file = Path(__file__).parents[1] / 'src' / 'desktop.py'
        spec = importlib.util.spec_from_file_location('src.test_desktop_backend', file)
        module = importlib.util.module_from_spec(spec)
        with patch.object(support.sys, 'platform', 'linux'):
            spec.loader.exec_module(module)
        self.assertEqual(module.window_surfaces(), [])
        self.assertEqual(module.desktop_shortcuts(), {})
        self.assertEqual(module.IconObserver().snapshot(), [])

    def test_macos_without_explicit_route_never_opens_input(self):
        card = Mock()
        with patch.object(support.sys, 'platform', 'darwin'), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'виртуальное устройство'):
                support.recording_source(card)
        card.get_microphone.assert_not_called()
        card.all_microphones.assert_not_called()

    def test_macos_route_requires_exact_unambiguous_selection(self):
        route = SimpleNamespace(id='virtual-id', name='My music route')
        card = Mock()
        card.all_microphones.return_value = [route, SimpleNamespace(id='physical', name='Built-in microphone')]
        with patch.object(support.sys, 'platform', 'darwin'), patch.dict(os.environ, {'PIXEL_DRUMMER_LOOPBACK_DEVICE': 'virtual-id'}, clear=True):
            self.assertIs(support.recording_source(card), route)
        card.default_speaker.assert_not_called()

    def test_linux_refuses_non_loopback_input(self):
        card = Mock()
        card.get_microphone.return_value.isloopback = False
        with patch.object(support.sys, 'platform', 'linux'), self.assertRaisesRegex(RuntimeError, 'loopback'):
            support.recording_source(card)

    def test_unix_parent_liveness_does_not_signal_or_terminate(self):
        with patch.object(support.os, 'kill', side_effect=PermissionError) as kill:
            self.assertTrue(support.process_alive(123))
            kill.assert_called_once_with(123, 0)
        with patch.object(support.os, 'kill', side_effect=ProcessLookupError):
            self.assertFalse(support.process_alive(123))
