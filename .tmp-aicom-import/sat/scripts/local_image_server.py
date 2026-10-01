#!/usr/bin/env python3
"""
Minimal OpenAI-compatible image API for CPU-local diffusers generation.

  python scripts/local_image_server.py
  curl -X POST http://127.0.0.1:8766/v1/images/generations \\
    -H 'content-type: application/json' \\
    -d '{"prompt":"ancient greek mosaic of twin stars, no text","size":"512x512"}'

Env:
  AICOM_LOCAL_IMAGE_PORT   default 8766
  AICOM_LOCAL_IMAGE_*      see llm/local_image.py
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import sys
from pathlib import Path

# Keep HF weights under repo data/ (gitignored) unless the operator overrides HF_HOME.
_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME", str(_ROOT / "data" / ".cache" / "huggingface"))
os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(os.environ["HF_HOME"], "hub"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm.local_image import generate_local_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("local_image_server")

app = FastAPI(title="AICOM Local Image", version="1.0")


class ImageGenRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    size: str = "512x512"
    n: int = 1
    model: str | None = None


def parse_size(size: str) -> tuple[int, int]:
    m = re.match(r"^(\d{2,4})x(\d{2,4})$", (size or "").strip())
    if not m:
        return 512, 512
    return int(m.group(1)), int(m.group(2))


@app.get("/health")
async def health():
    return {"status": "ok", "provider": "local-cpu"}


@app.post("/v1/images/generations")
async def images_generations(body: ImageGenRequest):
    if body.n != 1:
        raise HTTPException(status_code=400, detail="only n=1 supported")
    width, height = parse_size(body.size)
    try:
        png = await asyncio.to_thread(
            generate_local_image,
            body.prompt,
            width=width,
            height=height,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("image generation failed")
        raise HTTPException(status_code=500, detail="generation failed") from exc
    return {"data": [{"b64_json": base64.b64encode(png).decode("ascii")}]}


def main() -> None:
    import uvicorn

    port = int(os.environ.get("AICOM_LOCAL_IMAGE_PORT", "8766"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
