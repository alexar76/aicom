"""Build local security release wheels from audited workspace sources, offline."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'release-wheels'
OUT.mkdir(exist_ok=True)
PROJECTS = ['aimarket-mcp', 'metis', 'treasury', 'platon/backend', 'oracles/core', 'logos', 'atlas', 'skopos']

def build(project):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('UV_', 'PIP_'))}
    command = ['uv', 'build', '--offline', '--wheel', '--no-create-gitignore', '--out-dir', str(OUT), str(ROOT/project)]
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    log = project.replace('/', '-') + '-wheel-build.log'
    (HERE/log).write_text(completed.stdout + completed.stderr)
    return {'project': project, 'exit_code': completed.returncode, 'log': log}

with ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(build, PROJECTS))
(HERE/'local-build-results.json').write_text(json.dumps(results, indent=2)+'\n')
for result in results:
    print(json.dumps(result))
raise SystemExit(any(result['exit_code'] for result in results))
