"""Run one known local module with Python network/subprocess audit guards.

This is a Python audit guard, not an OS network namespace or container sandbox.
The capture client sends discovery/initialize/tools/list only; no tools/call.
"""

import argparse
import runpy
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--module", required=True, choices=(
    "aimarket_oracle_gateway.stdio_server", "aimarket_mcp_packager.stdio_server"))
parser.add_argument("--overlay", type=Path)
args = parser.parse_args()
if args.overlay:
    sys.path.insert(0, str(args.overlay.resolve()))


def guard(event, _args):
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.gethostbyname",
                 "socket.gethostbyname_ex", "subprocess.Popen", "os.system", "os.posix_spawn"}:
        raise PermissionError("list-only capture denies " + event)


sys.addaudithook(guard)
runpy.run_module(args.module, run_name="__main__", alter_sys=True)
