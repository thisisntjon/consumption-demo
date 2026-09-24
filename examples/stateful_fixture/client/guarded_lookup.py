"""Run the unchanged shared lookup with the replay guard already installed."""
import json
from pathlib import Path
import socket
import sys
import sitecustomize

if not sitecustomize.ACTIVE:
    raise SystemExit("replay guard is required")

root = Path(sys.argv[1]).resolve()
if sys.argv[2] == "probe":
    checks = {}
    for label, operation in {
        "outside_read_denied": lambda: Path(sys.argv[3]).read_bytes(),
        "socket_denied": lambda: socket.socket(),
    }.items():
        try:
            operation()
            checks[label] = False
        except PermissionError:
            checks[label] = True
    print(json.dumps(checks))
    raise SystemExit(0 if all(checks.values()) else 1)

sys.path.insert(0, str(root / "runtime" / "engine"))
from consumption_engine.__main__ import main

raise SystemExit(main(sys.argv[2:]))
