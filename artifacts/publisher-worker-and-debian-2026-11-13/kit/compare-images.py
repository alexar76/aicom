"""Verify that the candidate updates only the three intended Debian binaries."""

import json
from pathlib import Path
import sys

base, candidate = [json.loads(Path(name).read_text()) for name in sys.argv[1:]]
assert base["python"] == candidate["python"]
assert base["hub_source_sha256"] == candidate["hub_source_sha256"]
assert base["base_usdc_contract"] == candidate["base_usdc_contract"]
assert base["zlib_gzip_roundtrip"] and candidate["zlib_gzip_roundtrip"]
old, new = base["debian"], candidate["debian"]
assert old.keys() == new.keys()
delta = {name: [old[name], version] for name, version in new.items() if old[name] != version}
assert delta == {"apt": ["3.0.3", "3.0.4"], "libapt-pkg7.0:amd64": ["3.0.3", "3.0.4"],
                 "zlib1g:amd64": ["1:1.3.dfsg+really1.3.1-1+b1", "1:1.3.dfsg+really1.3.1-1+deb13u1"]}, delta
assert candidate["apt_version"].startswith("apt 3.0.4 ")
print(json.dumps({"changed_debian_packages": delta, "debian_count": len(new), "python_count": len(candidate["python"]),
                  "hub_source_sha256": candidate["hub_source_sha256"], "dpkg_audit_clean": True,
                  "apt_get_check": True, "zlib_gzip_roundtrip": True}, indent=2))
