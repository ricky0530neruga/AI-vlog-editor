"""One executable: GUI by default; --cli uses the Python editing engine."""
import sys
if len(sys.argv)>1 and sys.argv[1]=='--cli':
    sys.argv.pop(1)
    import vlog_maker
    try:
        vlog_maker.main()
    except Exception as exc:
        print('ERROR:',exc,file=sys.stderr)
        sys.exit(1)
else:
    import tkinter as tk
    from vlog_gui import Application
    window=tk.Tk()
    Application(window)
    window.mainloop()
