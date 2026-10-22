"""V1.5 entry point: PySide6 by default, v1.4 Tkinter via --legacy-gui.

Keep --cli for the original renderer/AI subprocess and packaged runtime.
"""
import sys
from pathlib import Path


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--cli':
        sys.argv.pop(1)
        log_handle=None
        # PyInstaller --windowed has no guaranteed stdout/stderr handles.
        # Our packaged Qt app streams a dedicated UTF-8 CLI log file instead.
        if '--cli-log' in sys.argv:
            position=sys.argv.index('--cli-log')
            if position+1>=len(sys.argv):raise SystemExit('Missing --cli-log path')
            log_path=Path(sys.argv[position+1])
            del sys.argv[position:position+2]
            log_handle=log_path.open('w',encoding='utf-8',buffering=1)
            sys.stdout=sys.stderr=log_handle
        import vlog_maker
        try:vlog_maker.main()
        except Exception as exc:
            if sys.stderr is not None:print('ERROR:',exc,file=sys.stderr,flush=True)
            raise SystemExit(1)
        finally:
            if log_handle is not None:log_handle.flush();log_handle.close()
    elif len(sys.argv)>1 and sys.argv[1]=='--legacy-gui':
        sys.argv.pop(1)
        import tkinter as tk
        from vlog_gui import Application
        root=tk.Tk();Application(root);root.mainloop()
    else:
        try:
            from vlog_qt import main as qt_main
        except ImportError as exc:
            if exc.name and (exc.name=='PySide6' or exc.name.startswith('PySide6.')):
                print('缺少 PySide6。請在 Windows 執行 setup_windows.bat，或安裝 requirements-windows.txt。',file=sys.stderr)
            raise
        return qt_main()

if __name__=='__main__':raise SystemExit(main())
