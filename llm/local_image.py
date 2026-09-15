"""
CPU-local text-to-image via Hugging Face diffusers.

Optional deps (heavy — install only when needed):
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  pip install -r requirements-local-image.txt

Env:
  AICOM_LOCAL_IMAGE_MODEL   default stabilityai/sd-turbo (~2GB, 4 steps, much sharper)
  AICOM_LOCAL_IMAGE_STEPS   inference steps (default 4 for sd-turbo, 20 for sd1.5)
  AICOM_LOCAL_IMAGE_GUIDANCE  CFG scale (default 0 for sd-turbo, 7.5 otherwise)
  AICOM_LOCAL_IMAGE_DEVICE  default cpu
  HF_HOME                   default data/.cache/huggingface (gitignored; fetched on first run)
"""

from __future__ import annotations

import io
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_pipeline: Any = None
_pipeline_lock = threading.Lock()

DEFAULT_NEGATIVE = (
    "blurry, ugly, deformed, disfigured, low quality, worst quality, jpeg artifacts, "
    "text, letters, words, watermark, signature, logo, caption, duplicate, cropped, "
    "out of frame, extra limbs, bad anatomy, muddy, noisy, flat lighting"
)


def local_image_model_id() -> str:
    return (
        os.environ.get("AICOM_LOCAL_IMAGE_MODEL", "stabilityai/sd-turbo").strip()
        or "stabilityai/sd-turbo"
    )


def _is_turbo_model(model_id: str) -> bool:
    low = model_id.lower()
    return "turbo" in low or "lcm" in low


def default_inference_steps(model_id: str | None = None) -> int:
    mid = model_id or local_image_model_id()
    default = "4" if _is_turbo_model(mid) else "20"
    raw = os.environ.get("AICOM_LOCAL_IMAGE_STEPS", default).strip()
    try:
        return max(1, min(40, int(raw)))
    except ValueError:
        return int(default)


def default_guidance_scale(model_id: str | None = None) -> float:
    mid = model_id or local_image_model_id()
    default = "0" if _is_turbo_model(mid) else "7.5"
    raw = os.environ.get("AICOM_LOCAL_IMAGE_GUIDANCE", default).strip()
    try:
        return max(0.0, min(20.0, float(raw)))
    except ValueError:
        return float(default)


def _device() -> str:
    return os.environ.get("AICOM_LOCAL_IMAGE_DEVICE", "cpu").strip() or "cpu"


def _load_pipeline():
    global _pipeline
    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        try:
            import torch
            from diffusers import AutoPipelineForText2Image
        except ImportError as exc:
            raise RuntimeError(
                "Local image generation requires optional deps: "
                "pip install torch --index-url https://download.pytorch.org/whl/cpu "
                "&& pip install -r requirements-local-image.txt"
            ) from exc

        model_id = local_image_model_id()
        logger.info("Loading local image model %s on %s (first run may download weights)", model_id, _device())
        pipe = AutoPipelineForText2Image.from_pretrained(
            model_id,
            torch_dtype=torch.float32,
            safety_checker=None,
        )
        pipe = pipe.to(_device())
        if _device() == "cpu":
            pipe.enable_attention_slicing()
        _pipeline = pipe
        logger.info("Local image pipeline ready: %s", model_id)
        return _pipeline


def generate_local_image(
    prompt: str,
    *,
    width: int = 512,
    height: int = 512,
    num_inference_steps: int | None = None,
    guidance_scale: float | None = None,
    negative_prompt: str | None = None,
    seed: int | None = None,
) -> bytes:
    """Render one PNG from a text prompt on CPU (typically 1–5 minutes at 512²–768²)."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    width = max(256, min(768, int(width)))
    height = max(256, min(768, int(height)))
    model_id = local_image_model_id()
    steps = num_inference_steps if num_inference_steps is not None else default_inference_steps(model_id)
    cfg = guidance_scale if guidance_scale is not None else default_guidance_scale(model_id)
    neg = negative_prompt if negative_prompt is not None else DEFAULT_NEGATIVE
    if _is_turbo_model(model_id):
        neg = None  # turbo distillation — negative prompt often hurts

    pipe = _load_pipeline()
    import torch

    generator = None
    if seed is not None:
        generator = torch.Generator(device=_device()).manual_seed(int(seed) & 0xFFFFFFFF)

    logger.info(
        "local_image generate %dx%d steps=%d cfg=%.1f model=%s prompt_chars=%d",
        width,
        height,
        steps,
        cfg,
        model_id,
        len(prompt),
    )
    kwargs: dict[str, Any] = {
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "guidance_scale": cfg,
        "generator": generator,
    }
    if neg:
        kwargs["negative_prompt"] = neg
    result = pipe(prompt, **kwargs)
    image = result.images[0]
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
