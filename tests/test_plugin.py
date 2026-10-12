"""Protect the user's character pack and exercise actual SDK UI dispatch."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from src.ipc import atomic_json
from src.assets import install
from src.plugin import PixelDrummer


class PluginTests(unittest.TestCase):
    def test_install_preserves_other_characters_and_active_selection(self):
        with TemporaryDirectory() as tmp:
            pack = Path(tmp)
            original = b'[pet]\ncharacter = "my-custom-character"\n'
            (pack / "companion.toml").write_bytes(original)
            other = pack / "characters" / "my-custom-character" / "character.toml"
            other.parent.mkdir(parents=True)
            other.write_text("custom character", encoding="utf-8")
            first = install(pack)
            self.assertTrue(first["installed"])
            self.assertEqual(install(pack), first)
            self.assertEqual((pack / "companion.toml").read_bytes(), original)
            self.assertEqual(other.read_text(encoding="utf-8"), "custom character")

    def test_edited_asset_is_protected_before_any_file_is_replaced(self):
        with TemporaryDirectory() as tmp:
            pack = Path(tmp)
            install(pack)
            own = pack / "characters" / "pixel-drummer-nayu" / "character.toml"
            own.write_text("user-painted version", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Файл изменён"):
                install(pack)
            self.assertEqual(own.read_text(encoding="utf-8"), "user-painted version")

    def test_sdk_accepts_empty_request_and_delivers_voice_command_once(self):
        async def run():
            plugin = PixelDrummer()
            contribution, = await plugin.get_ui_contributions()
            self.assertEqual(contribution.slot, "background.behind")
            self.assertFalse(contribution.pointer_events)
            self.assertTrue(contribution.transparent)
            result = await plugin.handle_ui_call("status", "{}")
            self.assertIsNone(result["operation"])
            await plugin.drums("fast")
            self.assertEqual((await plugin.handle_ui_call("status", "{}"))["operation"], "fast")
            self.assertIsNone((await plugin.handle_ui_call("status", "{}"))["operation"])
            with self.assertRaises(ValueError):
                await plugin.drums("invalid")
            await plugin.concert(True)
            self.assertEqual((await plugin.handle_ui_call('status','{}'))['operation'],'concert')
            self.assertIsNone((await plugin.handle_ui_call('status','{}'))['operation'])
            await plugin.concert(False)
            self.assertEqual((await plugin.handle_ui_call('status','{}'))['operation'],'auto')
            with TemporaryDirectory() as directory:
                plugin.runtime.data=Path(directory);plugin.runtime.session='test-session'
                atomic_json(Path(directory)/'renderer-request.json',dict(session='test-session',mode='walk',desktop_event='three'))
                status=await plugin.handle_ui_call('status','{}')
                self.assertEqual(status['operation'],'walk')
                self.assertEqual(status['operation_payload'],{'desktop_event':'three'})
                self.assertNotIn('desktop_event',plugin.runtime.control)
                next_status=await plugin.handle_ui_call('status','{}')
                self.assertEqual(next_status['operation_payload'],{})
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
