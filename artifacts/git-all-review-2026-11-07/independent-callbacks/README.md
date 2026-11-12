# Independent callback verification

Both selected callback suites passed on Attested and Blip in separate gVisor containers. These are synthetic DNS/HTTP tests: no production credentials, production database, mounted application state or live callback destination was used.

| Host | Project | Passed | Failed / errors / skipped | Pytest time |
| --- | --- | --- | --- | --- |
| Attested | Kova gateway | 19 | 0 / 0 / 0 | 0.751 s |
| Attested | Verified execution hub | 19 | 0 / 0 / 0 | 0.704 s |
| Blip | Kova gateway | 19 | 0 / 0 / 0 | 1.178 s |
| Blip | Verified execution hub | 19 | 0 / 0 / 0 | 1.322 s |

The selected files are `independent/kova-gateway/backend/tests/test_callback_http.py` and `independent/verified-execution-hub/backend/tests/test_callback_http.py`. Each suite checks signed callback bytes, checked-IP pinning with the original TLS identity, private and mixed DNS rejection, authority restrictions before DNS, compressed reply limits, redirect refusal, total response deadlines and retained resolver concurrency slots.

The immutable V4 input was the tree `1400f9f8e6f0b104298835b1f9bcfd35f4a75aa3`, whose parent-verified 10,101-blob SHA map has SHA256 `7085e9f236ccd276b89a3f864421751fb468f9da18b17b05376ffccb40068f16`. V4 omitted the two project-root pytest configurations. The first Kova attempt therefore failed before collection on both hosts; the original failure log and container receipts remain as `kova-initial-missing-config*`.

The exact two original `pyproject.toml` files were then transferred as the narrow `config/` supplement. A network-disabled gVisor preparation container copied the two project source subtrees to a private working copy and added their configurations at their original relative paths. Tests used the actual configurations there, including each project's `pythonpath` policy. V4 itself was not modified. All 53 backend Python files were checked against the original snapshot before testing; their complete SHA256 map remained identical afterward and on both hosts. The copied configurations were byte-compared before and after testing.

| Identity | SHA256 |
| --- | --- |
| Kova callback test | `b2b43e8fd23060aec96ec7597f7307bb14a329eedb7c1a9f86317c26a4e94560` |
| Verified hub callback test | `6c97774bc4da6bae667704bc85faf5af468ac366bda2bd21068f17bab2f8b858` |
| All 53 Python source hashes, before and after | `1d4ad0510224ae8a465598e5b167c7c4c5c781fb315f008bca29b168a355cdeb` |
| Kova project configuration | `58db1215951f47f601069b27ebc67a282170a24b874ad5adcc08095cab3678c9` |
| Verified hub project configuration | `52c7661d54d85b1fde390dec7b465276cb66b54475bfec1554e349b2f17d0c55` |
| Configuration SHA256 map | `57dea16c00a38d6aaff0aa571a37b65b9d1a15dc48fdeb16d00c2391c870ba0c` |
| Remote runner | `e6362579f331c063aaffe6e0ccda010ebf5e1c414a8ad2f7f32770618edb626a` |

The interpreter image was official Python 3.13.18, image ID `sha256:76baad6037690d6e8c4397fbcaef17bca6f19eecef822b708fe8fa3417d30bb5`. Each project had its own pinned-requirements dependency target, installed in a separate public-PyPI setup container using the gVisor runtime and bridge networking. Dependency reports and complete installed-file hash maps are retained per host. No active Hub dependency environment was modified.

Every pytest container used `runsc`, `network=none`, UID/GID `1000:1000`, a read-only root filesystem, read-only execution source and dependencies, dropped capabilities, and `no-new-privileges`. Work, temporary files, fixture signer keys and any synthetic data used container-local tmpfs. Only the dedicated result directory was a writable persistent mount. The pytest cache was disabled and Python bytecode writes were disabled. Kova emitted one upstream Starlette/httpx deprecation warning on each host; the suites had no failures, errors or skips.

All five final containers per host were removed; the earlier failed pre-collection container was removed before the corrected run. Both `remaining-containers.txt` files are empty. Removing the containers discarded their temporary state and generated fixture signer keys. Private inert source copies, public dependency targets and safe receipts remain under `/opt/aicom-verify/20261108-all-tree/independent-callbacks` for reproduction. No local project interpreter, build, package installation, test or server was run; only source/configuration edits, native file/hash operations and remote transport were performed locally.
