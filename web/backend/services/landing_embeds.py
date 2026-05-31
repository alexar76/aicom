"""
Optional embeds on generated static HTML:

- ``agent_to_website`` — demo chat widget (ported from aicom-landing ``agentToWebsite.mjs``)
- ``aimarket_widget`` — hub search/invoke panel for full products
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from core.delivery_profile import DESKTOP_APP, FULL_SOFTWARE, MARKETING_LANDING, normalize_delivery_profile
from core.public_site_url import resolve_public_site_url

logger = logging.getLogger(__name__)

AIMARKET_MARKER = "aifactory-aimarket-widget"

_BODY_CLOSE = re.compile(r"</body>", re.IGNORECASE)


def _insert_before_body(content: str, block: str, *, fallback_sep: str = "") -> str:
    """Insert ``block`` right before ``</body>`` (or append if absent).

    Uses string slicing rather than ``re.sub`` because ``block`` may contain
    backslash sequences (e.g. ``\\u003c``) that ``re.sub`` would mis-handle as
    replacement escapes (``re.error: bad escape``).
    """
    match = _BODY_CLOSE.search(content)
    if not match:
        return content + fallback_sep + block if fallback_sep else content + block
    idx = match.start()
    return f"{content[:idx]}{block}\n{content[idx:]}"


def _js_embed(value: Any) -> str:
    """JSON-encode for safe embedding inside an inline <script> block.

    ``json.dumps`` alone does not escape ``<``, ``>``, ``&`` or the JS line
    separators U+2028/U+2029, so a value containing ``</script>`` (or ``<!--``)
    would break out of the script element. Escaping these as ``\\uXXXX`` keeps
    the payload a valid JS string while preventing HTML/JS context breakout.
    """
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )

_HAS_AGENT_WIDGET = re.compile(
    r'id=["\']aicom-agent["\']|class=["\'][^"\']*aicom-agent\b',
    re.IGNORECASE,
)

_RISKY_AGENT_PATTERNS = [
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bnew\s+Function\s*\(", re.IGNORECASE),
    re.compile(r"\bfetch\s*\(\s*['\"]https?:", re.IGNORECASE),
    re.compile(r"\bXMLHttpRequest\b", re.IGNORECASE),
    re.compile(r"\bnavigator\.sendBeacon\s*\(", re.IGNORECASE),
    re.compile(r"\bdocument\.cookie\b", re.IGNORECASE),
    re.compile(r"\blocalStorage\s*\.\s*setItem", re.IGNORECASE),
    re.compile(r"\bsessionStorage\s*\.\s*setItem", re.IGNORECASE),
    re.compile(r"\bwindow\.open\s*\(", re.IGNORECASE),
    re.compile(r'<script[^>]+src\s*=\s*[\'"]https?:', re.IGNORECASE),
]

_AGENT_DIV_START = re.compile(r'<div[^>]*\bid=["\']aicom-agent["\']', re.IGNORECASE)
_DIV_TAG = re.compile(r"<\s*(/?)div\b", re.IGNORECASE)


def has_agent_widget(content: str) -> bool:
    return bool(_HAS_AGENT_WIDGET.search(content))


def has_risky_agent_patterns(content: str) -> bool:
    if not has_agent_widget(content):
        return False
    return any(p.search(content) for p in _RISKY_AGENT_PATTERNS)


def strip_agent_widget(content: str) -> str:
    """Remove the whole ``#aicom-agent`` widget subtree.

    The widget contains nested ``<div>`` elements (and inline ``<style>`` /
    ``<script>``), so we walk ``<div>``/``</div>`` tags counting nesting depth
    and cut at the matching close — a non-greedy ``...</div>`` regex would stop
    at the first inner close and leave risky markup behind.
    """
    match = _AGENT_DIV_START.search(content)
    if not match:
        return content
    start = match.start()
    depth = 0
    end: int | None = None
    for m in _DIV_TAG.finditer(content, start):
        if m.group(1):  # closing </div>
            depth -= 1
            if depth <= 0:
                close = content.find(">", m.end())
                end = (close + 1) if close != -1 else m.end()
                break
        else:  # opening <div>
            depth += 1
    if end is None:
        return content  # malformed/unbalanced — leave intact rather than corrupt
    return content[:start] + content[end:]


def _widget_copy(locale: str) -> dict[str, str]:
    code = (locale or "en").split("-")[0].split("_")[0]
    if code == "ru":
        return {
            "fab": "Спросить AI-агента",
            "title": "AI-ассистент",
            "subtitle": "Ответы по этому продукту",
            "placeholder": "Опишите задачу или задайте вопрос…",
            "send": "Отправить",
            "close": "Закрыть",
            "typing": "Печатает…",
            "opener": (
                "Привет! Я AI-агент на этом лендинге. Расскажу про предложение, "
                "помогу с выбором тарифа или следующим шагом."
            ),
            "fallback": (
                "Спасибо за вопрос. Я демо-агент на лендинге: опишите задачу подробнее, "
                "или нажмите «Связаться» / CTA на странице — команда ответит быстрее."
            ),
        }
    if code == "es":
        return {
            "fab": "Preguntar al agente IA",
            "title": "Asistente IA",
            "subtitle": "Respuestas sobre este producto",
            "placeholder": "Describe tu tarea o pregunta…",
            "send": "Enviar",
            "close": "Cerrar",
            "typing": "Escribiendo…",
            "opener": (
                "¡Hola! Soy el agente IA de esta landing. Te explico la propuesta, "
                "precios y el siguiente paso."
            ),
            "fallback": (
                "Gracias por tu mensaje. Soy un agente demo en la página: cuéntame más, "
                "o usa el CTA principal para hablar con el equipo."
            ),
        }
    return {
        "fab": "Ask AI agent",
        "title": "AI assistant",
        "subtitle": "Answers about this offer",
        "placeholder": "Describe your task or ask a question…",
        "send": "Send",
        "close": "Close",
        "typing": "Typing…",
        "opener": (
            "Hi! I'm the embedded AI agent on this landing. "
            "I can explain the offer, pricing, and what to do next."
        ),
        "fallback": (
            "Thanks for your message. I'm a demo agent on this page — add a bit more detail, "
            "or use the main CTA to reach the team."
        ),
    }


def build_agent_markup(*, user_prompt: str, locale: str) -> str:
    """Audited demo chat block — browser-side keyword replies only."""
    c = _widget_copy(locale)
    brief = _js_embed((user_prompt or "")[:500])
    loc = _js_embed(locale or "en")
    copy_json = _js_embed(c)
    esc = html.escape

    return f"""<div id="aicom-agent" class="aicom-agent" data-aicom-agent="1">
<style>
.aicom-agent{{--aicom-fab:var(--accent,#6366f1);--aicom-fab2:var(--accent2,#a855f7);font-family:var(--font-body,system-ui,sans-serif);position:fixed;bottom:1.25rem;right:1.25rem;z-index:99990}}
.aicom-agent-fab{{display:flex;align-items:center;gap:.5rem;padding:.65rem 1rem;border:none;border-radius:999px;color:#fff;font-weight:600;font-size:.85rem;cursor:pointer;background:linear-gradient(135deg,var(--aicom-fab),var(--aicom-fab2));box-shadow:0 12px 32px rgba(0,0,0,.35);transition:transform .2s ease}}
.aicom-agent-fab:hover{{transform:translateY(-2px)}}
.aicom-agent-fab svg{{width:1.1rem;height:1.1rem;flex-shrink:0}}
.aicom-agent-panel{{position:absolute;bottom:calc(100% + .75rem);right:0;width:min(380px,calc(100vw - 2rem));max-height:min(520px,70vh);display:flex;flex-direction:column;border-radius:1rem;overflow:hidden;background:rgba(12,12,20,.92);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.12);box-shadow:0 24px 64px rgba(0,0,0,.45);opacity:0;visibility:hidden;transform:translateY(8px) scale(.98);transition:opacity .22s ease,transform .22s ease,visibility .22s}}
.aicom-agent.is-open .aicom-agent-panel{{opacity:1;visibility:visible;transform:translateY(0) scale(1)}}
.aicom-agent-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:.5rem;padding:.85rem 1rem;border-bottom:1px solid rgba(255,255,255,.08)}}
.aicom-agent-head h2{{margin:0;font-size:.95rem;color:#f8fafc}}
.aicom-agent-head p{{margin:.2rem 0 0;font-size:.72rem;color:#94a3b8}}
.aicom-agent-close{{background:transparent;border:none;color:#94a3b8;cursor:pointer;font-size:1.1rem;line-height:1;padding:.2rem}}
.aicom-agent-msgs{{flex:1;overflow-y:auto;padding:.75rem 1rem;display:flex;flex-direction:column;gap:.6rem;min-height:180px}}
.aicom-agent-msg{{max-width:92%;padding:.55rem .75rem;border-radius:.75rem;font-size:.82rem;line-height:1.45}}
.aicom-agent-msg--bot{{align-self:flex-start;background:rgba(255,255,255,.08);color:#e2e8f0}}
.aicom-agent-msg--user{{align-self:flex-end;background:linear-gradient(135deg,var(--aicom-fab),var(--aicom-fab2));color:#fff}}
.aicom-agent-form{{display:flex;gap:.5rem;padding:.75rem;border-top:1px solid rgba(255,255,255,.08)}}
.aicom-agent-form input{{flex:1;border:1px solid rgba(255,255,255,.15);background:rgba(0,0,0,.25);color:#f1f5f9;border-radius:.5rem;padding:.55rem .65rem;font-size:.82rem}}
.aicom-agent-form button{{border:none;border-radius:.5rem;padding:.55rem .85rem;font-weight:600;font-size:.78rem;cursor:pointer;color:#fff;background:var(--aicom-fab)}}
@media(max-width:480px){{.aicom-agent{{right:.75rem;bottom:.75rem}}.aicom-agent-fab span{{display:none}}}}
</style>
<button type="button" class="aicom-agent-fab" aria-expanded="false" aria-controls="aicom-agent-panel">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/><path d="M5 19h14"/></svg>
<span>{esc(c["fab"])}</span>
</button>
<div id="aicom-agent-panel" class="aicom-agent-panel" role="dialog" aria-label="{esc(c["title"])}" hidden>
<div class="aicom-agent-head"><div><h2>{esc(c["title"])}</h2><p>{esc(c["subtitle"])}</p></div><button type="button" class="aicom-agent-close" aria-label="{esc(c["close"])}">×</button></div>
<div class="aicom-agent-msgs" id="aicom-agent-msgs"></div>
<form class="aicom-agent-form" id="aicom-agent-form"><input type="text" id="aicom-agent-input" placeholder="{esc(c["placeholder"])}" autocomplete="off" maxlength="500" required /><button type="submit">{esc(c["send"])}</button></form>
</div>
<script>
(function(){{
var root=document.getElementById("aicom-agent");
if(!root||root.dataset.aicomInit)return;
root.dataset.aicomInit="1";
var brief={brief};
var loc={loc};
var copy={copy_json};
var fab=root.querySelector(".aicom-agent-fab");
var panel=root.querySelector(".aicom-agent-panel");
var msgs=root.querySelector("#aicom-agent-msgs");
var form=root.querySelector("#aicom-agent-form");
var input=root.querySelector("#aicom-agent-input");
function addMsg(text,who){{var d=document.createElement("div");d.className="aicom-agent-msg aicom-agent-msg--"+who;d.textContent=text;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;}}
function replyFor(t){{
  var s=(t||"").toLowerCase();
  if(/price|pricing|plan|тариф|цена|precio/.test(s))return loc.startsWith("ru")?"Тарифы выше на странице — напишите приоритет (объём, скорость, поддержка).":loc.startsWith("es")?"Los planes están arriba — ¿volumen, velocidad o soporte?":"See pricing above — tell me volume, speed, or support priority.";
  if(/demo|trial|start|начать|prueba/.test(s))return loc.startsWith("ru")?"Следующий шаг — основная CTA на странице.":loc.startsWith("es")?"Siguiente paso: el CTA principal.":"Next step: use the main CTA on this page.";
  if(/how|what|как|что|qué/.test(s))return (loc.startsWith("ru")?"Кратко: ":"In short: ")+(brief||"this offer")+(loc.startsWith("ru")?". Уточните задачу.":". Add your goal.");
  return copy.fallback;
}}
function setOpen(on){{root.classList.toggle("is-open",on);panel.hidden=!on;fab.setAttribute("aria-expanded",on?"true":"false");if(on)setTimeout(function(){{input.focus();}},120);}}
fab.addEventListener("click",function(){{setOpen(!root.classList.contains("is-open"));}});
root.querySelector(".aicom-agent-close").addEventListener("click",function(){{setOpen(false);}});
addMsg(copy.opener,"bot");
form.addEventListener("submit",function(e){{e.preventDefault();var t=input.value.trim();if(!t)return;addMsg(t,"user");input.value="";addMsg(copy.typing,"bot");setTimeout(function(){{msgs.lastChild&&msgs.lastChild.remove();addMsg(replyFor(t),"bot");}},520+Math.random()*400);}});
}})();
</script>
</div>"""


def ensure_agent_widget(
    content: str,
    *,
    enabled: bool,
    user_prompt: str = "",
    locale: str = "en",
) -> str:
    if not enabled:
        return content

    strict = os.environ.get("AICOM_LANDING_AGENT_STRICT", "").strip().lower() not in (
        "false",
        "0",
    )

    if has_agent_widget(content):
        if strict and has_risky_agent_patterns(content):
            logger.warning("agent widget: unsafe patterns in model HTML — replacing with audited fallback")
            content = strip_agent_widget(content)
        else:
            return content

    if os.environ.get("AICOM_LANDING_SKIP_AGENT_INJECT", "").strip().lower() == "true":
        logger.warning("agent_to_website requested but AICOM_LANDING_SKIP_AGENT_INJECT=true")
        return content

    block = build_agent_markup(user_prompt=user_prompt, locale=locale)
    return _insert_before_body(content, block)


def resolve_aimarket_hub_url() -> str:
    for key in ("AIMARKET_HUB_URL", "AIMARKET_FEDERATION_HUB_URL", "NEXT_PUBLIC_AIMARKET_HUB_URL"):
        val = (os.environ.get(key) or "").strip().rstrip("/")
        if val.startswith(("http://", "https://")):
            return val
    return "https://modelmarket.dev"


def build_aimarket_widget_snippet(
    *,
    product_id: str,
    intent: str,
    hub_url: str | None = None,
    script_src: str | None = None,
) -> str:
    hub = (hub_url or resolve_aimarket_hub_url()).rstrip("/")
    src = (script_src or f"{resolve_public_site_url()}/aimarket.js").rstrip("/")
    if not src.endswith("aimarket.js"):
        src = f"{src.rstrip('/')}/aimarket.js"
    intent_attr = html.escape((intent or "")[:240], quote=True)
    hub_attr = html.escape(hub, quote=True)
    src_attr = html.escape(src, quote=True)
    pid_attr = html.escape(product_id, quote=True)
    return (
        f"<!-- {AIMARKET_MARKER} -->\n"
        f'<script src="{src_attr}" async '
        f'data-theme="auto" data-intent="{intent_attr}" '
        f'data-budget="3.00" data-hub-url="{hub_attr}" '
        f'data-affiliate-id="{pid_attr}"></script>'
    )


def ensure_aimarket_widget(
    content: str,
    *,
    enabled: bool,
    product_id: str,
    intent: str,
) -> str:
    if not enabled:
        return content
    if AIMARKET_MARKER in content or 'src="' in content and "aimarket.js" in content:
        return content
    snippet = build_aimarket_widget_snippet(product_id=product_id, intent=intent)
    return _insert_before_body(content, snippet, fallback_sep="\n")


def _product_locale(product: dict[str, Any]) -> str:
    for key in ("content_locale", "interface_locale", "locale"):
        val = str(product.get(key) or "").strip()
        if val and val.lower() != "auto":
            return val
    return "en"


def _product_user_prompt(product: dict[str, Any]) -> str:
    parts = [str(product.get("idea") or "").strip()]
    admin = str(product.get("admin_instructions") or "").strip()
    if admin:
        parts.append(admin[:800])
    return "\n".join(p for p in parts if p)


def apply_embeds_to_html(content: str, product: dict[str, Any]) -> str:
    profile = normalize_delivery_profile(str(product.get("delivery_profile") or ""))
    pid = str(product.get("id") or "")
    locale = _product_locale(product)
    prompt = _product_user_prompt(product)

    if product.get("agent_to_website") and profile == MARKETING_LANDING:
        content = ensure_agent_widget(
            content,
            enabled=True,
            user_prompt=prompt,
            locale=locale,
        )

    if product.get("aimarket_widget") and profile in (FULL_SOFTWARE, DESKTOP_APP):
        content = ensure_aimarket_widget(
            content,
            enabled=True,
            product_id=pid,
            intent=str(product.get("idea") or "")[:240],
        )

    return content


def inject_landing_embeds_for_product(data_root: Path, product_id: str, product: dict[str, Any]) -> None:
    """Walk generated HTML and apply optional embeds (idempotent where possible)."""
    if not product.get("agent_to_website") and not product.get("aimarket_widget"):
        return

    code_dir = data_root / "code" / product_id
    if not code_dir.is_dir():
        return

    for html_file in code_dir.rglob("*.html"):
        try:
            original = html_file.read_text(encoding="utf-8")
        except OSError:
            continue
        updated = apply_embeds_to_html(original, product)
        if updated != original:
            try:
                html_file.write_text(updated, encoding="utf-8")
            except OSError:
                continue
