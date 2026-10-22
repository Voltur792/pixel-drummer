"""Keep Windows desktop observation out of other platforms' import paths."""
import sys

if sys.platform == 'win32':
    from .desktop_windows import Surface, window_surfaces, desktop_shortcuts, IconObserver
else:
    from dataclasses import dataclass
    import threading

    @dataclass(frozen=True)
    class Surface:
        handle: int
        left: float
        top: float
        right: float
        bottom: float

    def window_surfaces():
        return []

    def desktop_shortcuts():
        return {}

    class IconObserver:
        error = None

        def __init__(self):
            self.stop_event = threading.Event()

        def start(self):
            pass

        def snapshot(self):
            return []
