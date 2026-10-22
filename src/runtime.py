"""Own renderer lifecycle; never controls or terminates other applications."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from .assets import ROOT
from .ipc import atomic_json as write_json
from .platform_support import config_directory


def data_directory():
    if os.environ.get('PIXEL_DRUMMER_DATA'):
        return Path(os.environ['PIXEL_DRUMMER_DATA'])
    legacy = ROOT / 'data'
    target = legacy if os.name == 'nt' else config_directory() / 'pixel-drummer'
    if (legacy / 'settings.json').exists() and not (target / 'settings.json').exists():
        return legacy
    return target


class Runtime:
    def __init__(self):
        self.data=data_directory()
        self.process=None
        self.session=None
        self.task=None
        self.log=None
        self.controller_seen=time.monotonic()
        self.control=dict(mode='auto',instrument='auto',roam=True,effects=True,visible=False,revision=0)
        saved={}
        try:
            saved=json.loads((self.data/'settings.json').read_text(encoding='utf-8'))
            for k in ('instrument','roam','effects'):
                if k in saved:self.control[k]=saved[k]
        except (OSError,ValueError):
            pass
        self.saved_position=saved.get('position')
        self.request_payload={}
        # Keep the same native frame centre/contact line on first activation.
        # Only companion geometry is read; other app settings are untouched.
        try:
            folder=config_directory()/'companion'
            settings=json.loads((folder/'settings.json').read_text(encoding='utf-8'))
            window=settings['window'];size=window['size'];x,y=window['pos']
            native_position=[x+size/2,y+size/2+(52-32)*4]
            if isinstance(saved.get('position'),list):
                native_position=saved['position']
            self.control['position']=native_position
        except (OSError,ValueError,KeyError,TypeError):
            pass

    def publish(self):
        if self.session:
            write_json(self.data/'control.json',dict(self.control,session=self.session,lease=time.monotonic()))

    def configure(self,**changes):
        allowed={'mode','instrument','roam','effects','visible','position','walk_to','stop','preview','desktop_event'}
        for key in ('position','walk_to','preview','desktop_event'):
            if key not in changes:self.control.pop(key,None)
        self.control.update({k:v for k,v in changes.items() if k in allowed})
        self.control['revision']+=1
        settings={k:self.control[k] for k in ('instrument','roam','effects')}
        if self.saved_position:settings['position']=self.saved_position
        write_json(self.data/'settings.json',settings)
        self.publish()

    def status(self, controller=True):
        if controller:self.controller_seen=time.monotonic()
        alive=self.process is not None and self.process.poll() is None
        try:
            state=json.loads((self.data/'renderer-status.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):
            state={}
        fresh=state.get('session')==self.session and time.monotonic()-state.get('heartbeat',0)<3
        return dict(alive=alive,ready=bool(alive and fresh and state.get('ready')),detail=state if fresh else {},control=self.control)

    async def start(self):
        if self.status()['ready']:
            return self.status()
        if self.process and self.process.poll() is None:
            await self.stop()
        self.data.mkdir(parents=True,exist_ok=True)
        self.session=uuid.uuid4().hex
        self.control.update(stop=False,visible=False)
        if 'position' not in self.control and self.saved_position:
            self.control['position']=list(self.saved_position)
        self.publish()
        self.log=(self.data/'renderer.log').open('w',encoding='utf-8')
        environment={k:v for k,v in os.environ.items() if not k.upper().startswith('ASTRA_')}
        self.process=subprocess.Popen([sys.executable,'-m','src.renderer','--data',str(self.data),
                                       '--parent',str(os.getpid()),'--session',self.session],
                                      cwd=ROOT,env=environment,stdin=subprocess.DEVNULL,
                                      stdout=self.log,stderr=self.log,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.task=asyncio.create_task(self.maintain())
        for _ in range(80):
            state=self.status()
            if state['ready']:return state
            if not state['alive']:break
            await asyncio.sleep(.1)
        await self.stop()
        raise RuntimeError('Музыкальный рендерер не запустился; обычная Nayu сохранена. См. data/renderer.log')

    async def maintain(self):
        while self.process and self.process.poll() is None:
            if time.monotonic()-self.controller_seen>4.5:
                # If the DOM vanishes, stop our scene before the native blank
                # one-shot expires into Astra's full original animation graph.
                self.configure(stop=True,visible=False)
                return
            self.publish()
            await asyncio.sleep(.5)

    def consume_request(self):
        path=self.data/'renderer-request.json'
        try:
            request=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            return None
        path.unlink(missing_ok=True)
        if request.get('session')!=self.session:return None
        mode=request.get('mode')
        if mode in ('auto','slow','mid','fast','walk','restore','concert'):
            # The UI must prepare/hide the native companion before a one-shot
            # desktop action is sent. Publishing twice could lose that action.
            self.request_payload={k:v for k,v in request.items() if k in
                                  ('instrument','roam','effects','position','walk_to','preview','desktop_event')}
            return mode
        self.configure(**request)
        return None

    async def stop(self):
        process=self.process
        current=self.status(controller=False).get('detail',{}).get('position')
        if current:
            self.saved_position=current
        if process and process.poll() is None:
            self.configure(stop=True,visible=False)
            for _ in range(15):
                if process.poll() is not None:break
                await asyncio.sleep(.1)
            if process.poll() is None:
                process.terminate()
                await asyncio.to_thread(process.wait,2)
        if self.task:
            self.task.cancel()
            self.task=None
        if self.log:self.log.close();self.log=None
        self.process=None
