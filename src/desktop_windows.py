"""Windows read-only desktop geometry. Never moves windows, shortcuts or files."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
from pathlib import Path
import threading
import winreg


@dataclass(frozen=True)
class Surface:
    handle: int
    left: float
    top: float
    right: float
    bottom: float


def window_surfaces():
    user=ctypes.WinDLL('user32',use_last_error=True)
    dwm=ctypes.WinDLL('dwmapi')
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    user.IsIconic.argtypes=[wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]
    user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
    dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    result=[];cover=[]
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    @callback
    def visit(handle,_):
        if not user.IsWindowVisible(handle) or user.IsIconic(handle):return True
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        if pid.value==os.getpid() or user.GetWindowLongPtrW(handle,-20)&0x80:return True
        cloaked=wintypes.DWORD()
        if dwm.DwmGetWindowAttribute(handle,14,ctypes.byref(cloaked),4)==0 and cloaked.value:return True
        rect=wintypes.RECT()
        if dwm.DwmGetWindowAttribute(handle,9,ctypes.byref(rect),ctypes.sizeof(rect))!=0:return True
        if rect.right-rect.left<300 or rect.bottom-rect.top<180:return True
        mid=(rect.left+rect.right)/2
        hidden=any(l<=mid<r and t<=rect.top<b for l,t,r,b in cover)
        if not hidden:result.append(Surface(int(handle),rect.left,rect.top,rect.right,rect.bottom))
        cover.append((rect.left,rect.top,rect.right,rect.bottom))
        return True
    user.EnumWindows.argtypes=[callback,wintypes.LPARAM]
    user.EnumWindows(visit,0)
    return result


def desktop_shortcuts():
    directories=[Path(os.environ.get('PUBLIC',r'C:\Users\Public'))/'Desktop']
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
            directories.append(Path(os.path.expandvars(winreg.QueryValueEx(key,'Desktop')[0])))
    except OSError:directories.append(Path.home()/'Desktop')
    return {p.stem.casefold():p for folder in directories if folder.exists()
            for p in folder.iterdir() if p.suffix.lower() in ('.lnk','.url')}


def desktop_list_handle():
    user=ctypes.WinDLL('user32')
    user.FindWindowExW.argtypes=[wintypes.HWND,wintypes.HWND,wintypes.LPCWSTR,wintypes.LPCWSTR]
    user.FindWindowExW.restype=wintypes.HWND
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    found=[]
    @callback
    def visit(handle,_):
        view=user.FindWindowExW(handle,0,'SHELLDLL_DefView',None)
        if view:
            icons=user.FindWindowExW(view,0,'SysListView32',None)
            if icons:found.append(icons);return False
        return True
    user.EnumWindows.argtypes=[callback,wintypes.LPARAM];user.EnumWindows(visit,0)
    return found[0] if found else None


class IconObserver(threading.Thread):
    """Reads desktop item's existing bounds; no UIA patterns are invoked."""
    def __init__(self):
        super().__init__(daemon=True,name='desktop-icon-positions')
        self.stop_event=threading.Event();self.lock=threading.Lock()
        self.items=[];self.error=None

    def snapshot(self):
        with self.lock:return list(self.items)

    def run(self):
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            comtypes.client.gen_dir=None
            module=comtypes.client.GetModule('UIAutomationCore.dll')
            automation=comtypes.client.CreateObject('{ff48dba4-60ef-4201-aa87-54103eef594e}',interface=module.IUIAutomation)
            while not self.stop_event.is_set():
                handle=desktop_list_handle()
                desktop=automation.ElementFromHandle(handle) if handle else None
                items=[]
                if desktop:
                    children=desktop.FindAll(2,automation.CreateTrueCondition())
                    for i in range(children.Length):
                        item=children.GetElement(i)
                        if item.CurrentControlType!=50007:continue
                        rect=item.CurrentBoundingRectangle
                        if rect.right>rect.left and rect.bottom>rect.top:
                            items.append(dict(name=item.CurrentName,x=(rect.left+rect.right)/2,y=rect.top+24))
                with self.lock:self.items=items
                self.stop_event.wait(12)
        except Exception as error:self.error=f'{type(error).__name__}: {error}'
        finally:
            try:comtypes.CoUninitialize()
            except Exception:pass
