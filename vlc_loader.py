"""Locate the system VLC installation before loading the Python binding."""
import os
from pathlib import Path
import sys

_DLL_DIR = None


def import_vlc():
    global _DLL_DIR
    if sys.platform == 'win32':
        candidates=[]
        for key in ('VLC_DIR','VLC_HOME'):
            if os.environ.get(key):candidates.append(Path(os.environ[key]))
        for key in ('PROGRAMFILES','PROGRAMFILES(X86)'):
            if os.environ.get(key):candidates.append(Path(os.environ[key])/'VideoLAN'/'VLC')
        for folder in candidates:
            if (folder/'libvlc.dll').is_file():
                os.environ.setdefault('VLC_PLUGIN_PATH',str(folder/'plugins'))
                if hasattr(os,'add_dll_directory'):
                    _DLL_DIR=os.add_dll_directory(str(folder))
                else:os.environ['PATH']=str(folder)+os.pathsep+os.environ.get('PATH','')
                break
    import vlc
    return vlc
