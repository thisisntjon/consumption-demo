"""Bounded Python replay guard. Not a hostile-code or OS security boundary."""
import atexit
import json
import os
from pathlib import Path
import sys
import ctypes

ACTIVE = False
if os.environ.get("CE_DEMO_ROOT"):
    try:
        ROOT = Path(os.environ["CE_DEMO_ROOT"]).resolve(strict=True)
        RUNTIME = Path(sys.base_prefix).resolve(strict=True)
        LOG = ROOT / "guard-logs" / (str(os.getpid()) + ".json")
        reads, denied = set(), []

        def inside(path, root):
            return path == root or root in path.parents

        def audit(event, args):
            if event == "open" and not isinstance(args[0], int):
                path = Path(os.fsdecode(args[0])).resolve()
                flags = args[2]
                writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                allowed = inside(path, ROOT) or (
                    not writing and inside(path, RUNTIME)
                    and "site-packages" not in {p.lower() for p in path.parts})
                if not allowed:
                    denied.append({"event": event, "path": str(path)})
                    raise PermissionError("demo replay denied outside read/write")
                if not writing:
                    reads.add(str(path))
            elif event.startswith("socket.") or event in {"os.system", "os.exec", "os.spawn"}:
                denied.append({"event": event})
                raise PermissionError("demo replay denied network/process operation")
            elif event == "subprocess.Popen":
                executable_name = args[0]
                if executable_name is None:
                    # Windows reports a command-line string when Popen inferred
                    # the executable. Parse it with Windows' own argv parser.
                    command = args[1]
                    if isinstance(command, str):
                        count = ctypes.c_int()
                        parse = ctypes.windll.shell32.CommandLineToArgvW
                        parse.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
                        parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
                        argv = parse(command, ctypes.byref(count))
                        if not argv or count.value < 1:
                            raise PermissionError("cannot identify replay executable")
                        try:
                            executable_name = argv[0]
                        finally:
                            ctypes.windll.kernel32.LocalFree(ctypes.cast(argv, ctypes.c_void_p))
                    else:
                        executable_name = command[0]
                executable = Path(executable_name).resolve()
                if executable != Path(sys.executable).resolve():
                    denied.append({"event": event})
                    raise PermissionError("demo replay allows only the declared Python interpreter")

        def finish():
            LOG.write_text(json.dumps({"active": True, "pid": os.getpid(),
                "python": sys.executable, "root": str(ROOT), "reads": sorted(reads),
                "denied": denied}, indent=2), encoding="utf-8")

        sys.addaudithook(audit)
        atexit.register(finish)
        ACTIVE = True
    except BaseException:
        # Python normally suppresses sitecustomize import errors. Fail closed here.
        os._exit(81)
