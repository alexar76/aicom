#!/usr/bin/env python3
"""Publish the versioned factory guide with the frontend, independent of GitHub pushes."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
DEST = ROOT / 'web/frontend/public/factory/docs'
DEST.mkdir(parents=True, exist_ok=True)
for language in ['', '.ru', '.es', '.fr', '.zh']:
    name = f'factory-subcontracting{language}.md'
    source = (ROOT / 'docs' / name).read_text()
    # Keep downloaded documentation links rooted at the canonical source repository.
    def absolute(match):
        label, href = match.groups()
        if href.startswith(('https://', 'http://', '#')):
            return match.group(0)
        resolved = (ROOT / 'docs' / href).resolve().relative_to(ROOT)
        return f'[{label}](https://github.com/alexar76/aicom/blob/main/{resolved.as_posix()})'
    (DEST / name).write_text(re.sub(r'\[([^\]]+)\]\(([^)]+)\)', absolute, source))
print('Published 5 factory guides.')
