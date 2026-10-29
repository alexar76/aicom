"""Launch one verified local Oracle wheel without network or child-process access."""

import argparse
import runpy
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--package-root", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.package_root.resolve()))


def guard(event, _args):
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.gethostbyname",
                 "socket.gethostbyname_ex", "subprocess.Popen", "os.system", "os.posix_spawn"}:
        raise PermissionError("startup-only replay denies " + event)


sys.addaudithook(guard)
runpy.run_module("aimarket_oracle_gateway.stdio_server", run_name="__main__", alter_sys=True)
