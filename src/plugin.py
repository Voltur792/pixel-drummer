"""Automatic native Nayu drums. Commands run in the permitted DOM context."""
import json
import os
from pathlib import Path
from astra_plugin_sdk import Plugin, ui_call, tool, action
from . import VERSION
from .assets import install, CHARACTER, ANIMSET
from .runtime import Runtime, data_directory


class PixelDrummer(Plugin):
    def __init__(self):
        super().__init__()
        self.pending = None
        self.diagnostic = {}
        self.runtime = Runtime()

    async def get_ui_contributions(self):
        return [self.ui_effect("drummer.js", id="drummer-controller")]

    @ui_call
    async def prepare(self):
        assets = install()
        renderer = await self.runtime.start()
        return dict(assets, renderer=renderer, proxy="pixel-band-proxy")

    @ui_call
    async def configure(self, payload: dict):
        self.runtime.configure(**payload)
        return self.runtime.status()

    @ui_call
    async def stop_renderer(self):
        await self.runtime.stop()
        return {"ok": True}

    async def on_shutdown(self):
        await self.runtime.stop()

    @ui_call
    async def status(self):
        request = self.runtime.consume_request()
        if request:
            self.pending = request
        operation, self.pending = self.pending, None
        payload,self.runtime.request_payload=self.runtime.request_payload,{}
        return {"character": "pixel-band-proxy", "animset": ANIMSET,
                "operation": operation, "operation_payload":payload,"renderer": self.runtime.status()}

    @ui_call
    async def report(self, payload: dict):
        payload = {**payload, "version": VERSION}
        self.diagnostic = payload
        # This contains only our own command results, not session tokens or app settings.
        destination = data_directory()
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "diagnostic.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    @tool("Control Nayu's musical scene: auto (music-driven), slow/mid/fast (demo), walk (no instruments), restore (ordinary native companion). Requires Astra's UI controller to be loaded.")
    async def drums(self, mode: str = "auto"):
        if mode not in {"auto", "slow", "mid", "fast", "walk", "restore"}:
            raise ValueError("mode: auto, slow, mid, fast, walk, restore")
        self.pending = mode
        return {"queued": mode, "message": "Команда передана фоновому контроллеру барабанов."}

    @tool("Select Nayu's music instrument: auto, drums, guitar (electric guitar), microphone, keyboard (synthesizer/electric piano). Local audio classification selects instruments and detects vocals; music controls automatic playing. Optional roam enables desktop walking, effects enables particles.")
    async def band(self, instrument: str = "auto", roam: bool = True, effects: bool = True):
        if instrument not in {"auto", "drums", "guitar", "microphone", "keyboard"}:
            raise ValueError("instrument: auto, drums, guitar, microphone, keyboard")
        self.runtime.configure(instrument=instrument,roam=roam,effects=effects)
        self.pending = "auto"
        return {"queued": True,"instrument":instrument,"roam":roam,"effects":effects}

    @tool("Show or hide Nayu's four-person music stage. Use enabled=true for spoken 'Собери группу на сцене', 'Покажи музыкальную сцену', 'Включи концерт'. Four Nayu performers walk on with drums, red electric guitar, microphone and synthesizer. Use enabled=false for 'Убери сцену', 'Выключи концерт', returning one companion to automatic music mode.")
    async def concert(self, enabled: bool = True):
        self.runtime.configure(instrument='auto')
        self.pending='concert' if enabled else 'auto'
        return {'queued':self.pending,'message':'Группа выходит на сцену.' if enabled else 'Сцена убирается, включён автоматический режим.'}

    @action('Показать музыкальную сцену', ai_available=True, ai_description='Собери группу на сцене: четыре Nayu с инструментами')
    async def show_stage(self):
        return await self.concert(True)

    @action('Убрать сцену и включить автоматический режим', ai_available=True, ai_description='Убери сцену, выключи концерт и верни автоматический режим')
    async def hide_stage(self):
        return await self.concert(False)


if __name__ == "__main__":
    PixelDrummer().run()
