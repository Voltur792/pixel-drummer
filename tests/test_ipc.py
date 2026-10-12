import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from src.ipc import atomic_json


class IpcTests(unittest.TestCase):
    def test_brief_reader_lock_does_not_stop_controller(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'control.json'
            atomic_json(target, {'revision': 1})
            replace = Path.replace
            attempts = []

            def locked_then_released(source, destination):
                attempts.append(source)
                if len(attempts) < 3:
                    self.assertEqual(json.loads(target.read_text()), {'revision': 1})
                    raise PermissionError('reader has not closed its handle yet')
                return replace(source, destination)

            with patch.object(Path, 'replace', locked_then_released), patch('src.ipc.time.sleep'):
                atomic_json(target, {'revision': 2})
            self.assertEqual(json.loads(target.read_text()), {'revision': 2})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def test_persistent_failure_preserves_previous_complete_message(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'control.json'
            atomic_json(target, {'revision': 1})
            with patch.object(Path, 'replace', side_effect=PermissionError('locked')), patch('src.ipc.time.sleep'):
                with self.assertRaises(PermissionError):
                    atomic_json(target, {'revision': 2})
            self.assertEqual(json.loads(target.read_text()), {'revision': 1})
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])
