"""Platform paths and capabilities without importing desktop or audio APIs."""
import os
from pathlib import Path
import sys


def config_directory():
    if sys.platform == 'win32':
        roaming = Path(os.environ['APPDATA']) if os.environ.get('APPDATA') else Path.home() / 'AppData' / 'Roaming'
        return roaming / 'astra' / 'astra' / 'config'
    home = Path.home()
    if sys.platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'com.astra.astra'
    xdg = Path(os.environ.get('XDG_CONFIG_HOME', ''))
    return (xdg if xdg.is_absolute() else home / '.config') / 'astra'


def is_wayland():
    backend = os.environ.get('QT_QPA_PLATFORM', '').split(':', 1)[0].lower()
    return backend.startswith('wayland') or (not backend and os.environ.get('XDG_SESSION_TYPE', '').lower() == 'wayland')


def capabilities():
    return {'desktop_events': sys.platform == 'win32', 'screen_walking': not is_wayland(),
            'platform': sys.platform, 'wayland': is_wayland()}


def process_alive(pid):
    if not pid:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def recording_source(soundcard):
    # CoreAudio has no speaker loopback. Only an explicitly named virtual
    # route is allowed there; never fall back to the default physical input.
    if sys.platform == 'darwin':
        selected = os.environ.get('PIXEL_DRUMMER_LOOPBACK_DEVICE', '').strip()
        if not selected:
            raise RuntimeError('Для реакции на музыку macOS укажите виртуальное устройство в PIXEL_DRUMMER_LOOPBACK_DEVICE. Деморежимы доступны без захвата звука.')
        candidates = [m for m in soundcard.all_microphones() if str(m.id) == selected or m.name == selected]
        if len(candidates) != 1:
            raise RuntimeError('Указанное виртуальное звуковое устройство не найдено или имя неоднозначно.')
        return candidates[0]
    speaker = soundcard.default_speaker()
    if speaker is None:
        raise RuntimeError('Нет устройства воспроизведения')
    microphone = soundcard.get_microphone(speaker.id, include_loopback=True)
    if not microphone.isloopback:
        raise RuntimeError('Устройство не является speaker loopback')
    return microphone
