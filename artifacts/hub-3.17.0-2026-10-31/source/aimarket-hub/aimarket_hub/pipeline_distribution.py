"""Optional public wheel distribution for agents without a source checkout."""
import json
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent / 'static' / 'client'


def metadata():
    try:
        data = json.loads((ROOT / 'release.json').read_text())
        if not re.fullmatch(r'aimarket_hub-[0-9.]+-py3-none-any\.whl', data['filename']):
            return None
        if not re.fullmatch(r'[0-9a-f]{64}', data['sha256']):
            return None
        return data if (ROOT / data['filename']).is_file() else None
    except (OSError, ValueError, KeyError):
        return None


def attach_routes(app):
    @app.get('/clients/pipeline-guide/{language}')
    def client_guide(language: str):
        if language not in {'en', 'ru', 'es', 'fr', 'zh'} or not (ROOT / (language + '.md')).is_file():
            raise HTTPException(404, 'unknown guide')
        return FileResponse(ROOT / (language + '.md'), media_type='text/plain; charset=utf-8')

    @app.get('/clients/pipeline.json')
    def client_release():
        release = metadata()
        if not release:
            raise HTTPException(503, 'client distribution not installed on this hub')
        return release

    @app.get('/clients/{filename}')
    def client_wheel(filename: str):
        if not re.fullmatch(r'aimarket_hub-[0-9.]+-py3-none-any\.whl', filename) or not (ROOT / filename).is_file():
            raise HTTPException(404, 'unknown client distribution')
        return FileResponse(ROOT / filename, media_type='application/zip', filename=filename,
                            headers={'Cache-Control': 'public, max-age=31536000, immutable'})
