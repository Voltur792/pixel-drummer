"""Protect the user's character pack and exercise actual SDK UI dispatch."""
import asyncio
import hashlib
import json
from pathlib import Path
import tomllib
from tempfile import TemporaryDirectory
import unittest
import unittest.mock
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

    def test_files_the_engine_migrated_to_schema_5_are_still_ours(self):
        # Astra 0.2.7 converts schema 4 packs in place: it backs the old tree up
        # in .pre-migration-*, renames keys and gives every animation pack a uid.
        with TemporaryDirectory() as tmp:
            pack = Path(tmp)
            (pack / "companion.toml").write_text("[meta]\nschema_version = 5\n", encoding="utf-8")
            legacy = b'[character]\nkind="pixel"\nmodel="builtin:nayu-2d"\nanimations="pixel-band-proxy"\n'
            backup = pack / ".pre-migration-1" / "characters" / "pixel-band-proxy" / "character.toml"
            backup.parent.mkdir(parents=True)
            backup.write_bytes(legacy)
            graph = b'[animations]\nkind = "pixel"\n'
            old_graph = pack / ".pre-migration-1" / "animsets" / "pixel-band-proxy" / "animset.toml"
            old_graph.parent.mkdir(parents=True)
            old_graph.write_bytes(graph)
            (pack / "pixel-drummer-receipt.json").write_text(json.dumps({
                "characters/pixel-band-proxy/character.toml": hashlib.sha256(legacy).hexdigest(),
                "animsets/pixel-band-proxy/animset.toml": hashlib.sha256(graph).hexdigest(),
            }), encoding="utf-8")
            migrated = pack / "characters" / "pixel-band-proxy" / "character.toml"
            migrated.parent.mkdir(parents=True)
            migrated.write_bytes(legacy.replace(b"animations=", b"animpack="))
            converted = pack / "animpacks" / "pixel-band-proxy" / "animpack.toml"
            converted.parent.mkdir(parents=True)
            converted.write_bytes(b'[animpack]\nkind = "pixel"\nuid = "user.0123456789abcdef"\n')
            self.assertTrue(install(pack)["installed"])
            character = tomllib.loads(migrated.read_text(encoding="utf-8"))["character"]
            self.assertEqual(character["animpack"], "pixel-band-proxy")
            self.assertNotIn("animations", character)
            graph = tomllib.loads(converted.read_text(encoding="utf-8"))
            self.assertEqual(graph["animpack"]["uid"], "user.0123456789abcdef")
            self.assertIn("states", graph)
            self.assertTrue((pack / "animpacks" / "pixel-drummer-beats" / "clips" / "drums-native-loop.png").exists())
            self.assertFalse((pack / "animsets").exists())
            # The uid we kept is what the receipt now vouches for.
            install(pack)
            self.assertIn(b"user.0123456789abcdef", converted.read_bytes())

    def test_old_astra_pack_is_refused_without_writing(self):
        with TemporaryDirectory() as tmp:
            pack = Path(tmp)
            (pack / "companion.toml").write_text("[meta]\nschema_version = 4\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "0.2.7"):
                install(pack)
            self.assertEqual([p.name for p in pack.iterdir()], ["companion.toml"])

    def test_diagnostic_reports_the_manifest_version(self):
        with TemporaryDirectory() as tmp, unittest.mock.patch.dict("os.environ", {"PIXEL_DRUMMER_DATA": tmp}):
            asyncio.run(PixelDrummer().handle_ui_call("report", json.dumps({"payload": {"version": "0.4.1", "ok": True}})))
            written = json.loads((Path(tmp) / "diagnostic.json").read_text(encoding="utf-8"))
            manifest = tomllib.loads((Path(__file__).resolve().parents[1] / "plugin.toml").read_text(encoding="utf-8"))
            self.assertEqual(written["version"], manifest["plugin"]["version"])

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
