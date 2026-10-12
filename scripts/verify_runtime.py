"""Development smoke test of the real GUI/audio child, hidden by default."""
import asyncio
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.runtime import Runtime


async def main():
    with TemporaryDirectory(prefix='pixel-band-smoke-') as directory:
        os.environ['PIXEL_DRUMMER_DATA']=directory
        runtime=Runtime()
        try:
            start=await runtime.start()
            assert start['ready']
            runtime.configure(mode='mid',instrument='guitar',visible=False)
            await asyncio.sleep(3)
            status=runtime.status()
            assert status['ready'],status
            detail=status['detail']
            assert detail['state']=='play',detail
            assert detail['instrument']=='guitar',detail
            assert detail['audio']['audio_ready'],detail['audio']
            assert detail['audio']['tag_ready'],detail['audio']
            runtime.configure(mode='concert',visible=False)
            await asyncio.sleep(2)
            concert=runtime.status()['detail']
            assert concert['concert']['active'] and concert['concert']['performers']==4,concert
            runtime.configure(mode='walk',walk_to=2)
            await asyncio.sleep(3)
            idle=runtime.status()['detail']
            assert idle['state'] in ('idle','walk'),idle
            assert not idle['concert']['active'],idle
            assert idle['desktop']['icons_seen']>0 and not idle['desktop']['observer_error'],idle
            # Request is the same mechanism as the renderer's context menu.
            path=Path(directory)/'renderer-request.json'
            path.write_text(json.dumps(dict(session=runtime.session,instrument='microphone',effects=False)),encoding='utf-8')
            runtime.consume_request()
            assert runtime.control['instrument']=='microphone'
            assert not runtime.control['effects']
            # Restore/re-enable must preserve the last location rather than
            # restarting on the primary screen. Exercise a real second child.
            saved_position=runtime.status()['detail']['position']
            first_child=runtime.process
            await runtime.stop()
            assert first_child.poll() is not None
            runtime.configure(mode='mid',instrument='guitar',stop=False)
            restarted=await runtime.start()
            assert restarted['ready'],restarted
            assert restarted['detail']['position']==saved_position,restarted
            print(json.dumps(dict(ready=True,three_screens=len(detail['screens'])==3,
                                  audio_ready=True,forced_guitar=detail['state'],
                                  audio_tags=True,concert_four_performers=True,concert_exit=True,desktop_icon_geometry=True,
                                  stop_to_idle=idle['state'],menu_request=True,
                                  reactivation_keeps_position=True,
                                  render_interval_ms=detail['render_interval_ms']),indent=2))
        finally:
            child=runtime.process
            await runtime.stop()
            assert child is None or child.poll() is not None
            print('Own renderer exited; no orphan process')


asyncio.run(main())
