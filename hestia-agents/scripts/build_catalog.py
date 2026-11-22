"""Build the public catalogue of HESTIA's agents: what each does, what it can reach, the code that runs.

    python3 scripts/build_catalog.py [out_dir]          # default: ../hestia/docs/agents

The hearth serves that directory at /agents/ (hestia/app_routes/discovery.py), and its public roster
(/v1/hearth) gives each agent's handler_sha256: the page's live.js compares the two when it loads.
tests/test_catalog.py fails when the committed copy is not what this script builds now.

Everything comes from this repository, so the page cannot drift from the code:
  - each agent's capability, price, input schema and network reach from hestia_agents/manifests.py
    (the same values a deploy sends to the hearth, which shows the hosts on its public roster);
  - its description in five languages from docs/AGENTS*.md;
  - the handler itself, copied to src/ with its SHA-256 (SHA256SUMS), so anyone can read the exact
    code and compare it with what they are told runs;
  - the tests that hold it, and the recorded data they replay, copied to tests/;
  - the sandbox and egress limits from ../hestia (hestia/sandbox.py, hestia/egress.py).
Writes index.html (English), index.<lang>.html, catalog.json, live.js, src/, tests/, docs/ and SHA256SUMS.
Nothing in it depends on when or from which commit it was built, so the same tree builds the same bytes.
"""
# ruff: noqa: E501 — the page's five-language strings and its CSS read best unbroken

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hestia_agents.manifests import AGENTS, handler_source, language  # noqa: E402

HESTIA = ROOT.parent / "hestia" / "hestia"
OUT = ROOT.parent / "hestia" / "docs" / "agents"
# Published next to the tests because the tests import them; nothing else from tests/ is.
SUPPORT = ("tests/conftest.py", "tests/replay.py")
# The recorded replies are registry and web documents as they came back; the published copies drop
# e-mail addresses and local build paths in them (npm keeps a publisher's and a maintainer's address
# and, for a package packed from a folder, that folder's path). The tests run on the unedited files.
# An address starts after a character that cannot be in one, or right after an escape such as \n in
# the JSON text; never on the escape's own letter: "\n@mcp.tool()" in a README is a decorator.
EMAIL = re.compile(rb"(?:(?<=\\[nrt])|(?<![A-Za-z0-9._%+\\-]))(?<!\\)"
                   rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
LOCAL_PATH = re.compile(rb"(?:file:)?/(?:Users|home)/[^\s\"\\]+")
LANGS = ["", ".ru", ".es", ".fr", ".zh"]
HEARTH = "https://hestia.modelmarket.dev"


def redacted(raw: bytes) -> tuple[bytes, dict[str, int]]:
    out, emails = EMAIL.subn(b"[e-mail removed]", raw)
    out, paths = LOCAL_PATH.subn(b"[local path removed]", out)
    return out, {k: v for k, v in (("emails", emails), ("local_paths", paths)) if v}


def _const(path: Path, name: str) -> str:
    match = re.search(rf"^{name}\s*=\s*(.+)$", path.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit(f"{name} not found in {path}")
    return match.group(1).split("#", 1)[0].strip()


def limits() -> dict:
    sandbox, egress = HESTIA / "sandbox.py", HESTIA / "egress.py"
    py = ROOT.parent / "hestia" / "scripts" / "fetch_python_wasi.py"
    qjs = ROOT.parent / "hestia" / "scripts" / "fetch_qjs_wasi.py"
    return {
        "timeout_s": float(_const(sandbox, "DEFAULT_TIMEOUT_S")),
        "memory_mb": int(_const(sandbox, "DEFAULT_MEMORY_MB")),
        "max_requests_per_call": int(_const(egress, "MAX_ROUNDS")),
        "max_response_kib": int(eval(_const(egress, "MAX_RESPONSE_BYTES"))) // 1024,  # noqa: S307 — "256 * 1024"
        "request_timeout_s": float(_const(egress, "REQUEST_TIMEOUT_S")),
        "max_declared_hosts": int(_const(egress, "MAX_HOSTS")),
        "requests_per_minute_per_agent": int(_const(egress, "DEFAULT_PER_MINUTE")),
        "requests_per_minute_per_named_host": int(_const(egress, "DEFAULT_TARGET_PER_MINUTE")),
        "python": "CPython " + _const(py, "VERSION").strip('"') + " for WASI",
        "javascript": "QuickJS-ng " + _const(qjs, "VERSION").strip('"') + " for WASI",
    }


def sections(lang: str) -> tuple[str, dict[str, str]]:
    text = (ROOT / "docs" / f"AGENTS{lang}.md").read_text(encoding="utf-8")
    intro = text.split("\n## ", 1)[0].split("\n", 3)[-1].strip()
    intro = "\n".join(line for line in intro.splitlines() if not line.startswith("🌐")).strip()
    out = {}
    for match in re.finditer(r"^### (\S+)\n(.*?)(?=^### |^## |\Z)", text, re.M | re.S):
        out[match.group(1)] = match.group(2).strip()
    return intro, out


def tests_for(slug: str) -> list[dict]:
    """The test file named after the agent, and test_agents.py, which runs every handler (admission,
    determinism, probes). For the first three agents, whose cases live in test_agents.py only, that
    file is their test."""
    found = []
    for name in (f"test_{slug.replace('-', '_')}.py", "test_agents.py"):
        path = ROOT / "tests" / name
        if path.exists():
            source = path.read_text(encoding="utf-8")
            found.append({"file": "tests/" + name, "tests": len(re.findall(r"^def test_", source, re.M))})
    return found


def data_for(slug: str) -> list[str]:
    under = slug.replace("-", "_")
    return sorted("tests/" + p.name for p in (ROOT / "tests").glob(f"{under}*.json"))



# ------------------------------------------------------------------ a small Markdown renderer


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out


def markdown(text: str) -> str:
    parts, out = re.split(r"(```[a-z]*\n.*?\n```)", text, flags=re.S), []
    for part in parts:
        if part.startswith("```"):
            body = part.split("\n", 1)[1].rsplit("\n```", 1)[0]
            out.append("<pre><code>" + html.escape(body) + "</code></pre>")
            continue
        for para in re.split(r"\n\s*\n", part.strip()):
            if para.strip():
                out.append("<p>" + _inline(" ".join(para.split())) + "</p>")
    return "\n".join(out)


# ------------------------------------------------------------------ the page

T = {
    "": {
        "offline": "no network", "caller_host": "the host you name",
        "title": "HESTIA agents — catalogue", "lang": "en", "agents": "Agents",
        "what": "What it answers", "network": "Network", "price": "Price", "free": "free",
        "none": "No network: everything comes in the request.",
        "reaches": "Reaches only", "named": "and the host you name in",
        "sandbox": "Sandbox", "code": "Code", "tests": "Tests", "data": "Recorded data it replays",
        "signature": "Signature", "schema": "Input schema", "source": "source",
        "sig_text": "Every answer is signed by the hearth with Ed25519 over the result, the capability id and "
                    "the SHA-256 of your input. Check it with signature.verify@v1, format \"hestia\".",
        "sandbox_text": "{runtime} in WebAssembly (wasmtime): no filesystem beyond the read-only standard "
                        "library, no sockets, no processes, no secrets. {timeout:g} s and {memory} MB per call. "
                        "Network only through the hearth: HTTPS on port 443 to public addresses, no redirects "
                        "followed, at most {rounds} requests per call, {kib} KiB per response.",
        "code_text": "The handler that a deploy sends, {bytes} bytes, SHA-256 {sha}.",
        "how": "How to call",
        "how_text": "Through a hub with credits: POST {hub}/ai-market/v2/invoke with the capability id. "
                    "Directly: POST {hearth}/t/<slug>/invoke; a priced agent answers 402 with its x402 terms.",
        "limits": "Hearth limits (from the HESTIA source)",
        "roster": "Live roster of the hearth", "sums": "SHA-256 of every handler",
    },
    ".ru": {
        "offline": "без сети", "caller_host": "хост, названный вами",
        "title": "Агенты HESTIA — каталог", "lang": "ru", "agents": "Агенты",
        "what": "Что отвечает", "network": "Сеть", "price": "Цена", "free": "бесплатно",
        "none": "Без сети: всё нужное приходит в запросе.",
        "reaches": "Обращается только к", "named": "и к хосту, который вы назвали в",
        "sandbox": "Песочница", "code": "Код", "tests": "Тесты", "data": "Записанные данные, на которых проверяется",
        "signature": "Подпись", "schema": "Схема входа", "source": "исходник",
        "sig_text": "Каждый ответ Гестия подписывает Ed25519 — подпись покрывает результат, идентификатор "
                    "возможности и SHA-256 вашего входа. Проверить: signature.verify@v1, format \"hestia\".",
        "sandbox_text": "{runtime} в WebAssembly (wasmtime): никакой файловой системы, кроме стандартной "
                        "библиотеки только для чтения, никаких сокетов, процессов и секретов. {timeout:g} с и "
                        "{memory} МБ на вызов. Сеть — только через Гестию: HTTPS на порт 443 к публичным адресам, "
                        "без перехода по редиректам, не больше {rounds} запросов за вызов, {kib} КиБ на ответ.",
        "code_text": "Обработчик, который отправляет выкат, {bytes} байт, SHA-256 {sha}.",
        "how": "Как вызвать",
        "how_text": "Через хаб с кредитами: POST {hub}/ai-market/v2/invoke с идентификатором возможности. "
                    "Напрямую: POST {hearth}/t/<slug>/invoke; платный агент отвечает 402 с условиями x402.",
        "limits": "Ограничения Гестии (из исходников HESTIA)",
        "roster": "Живой список агентов Гестии", "sums": "SHA-256 каждого обработчика",
    },
    ".es": {
        "offline": "sin red", "caller_host": "el host que usted nombre",
        "title": "Agentes de HESTIA — catálogo", "lang": "es", "agents": "Agentes",
        "what": "Qué responde", "network": "Red", "price": "Precio", "free": "gratis",
        "none": "Sin red: todo llega en la petición.",
        "reaches": "Solo llega a", "named": "y al host que usted nombre en",
        "sandbox": "Sandbox", "code": "Código", "tests": "Pruebas", "data": "Datos grabados que reproduce",
        "signature": "Firma", "schema": "Esquema de entrada", "source": "código",
        "sig_text": "El hearth firma cada respuesta con Ed25519 sobre el resultado, el id de la capacidad y el "
                    "SHA-256 de su entrada. Verifíquela con signature.verify@v1, format \"hestia\".",
        "sandbox_text": "{runtime} en WebAssembly (wasmtime): sin sistema de archivos salvo la biblioteca estándar "
                        "de solo lectura, sin sockets, procesos ni secretos. {timeout:g} s y {memory} MB por "
                        "llamada. Red solo a través del hearth: HTTPS al puerto 443 hacia direcciones públicas, sin "
                        "seguir redirecciones, como mucho {rounds} peticiones por llamada, {kib} KiB por respuesta.",
        "code_text": "El handler que envía un despliegue, {bytes} bytes, SHA-256 {sha}.",
        "how": "Cómo llamarlos",
        "how_text": "Por un hub con créditos: POST {hub}/ai-market/v2/invoke con el id de la capacidad. "
                    "Directamente: POST {hearth}/t/<slug>/invoke; un agente de pago responde 402 con sus "
                    "condiciones x402.",
        "limits": "Límites del hearth (del código de HESTIA)",
        "roster": "Lista en vivo del hearth", "sums": "SHA-256 de cada handler",
    },
    ".fr": {
        "offline": "sans réseau", "caller_host": "l'hôte que vous nommez",
        "title": "Agents HESTIA — catalogue", "lang": "fr", "agents": "Agents",
        "what": "Ce qu'il répond", "network": "Réseau", "price": "Prix", "free": "gratuit",
        "none": "Sans réseau : tout arrive dans la requête.",
        "reaches": "N'atteint que", "named": "et l'hôte que vous nommez dans",
        "sandbox": "Bac à sable", "code": "Code", "tests": "Tests", "data": "Données enregistrées qu'il rejoue",
        "signature": "Signature", "schema": "Schéma d'entrée", "source": "source",
        "sig_text": "Le foyer signe chaque réponse avec Ed25519 sur le résultat, l'identifiant de la capacité et "
                    "le SHA-256 de votre entrée. Vérifiez-la avec signature.verify@v1, format \"hestia\".",
        "sandbox_text": "{runtime} en WebAssembly (wasmtime) : aucun système de fichiers hormis la bibliothèque "
                        "standard en lecture seule, ni sockets, ni processus, ni secrets. {timeout:g} s et "
                        "{memory} Mo par appel. Réseau uniquement via le foyer : HTTPS sur le port 443 vers des "
                        "adresses publiques, sans suivre de redirection, au plus {rounds} requêtes par appel, "
                        "{kib} Kio par réponse.",
        "code_text": "Le handler qu'envoie un déploiement, {bytes} octets, SHA-256 {sha}.",
        "how": "Comment les appeler",
        "how_text": "Par un hub avec des crédits : POST {hub}/ai-market/v2/invoke avec l'identifiant de la "
                    "capacité. Directement : POST {hearth}/t/<slug>/invoke ; un agent payant répond 402 avec ses "
                    "conditions x402.",
        "limits": "Limites du foyer (d'après le code de HESTIA)",
        "roster": "Liste en direct du foyer", "sums": "SHA-256 de chaque handler",
    },
    ".zh": {
        "offline": "不联网", "caller_host": "你指定的主机",
        "title": "HESTIA 智能体目录", "lang": "zh", "agents": "智能体",
        "what": "回答什么", "network": "网络", "price": "价格", "free": "免费",
        "none": "不联网：所需的一切都在请求中。",
        "reaches": "只访问", "named": "以及你在下列字段中指定的主机：",
        "sandbox": "沙箱", "code": "代码", "tests": "测试", "data": "它重放的录制数据",
        "signature": "签名", "schema": "输入模式", "source": "源码",
        "sig_text": "hearth 用 Ed25519 为每个回答签名，签名覆盖结果、能力标识和你的输入的 SHA-256。"
                    "用 signature.verify@v1（format \"hestia\"）核对。",
        "sandbox_text": "{runtime}，运行在 WebAssembly（wasmtime）中：除只读标准库外没有文件系统，没有套接字、进程和密钥。"
                        "每次调用 {timeout:g} 秒、{memory} MB。网络只能经由 hearth：仅限 443 端口的 HTTPS、仅限公网地址，"
                        "不跟随重定向，每次调用最多 {rounds} 个请求，每个响应最多 {kib} KiB。",
        "code_text": "部署时发送的处理程序，{bytes} 字节，SHA-256 {sha}。",
        "how": "如何调用",
        "how_text": "通过枢纽用积分支付：POST {hub}/ai-market/v2/invoke 并带上能力标识。直接调用：POST {hearth}/t/<slug>/invoke；"
                    "收费智能体会返回带 x402 条款的 402。",
        "limits": "hearth 限制（取自 HESTIA 源码）",
        "roster": "hearth 实时名单", "sums": "每个处理程序的 SHA-256",
    },
}

# The live comparison and the "check it yourself" block; live.js reads the live_* strings from the page.
T_LIVE = {
    "": {
        "now": "Now", "full_text": "Full catalogue text", "files": "Files",
        "data_note": 'In the recorded replies published here, e-mail addresses and local build paths are replaced by a marker (counted per file in catalog.json); the tests run on the unedited recordings.',
        "license": "The agents' code is published under the MIT licence.",
        "verify": "Check it yourself",
        "verify_text": "The hearth's public roster gives, for every agent it runs, the SHA-256 of the handler "
                       "file it hands the sandbox on each call (handler_sha256). This page compares it with the "
                       "source published here when it loads. To compare by hand, for one agent:",
        "verify_note": "Needs curl, jq and sha256sum (on macOS: shasum -a 256). Both commands print the same hex "
                       "digest when the hearth runs exactly the published file.",
        "live_copy": "copy", "live_copied": "copied",
        "live_wait": "checking…", "live_same": "same code", "live_differs": "different code",
        "live_absent": "not running", "live_nohash": "no digest", "live_error": "roster not read",
        "live_card_same": "Running on the hearth now, with this exact SHA-256.",
        "live_card_differs": "Running on the hearth now with different code: SHA-256 {sha}.",
        "live_card_absent": "Not on the hearth's roster now.",
        "live_card_nohash": "On the roster, but the hearth publishes no digest for it.",
        "live_summary": "Compared with the hearth's roster just now: {same} of {total} agents run exactly the "
                        "published code, {differs} run different code, {absent} are not running.",
        "live_summary_all": "All {total} agents run exactly the published code: compared with the hearth's roster just now.",
        "live_failed": "The hearth's roster could not be read ({error}); the comparison is not shown.",
        "others": "Other agents on this hearth",
        "others_text": "Agents of other owners, and any agent of the operator whose code is not in this catalogue. "
                       "Their source is not published here; the roster still gives each one's SHA-256, so an owner "
                       "who publishes the source lets anyone match it.",
        "others_none": "None at the moment.", "owner": "Owner", "owner_operator": "operator",
        "owner_other": "another owner",
    },
    ".ru": {
        "now": "Сейчас", "full_text": "Полный текст каталога", "files": "Файлы",
        "data_note": 'В опубликованных здесь записанных ответах адреса почты и локальные пути сборки заменены пометкой (сколько и в каком файле — в catalog.json); тесты работают на неизменённых записях.',
        "license": "Код агентов опубликован под лицензией MIT.",
        "verify": "Проверьте сами",
        "verify_text": "Публичный список агентов Гестии для каждого работающего агента даёт SHA-256 файла "
                       "обработчика, который она передаёт песочнице при каждом вызове (handler_sha256). Эта страница "
                       "при загрузке сравнивает его с опубликованным здесь исходником. Сравнить вручную для одного "
                       "агента:",
        "verify_note": "Нужны curl, jq и sha256sum (на macOS: shasum -a 256). Если Гестия выполняет ровно "
                       "опубликованный файл, обе команды печатают один и тот же хеш.",
        "live_copy": "копировать", "live_copied": "скопировано",
        "live_wait": "проверяю…", "live_same": "тот же код", "live_differs": "другой код",
        "live_absent": "не запущен", "live_nohash": "нет хеша", "live_error": "список не прочитан",
        "live_card_same": "Сейчас работает на Гестии, ровно с этим SHA-256.",
        "live_card_differs": "Сейчас работает на Гестии с другим кодом: SHA-256 {sha}.",
        "live_card_absent": "Сейчас его нет в списке агентов Гестии.",
        "live_card_nohash": "Есть в списке, но Гестия не публикует для него хеш.",
        "live_summary": "Сверка со списком агентов Гестии только что: {same} из {total} агентов выполняют ровно "
                        "опубликованный код, у {differs} код другой, {absent} не запущены.",
        "live_summary_all": 'Все {total} агентов выполняют ровно опубликованный код — сверено со списком агентов Гестии только что.',
        "live_failed": "Список агентов Гестии не прочитан ({error}); сверка не показана.",
        "others": "Другие агенты на этой Гестии",
        "others_text": "Агенты других владельцев и агенты оператора, чьего кода нет в этом каталоге. Их исходники "
                       "здесь не опубликованы; список всё равно даёт SHA-256 каждого, так что владелец, "
                       "опубликовав исходник, позволит любому его сверить.",
        "others_none": "Сейчас таких нет.", "owner": "Владелец", "owner_operator": "оператор",
        "owner_other": "другой владелец",
    },
    ".es": {
        "now": "Ahora", "full_text": "Texto completo del catálogo", "files": "Archivos",
        "data_note": 'En las respuestas grabadas que se publican aquí, las direcciones de correo y las rutas locales de compilación se sustituyen por una marca (contadas por archivo en catalog.json); las pruebas usan las grabaciones sin editar.',
        "license": "El código de los agentes se publica bajo la licencia MIT.",
        "verify": "Compruébelo usted",
        "verify_text": "La lista pública del hearth da, para cada agente que ejecuta, el SHA-256 del archivo del "
                       "handler que entrega al sandbox en cada llamada (handler_sha256). Esta página lo compara al "
                       "cargarse con el código publicado aquí. Para compararlo a mano con un agente:",
        "verify_note": "Necesita curl, jq y sha256sum (en macOS: shasum -a 256). Si el hearth ejecuta exactamente "
                       "el archivo publicado, ambos comandos imprimen el mismo hash.",
        "live_copy": "copiar", "live_copied": "copiado",
        "live_wait": "comprobando…", "live_same": "mismo código", "live_differs": "código distinto",
        "live_absent": "no está en marcha", "live_nohash": "sin hash", "live_error": "lista no leída",
        "live_card_same": "En marcha en el hearth ahora, con este mismo SHA-256.",
        "live_card_differs": "En marcha en el hearth ahora con otro código: SHA-256 {sha}.",
        "live_card_absent": "Ahora no figura en la lista del hearth.",
        "live_card_nohash": "Figura en la lista, pero el hearth no publica su hash.",
        "live_summary": "Comparado ahora mismo con la lista del hearth: {same} de {total} agentes ejecutan "
                        "exactamente el código publicado, {differs} ejecutan otro código y {absent} no están en "
                        "marcha.",
        "live_summary_all": 'Los {total} agentes ejecutan exactamente el código publicado: comparado ahora mismo con la lista del hearth.',
        "live_failed": "No se pudo leer la lista del hearth ({error}); no se muestra la comparación.",
        "others": "Otros agentes de este hearth",
        "others_text": "Agentes de otros propietarios y agentes del operador cuyo código no está en este catálogo. "
                       "Su código no se publica aquí; la lista da igualmente el SHA-256 de cada uno, así que un "
                       "propietario que publique el código permite a cualquiera cotejarlo.",
        "others_none": "Ninguno por ahora.", "owner": "Propietario", "owner_operator": "operador",
        "owner_other": "otro propietario",
    },
    ".fr": {
        "now": "Maintenant", "full_text": "Texte complet du catalogue", "files": "Fichiers",
        "data_note": 'Dans les réponses enregistrées publiées ici, les adresses e-mail et les chemins locaux de build sont remplacés par une marque (comptés par fichier dans catalog.json) ; les tests tournent sur les enregistrements non modifiés.',
        "license": "Le code des agents est publié sous licence MIT.",
        "verify": "Vérifiez vous-même",
        "verify_text": "La liste publique du foyer donne, pour chaque agent qu'il fait tourner, le SHA-256 du "
                       "fichier handler qu'il remet au bac à sable à chaque appel (handler_sha256). Cette page le "
                       "compare au chargement avec le code publié ici. Pour comparer à la main, pour un agent :",
        "verify_note": "Il faut curl, jq et sha256sum (sur macOS : shasum -a 256). Si le foyer exécute exactement "
                       "le fichier publié, les deux commandes affichent le même hachage.",
        "live_copy": "copier", "live_copied": "copié",
        "live_wait": "vérification…", "live_same": "même code", "live_differs": "code différent",
        "live_absent": "arrêté", "live_nohash": "pas de hachage", "live_error": "liste non lue",
        "live_card_same": "Tourne sur le foyer en ce moment, avec ce SHA-256 exact.",
        "live_card_differs": "Tourne sur le foyer en ce moment avec un autre code : SHA-256 {sha}.",
        "live_card_absent": "Absent de la liste du foyer en ce moment.",
        "live_card_nohash": "Dans la liste, mais le foyer ne publie pas son hachage.",
        "live_summary": "Comparé à l'instant avec la liste du foyer : {same} agents sur {total} exécutent "
                        "exactement le code publié, {differs} un autre code, {absent} ne tournent pas.",
        "live_summary_all": "Les {total} agents exécutent exactement le code publié : comparé à l'instant avec la liste du foyer.",
        "live_failed": "La liste du foyer n'a pas pu être lue ({error}) ; la comparaison n'est pas affichée.",
        "others": "Autres agents de ce foyer",
        "others_text": "Les agents d'autres propriétaires, et ceux de l'opérateur dont le code n'est pas dans ce "
                       "catalogue. Leur code n'est pas publié ici ; la liste donne tout de même le SHA-256 de "
                       "chacun, si bien qu'un propriétaire qui publie son code permet à chacun de le comparer.",
        "others_none": "Aucun pour l'instant.", "owner": "Propriétaire", "owner_operator": "opérateur",
        "owner_other": "autre propriétaire",
    },
    ".zh": {
        "now": "当前", "full_text": "完整目录文本", "files": "文件",
        "data_note": '此处发布的录制响应中，电子邮件地址和本地构建路径已替换为标记（每个文件的数量见 catalog.json）；测试使用未经修改的录制数据。',
        "license": "智能体代码以 MIT 许可证发布。",
        "verify": "自行核对",
        "verify_text": "hearth 的公开名单为它运行的每个智能体给出处理程序文件的 SHA-256（handler_sha256），"
                       "也就是每次调用时交给沙箱的那个文件。本页加载时会把它与这里发布的源码比对。手动比对某个智能体：",
        "verify_note": "需要 curl、jq 和 sha256sum（macOS 上用 shasum -a 256）。如果 hearth 运行的正是所发布的文件，"
                       "两条命令会输出同一个哈希。",
        "live_copy": "复制", "live_copied": "已复制",
        "live_wait": "核对中…", "live_same": "代码相同", "live_differs": "代码不同",
        "live_absent": "未运行", "live_nohash": "无哈希", "live_error": "名单未读取",
        "live_card_same": "当前正在 hearth 上运行，SHA-256 与此完全一致。",
        "live_card_differs": "当前正在 hearth 上运行，但代码不同：SHA-256 {sha}。",
        "live_card_absent": "当前不在 hearth 的名单上。",
        "live_card_nohash": "在名单上，但 hearth 没有公布它的哈希。",
        "live_summary": "刚刚与 hearth 名单比对：{total} 个智能体中有 {same} 个运行的正是所发布的代码，"
                        "{differs} 个代码不同，{absent} 个未运行。",
        "live_summary_all": '全部 {total} 个智能体运行的正是所发布的代码：刚刚与 hearth 名单比对。',
        "live_failed": "无法读取 hearth 的名单（{error}），因此不显示比对结果。",
        "others": "此 hearth 上的其他智能体",
        "others_text": "其他所有者的智能体，以及代码不在本目录中的运营者智能体。它们的源码不在这里发布；"
                       "名单仍给出每个智能体的 SHA-256，所有者一旦公布源码，任何人都能比对。",
        "others_none": "目前没有。", "owner": "所有者", "owner_operator": "运营者",
        "owner_other": "其他所有者",
    },
}

# The page's own words (navigation, hero, figures, footer); the live check's words are in T_LIVE.
T_UI = {
    "": {
        "kicker": "Agent catalogue", "h1": "Every agent, its code and its <em>SHA-256</em>",
        "nav_hearth": "Hearth", "nav_agents": "Agents", "nav_verify": "Check", "nav_limits": "Limits",
        "nav_others": "Others",
        "m_agents": "agents", "m_free": "free", "m_offline": "no network", "m_live": "run the published code",
        "m_signed": "every answer signed",
        "lede_agents": "Open an agent for what it answers, where it may connect, its code and its tests.",
        "foot_about": "HESTIA runs each agent in a WebAssembly sandbox and signs every answer with Ed25519.",
        "foot_links": "Links", "proof_pub": "published here", "proof_live": "running on the hearth",
    },
    ".ru": {
        "kicker": "Каталог агентов", "h1": "Каждый агент, его код и его <em>SHA-256</em>",
        "nav_hearth": "Гестия", "nav_agents": "Агенты", "nav_verify": "Проверка", "nav_limits": "Лимиты",
        "nav_others": "Другие",
        "m_agents": "агентов", "m_free": "бесплатных", "m_offline": "без сети",
        "m_live": "выполняют опубликованный код", "m_signed": "каждый ответ подписан",
        "lede_agents": "Откройте агента: что он отвечает, куда может обращаться, его код и тесты.",
        "foot_about": "Гестия запускает каждого агента в песочнице WebAssembly и подписывает каждый ответ Ed25519.",
        "foot_links": "Ссылки", "proof_pub": "опубликован здесь", "proof_live": "работает на Гестии",
    },
    ".es": {
        "kicker": "Catálogo de agentes", "h1": "Cada agente, su código y su <em>SHA-256</em>",
        "nav_hearth": "Hearth", "nav_agents": "Agentes", "nav_verify": "Comprobar", "nav_limits": "Límites",
        "nav_others": "Otros",
        "m_agents": "agentes", "m_free": "gratis", "m_offline": "sin red",
        "m_live": "ejecutan el código publicado", "m_signed": "cada respuesta firmada",
        "lede_agents": "Abra un agente para ver qué responde, adónde puede conectarse, su código y sus pruebas.",
        "foot_about": "HESTIA ejecuta cada agente en un sandbox de WebAssembly y firma cada respuesta con Ed25519.",
        "foot_links": "Enlaces", "proof_pub": "publicado aquí", "proof_live": "en marcha en el hearth",
    },
    ".fr": {
        "kicker": "Catalogue des agents", "h1": "Chaque agent, son code et son <em>SHA-256</em>",
        "nav_hearth": "Foyer", "nav_agents": "Agents", "nav_verify": "Vérifier", "nav_limits": "Limites",
        "nav_others": "Autres",
        "m_agents": "agents", "m_free": "gratuits", "m_offline": "sans réseau",
        "m_live": "exécutent le code publié", "m_signed": "chaque réponse signée",
        "lede_agents": "Ouvrez un agent : ce qu'il répond, où il peut se connecter, son code et ses tests.",
        "foot_about": "HESTIA exécute chaque agent dans un bac à sable WebAssembly et signe chaque réponse avec "
                      "Ed25519.",
        "foot_links": "Liens", "proof_pub": "publié ici", "proof_live": "tourne sur le foyer",
    },
    ".zh": {
        "kicker": "智能体目录", "h1": "每个智能体、它的代码和它的 <em>SHA-256</em>",
        "nav_hearth": "Hearth", "nav_agents": "智能体", "nav_verify": "核对", "nav_limits": "限制",
        "nav_others": "其他",
        "m_agents": "个智能体", "m_free": "免费", "m_offline": "不联网", "m_live": "运行所发布的代码",
        "m_signed": "每个回答都签名",
        "lede_agents": "打开一个智能体，查看它回答什么、可以连接哪里、它的代码和测试。",
        "foot_about": "HESTIA 在 WebAssembly 沙箱中运行每个智能体，并用 Ed25519 为每个回答签名。",
        "foot_links": "链接", "proof_pub": "此处发布", "proof_live": "hearth 上运行",
    },
}

LIMIT_LABELS = {
    "": ("time per call, s", "memory per call, MB", "requests per call", "KiB per response",
         "time per request, s", "hosts an agent may declare", "requests a minute per agent",
         "requests a minute to one caller-named host", "Python runtime", "JavaScript runtime"),
    ".ru": ("время на вызов, с", "память на вызов, МБ", "запросов за вызов", "КиБ на ответ",
            "время на запрос, с", "хостов, которые агент может объявить", "запросов в минуту на агента",
            "запросов в минуту к одному хосту, названному вызывающим", "среда Python", "среда JavaScript"),
    ".es": ("tiempo por llamada, s", "memoria por llamada, MB", "peticiones por llamada", "KiB por respuesta",
            "tiempo por petición, s", "hosts que un agente puede declarar", "peticiones por minuto por agente",
            "peticiones por minuto a un host nombrado por quien llama", "entorno Python", "entorno JavaScript"),
    ".fr": ("temps par appel, s", "mémoire par appel, Mo", "requêtes par appel", "Kio par réponse",
            "temps par requête, s", "hôtes qu'un agent peut déclarer", "requêtes par minute par agent",
            "requêtes par minute vers un hôte nommé par l'appelant", "environnement Python",
            "environnement JavaScript"),
    ".zh": ("每次调用时间（秒）", "每次调用内存（MB）", "每次调用请求数", "每个响应 KiB", "每个请求时间（秒）",
            "智能体可声明的主机数", "每个智能体每分钟请求数", "对调用方指定的单个主机每分钟请求数",
            "Python 运行时", "JavaScript 运行时"),
}

# The hearth's landing look (docs/landing/index.html): the same palette, type and layered panels,
# without its 3D stage. Dark only, like the landing. Fonts come from the hearth's own /fonts/.
CSS = """
:root{--void:#140c08;--panel:rgba(22,13,8,.74);--panel-2:rgba(30,18,11,.86);
--ink:#f4ebe0;--ink-2:#e2d2c0;--muted:#b89f86;--faint:#7f6956;
--ember:#ff9a3c;--ember-hi:#ffc266;--ember-lo:#c45a18;--ok:#66f7c5;--bad:#ff7b62;
--line:rgba(255,154,60,.22);--line-2:rgba(255,255,255,.07);--line-hot:rgba(102,247,197,.42);
--head:"Syne",system-ui,-apple-system,sans-serif;--body:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;--ease:cubic-bezier(.22,.68,.16,1);
--lift:0 1px 0 rgba(255,255,255,.045) inset,0 22px 48px -30px rgba(0,0,0,.92),0 10px 22px -16px rgba(0,0,0,.6);
--glow:0 1px 0 rgba(255,255,255,.06) inset,0 30px 70px -34px rgba(0,0,0,.95),0 18px 46px -26px rgba(255,140,50,.32)}
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%;overflow-x:clip;scroll-padding-top:76px}
body{margin:0;background:var(--void);color:var(--ink);font:16px/1.6 var(--body);-webkit-font-smoothing:antialiased;
text-rendering:optimizeLegibility}
::selection{background:rgba(255,154,60,.28);color:#fff}
:focus-visible{outline:2px solid var(--ok);outline-offset:3px;border-radius:4px}
a{color:var(--ember-hi);text-decoration-color:rgba(255,194,102,.35);text-underline-offset:3px}
a:hover{color:var(--ember);text-decoration-color:currentColor}
h1,h2,h3{text-wrap:balance}p{text-wrap:pretty}
code{font-family:var(--mono);font-size:.86em;color:var(--ink-2);background:rgba(255,154,60,.08);
border:1px solid rgba(255,154,60,.14);padding:1px 6px;border-radius:6px;overflow-wrap:anywhere}
pre{margin:14px 0;background:linear-gradient(180deg,rgba(12,8,6,.94),rgba(9,6,4,.9));border:1px solid var(--line);
border-radius:14px;padding:14px 16px;overflow:auto;font:12.5px/1.55 var(--mono);color:var(--ink-2);
box-shadow:0 1px 0 rgba(255,255,255,.04) inset,0 16px 32px -24px rgba(0,0,0,.9)}
pre code{background:none;border:0;padding:0;font-size:inherit;overflow-wrap:normal}
.nebula{position:fixed;inset:0;z-index:0;pointer-events:none;background:
radial-gradient(58vw 46vw at 84% 2%,rgba(255,154,60,.17),transparent 58%),
radial-gradient(46vw 40vw at 6% 70%,rgba(102,247,197,.07),transparent 55%),
radial-gradient(70vw 44vw at 50% 112%,rgba(255,80,20,.07),transparent 52%),linear-gradient(165deg,#1c1008,#0e0906)}
.grain{position:fixed;inset:0;z-index:1;pointer-events:none;opacity:.16;mix-blend-mode:overlay;
background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='.5'/%3E%3C/svg%3E")}
.vignette{position:fixed;inset:0;z-index:1;pointer-events:none;box-shadow:inset 0 0 240px 60px rgba(8,5,3,.78)}
.wrap{position:relative;z-index:2;max-width:1180px;margin:0 auto;padding:0 max(18px,env(safe-area-inset-right))
0 max(18px,env(safe-area-inset-left))}
nav{position:sticky;top:0;z-index:60;backdrop-filter:blur(16px) saturate(130%);-webkit-backdrop-filter:blur(16px);
background:linear-gradient(180deg,rgba(20,12,8,.95),rgba(20,12,8,.55));border-bottom:1px solid var(--line)}
nav .row{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:60px}
.brand{display:flex;align-items:center;gap:10px;font:800 15px/1 var(--head);letter-spacing:.14em;color:var(--ink);
text-decoration:none;white-space:nowrap}
.brand:hover{color:var(--ink)}.brand small{font:600 10px/1 var(--mono);letter-spacing:.14em;color:var(--ember);
text-transform:uppercase}
.pip{width:12px;height:12px;border-radius:50%;flex:none;background:radial-gradient(circle at 34% 30%,#fff6e8,var(--ember) 46%,
#6a2c0c);box-shadow:0 0 18px rgba(255,154,60,.55);animation:pip 3s var(--ease) infinite}
@keyframes pip{0%,100%{transform:scale(1);opacity:.9}50%{transform:scale(1.14);opacity:1}}
.nav-links{display:flex;gap:2px;align-items:center}
.nav-links a{color:var(--muted);text-decoration:none;font:500 12px/1 var(--mono);letter-spacing:.07em;padding:9px 11px;
border-radius:8px;transition:color .2s var(--ease),background .2s var(--ease);white-space:nowrap}
.nav-links a:hover{color:var(--ember);background:rgba(255,154,60,.07)}
.langs{display:flex;gap:2px;padding:3px;border:1px solid var(--line);border-radius:9px;background:rgba(20,12,8,.6);flex:none}
.langs a,.langs strong{font:600 10px/1 var(--mono);letter-spacing:.08em;padding:6px 7px;border-radius:6px;
text-decoration:none;color:var(--faint);text-transform:uppercase}
.langs a:hover{color:var(--ember)}.langs strong{background:rgba(255,154,60,.17);color:var(--ember-hi)}
.hero{padding:clamp(34px,6vw,72px) 0 8px}
.kicker{display:inline-flex;align-items:center;gap:10px;font:600 10.5px/1 var(--mono);letter-spacing:.2em;
text-transform:uppercase;color:var(--ember);margin:0 0 18px}
.kicker:before{content:"";width:30px;height:1px;background:var(--ember);box-shadow:0 0 12px var(--ember)}
h1{margin:0;font:800 clamp(2.2rem,5.6vw,3.7rem)/1 var(--head);letter-spacing:-.025em;max-width:16em}
h1 em{font-style:normal;background:linear-gradient(180deg,var(--ember-hi),var(--ember-lo));-webkit-background-clip:text;
background-clip:text;-webkit-text-fill-color:transparent;color:var(--ember)}
.hero-grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr);gap:clamp(24px,4vw,48px);
align-items:center}
.hero-grid>*{min-width:0}
.proof{position:relative;border-radius:20px;padding:1px;background:linear-gradient(150deg,rgba(255,194,102,.55),
rgba(255,154,60,.12) 38%,rgba(102,247,197,.35));box-shadow:0 40px 90px -36px rgba(0,0,0,.95),
0 24px 60px -30px rgba(255,140,50,.38)}
.proof-in{border-radius:19px;background:radial-gradient(120% 90% at 50% 0,rgba(40,23,13,.96),rgba(12,8,6,.97));
padding:16px 18px 18px;overflow:hidden}
.proof-top{display:flex;align-items:center;justify-content:space-between;gap:10px;font:600 10px/1 var(--mono);
letter-spacing:.12em;text-transform:uppercase;color:var(--faint);padding-bottom:14px;border-bottom:1px solid var(--line-2)}
.dots{display:flex;gap:6px}.dots i{width:8px;height:8px;border-radius:50%;background:rgba(255,154,60,.35)}
.dots i:first-child{background:var(--ember)}.dots i:last-child{background:rgba(102,247,197,.5)}
.p-slug{margin:16px 0 14px;font:700 1.05rem/1.2 var(--head)}.p-slug code{font-size:11px;margin-left:6px}
.p-row{display:grid;gap:6px;padding:12px 14px;border:1px solid var(--line-2);border-radius:12px;background:rgba(255,255,255,.02)}
.p-k{font:600 10px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.p-v{background:none;border:0;padding:0;font-size:13px;color:var(--ember-hi);overflow-wrap:anywhere}
.p-row.live .p-v{color:var(--ok)}
.p-eq{display:grid;place-items:center;height:34px;font:800 22px/1 var(--head);color:var(--ember);
text-shadow:0 0 18px rgba(255,154,60,.6)}
.p-verdict{display:flex;justify-content:center;margin-top:14px}.p-verdict .chip{font-size:10.5px;padding:7px 12px}
.lead{max-width:46rem;color:var(--ink-2);font-size:clamp(15px,1.45vw,17px);margin-top:20px}
.lead p{margin:0 0 .8em}
.status{display:flex;align-items:flex-start;gap:12px;margin:24px 0 0;max-width:52rem;padding:14px 16px;border-radius:14px;
border:1px solid var(--line);background:var(--panel-2);box-shadow:var(--lift);font-size:.95rem;color:var(--ink-2)}
.status:before{content:"";flex:none;width:9px;height:9px;margin-top:.45em;border-radius:50%;background:var(--ember);
box-shadow:0 0 12px var(--ember);animation:beat 1.6s infinite}
.status[data-state=same]{border-color:var(--line-hot)}
.status[data-state=same]:before{background:var(--ok);box-shadow:0 0 12px var(--ok);animation:none}
.status[data-state=differs]{border-color:rgba(255,123,98,.5)}
.status[data-state=differs]:before{background:var(--bad);box-shadow:0 0 12px var(--bad);animation:none}
.status[data-state=error]:before{background:var(--faint);box-shadow:none;animation:none}
@keyframes beat{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}
.cta{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:12px 19px;border-radius:999px;font:700 12.5px/1 var(--head);
letter-spacing:.05em;text-decoration:none;border:1px solid transparent;transition:transform .22s var(--ease),
box-shadow .22s var(--ease),border-color .22s var(--ease)}
.btn:hover{transform:translateY(-2px)}
.btn-primary{background:linear-gradient(135deg,var(--ember-hi),#ff8c42);color:#1a1006;box-shadow:0 6px 26px rgba(255,154,60,.26)}
.btn-primary:hover{color:#1a1006;box-shadow:0 10px 38px rgba(255,154,60,.42)}
.btn-ghost{border-color:var(--line);color:var(--ink);background:rgba(20,12,8,.55);backdrop-filter:blur(8px)}
.btn-ghost:hover{color:var(--ink);border-color:var(--line-hot);box-shadow:0 0 24px rgba(102,247,197,.15)}
.metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:30px 0 6px}
.metric{border:1px solid var(--line);border-radius:14px;padding:15px 14px 13px;background:var(--panel);box-shadow:var(--lift)}
.metric .v{font:800 1.55rem/1 var(--head);color:var(--ember)}.metric .v.word{font-size:1.1rem;letter-spacing:.03em}
.metric .v.ok{color:var(--ok)}
.metric .k{margin-top:8px;font:600 10px/1.3 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.section{padding:clamp(40px,6vw,64px) 0 8px}
.section h2{font:800 clamp(1.55rem,3.2vw,2.15rem)/1.1 var(--head);letter-spacing:-.02em;margin:0 0 10px}
.eyebrow{font:600 10.5px/1 var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--ok);margin:0 0 12px}
.lede{margin:0 0 24px;color:var(--muted);max-width:46rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(262px,1fr));gap:12px}
.tile{position:relative;display:flex;flex-direction:column;gap:9px;padding:16px 16px 14px;border-radius:16px;
border:1px solid var(--line);background:linear-gradient(180deg,var(--panel-2),var(--panel));box-shadow:var(--lift);
color:var(--ink);text-decoration:none;overflow:hidden;transition:transform .22s var(--ease),border-color .22s var(--ease),
box-shadow .22s var(--ease)}
.tile:after{content:"";position:absolute;inset:0 0 auto;height:60px;pointer-events:none;
background:radial-gradient(120px 50px at 18% 0,rgba(255,154,60,.13),transparent 70%)}
.tile:hover{color:var(--ink);transform:translateY(-3px);border-color:rgba(255,154,60,.5);box-shadow:var(--glow)}
.tile-top{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.slug{font:700 15px/1.2 var(--head);letter-spacing:.01em;overflow-wrap:anywhere}
.tile .cap{align-self:flex-start;font-size:11px}
.blurb{color:var(--muted);font-size:.89rem;line-height:1.5;flex:1}
.tags{display:flex;flex-wrap:wrap;gap:6px}
.tag{font:600 9.5px/1 var(--mono);letter-spacing:.07em;padding:5px 8px;border-radius:999px;border:1px solid var(--line);
color:var(--muted);white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}
.tag.free{color:var(--ok);border-color:rgba(102,247,197,.35)}.tag.paid{color:var(--ember-hi);border-color:rgba(255,194,102,.4)}
.chip{flex:none;display:inline-flex;align-items:center;gap:6px;font:600 9.5px/1 var(--mono);letter-spacing:.07em;
padding:5px 8px;border-radius:999px;border:1px solid var(--line-2);color:var(--faint);white-space:nowrap}
.chip:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.9}
.chip[data-state=same]{color:var(--ok);border-color:rgba(102,247,197,.35);background:rgba(102,247,197,.06)}
.chip[data-state=differs]{color:var(--bad);border-color:rgba(255,123,98,.45);background:rgba(255,123,98,.07)}
.agents{display:grid;gap:16px;margin-top:34px}
.agent{position:relative;border:1px solid var(--line);border-radius:20px;padding:22px 22px 12px;
background:linear-gradient(180deg,rgba(32,19,11,.86),rgba(16,10,7,.82));box-shadow:var(--lift);overflow:hidden}
.agent:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;
background:linear-gradient(180deg,var(--ember),rgba(255,154,60,0) 70%)}
.agent:after{content:"";position:absolute;inset:0 0 auto;height:140px;pointer-events:none;
background:radial-gradient(420px 120px at 12% 0,rgba(255,154,60,.09),transparent 70%)}
.agent:target{border-color:rgba(255,154,60,.6);box-shadow:var(--glow)}
.agent-head{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:10px 16px;margin-bottom:6px}
.agent-head h3{margin:0 0 6px;font:800 1.3rem/1.15 var(--head);letter-spacing:-.01em;overflow-wrap:anywhere}
.agent-head .tags{align-items:center}
.agent>p,.agent>pre{position:relative;z-index:1}
.agent>p{color:var(--ink-2);max-width:62rem}
.facts{position:relative;z-index:1;display:grid;grid-template-columns:190px minmax(0,1fr);margin:16px 0 8px;
border:1px solid var(--line-2);border-radius:14px;overflow:hidden;background:rgba(10,6,4,.42);font-size:.92rem}
.facts dt,.facts dd{padding:10px 14px;border-top:1px solid var(--line-2)}
.facts dt:first-of-type,.facts dt:first-of-type+dd{border-top:0}
.facts dt{font:600 10.5px/1.5 var(--mono);letter-spacing:.09em;text-transform:uppercase;color:var(--faint);padding-top:12px}
.facts dd{margin:0;min-width:0;overflow-wrap:anywhere;color:var(--ink-2)}
.facts dd[data-state=same]{color:var(--ok)}.facts dd[data-state=differs]{color:var(--bad)}
.facts dd[data-state=absent],.facts dd[data-state=nohash],.facts dd[data-state=error]{color:var(--muted)}
details{position:relative;z-index:1;margin:6px 0 10px}
summary{cursor:pointer;width:max-content;max-width:100%;font:600 11px/1 var(--mono);letter-spacing:.08em;
text-transform:uppercase;color:var(--muted);padding:9px 12px;border:1px solid var(--line);border-radius:999px;
list-style:none;transition:color .2s var(--ease),border-color .2s var(--ease)}
summary::-webkit-details-marker{display:none}summary:before{content:"+ ";color:var(--ember)}
details[open] summary:before{content:"− "}summary:hover{color:var(--ember-hi);border-color:rgba(255,154,60,.5)}
.panel{border:1px solid var(--line);border-radius:18px;padding:20px;background:linear-gradient(180deg,var(--panel-2),var(--panel));
box-shadow:var(--lift)}
.panel p{color:var(--ink-2);margin:0 0 12px}.panel .note{color:var(--muted);font-size:.88rem}
.cmd{position:relative}.cmd pre{padding-right:84px}
.copy{position:absolute;top:10px;right:10px;background:rgba(255,154,60,.1);border:1px solid var(--line);color:var(--ember);
font:600 10px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;padding:7px 10px;border-radius:7px;cursor:pointer;
transition:.2s var(--ease)}
.copy:hover{background:rgba(255,154,60,.2);color:var(--ember-hi)}.copy.done{color:var(--ok);border-color:rgba(102,247,197,.4)}
.limits{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.limit{border:1px solid var(--line);border-radius:14px;padding:14px;background:var(--panel);box-shadow:var(--lift)}
.limit .v{font:800 1.45rem/1.1 var(--head);color:var(--ember)}.limit .v.word{font:600 .95rem/1.3 var(--mono);color:var(--ok)}
.limit .k{margin-top:8px;color:var(--muted);font-size:.84rem;line-height:1.4}
.table{overflow-x:auto;border:1px solid var(--line);border-radius:16px;background:var(--panel);box-shadow:var(--lift)}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th{font:600 10px/1.3 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);text-align:left;
padding:12px 14px;border-bottom:1px solid var(--line)}
td{padding:10px 14px;border-top:1px solid var(--line-2);vertical-align:top;color:var(--ink-2)}
tr:first-child td{border-top:0}
.muted{color:var(--muted)}
footer{position:relative;z-index:2;margin-top:clamp(48px,7vw,80px);border-top:1px solid var(--line);
background:linear-gradient(180deg,rgba(12,8,6,0),rgba(12,8,6,.72))}
.fgrid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:28px;padding:36px 0 18px}
.fgrid h5{margin:0 0 12px;font:600 9.5px/1 var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--faint)}
.fgrid p{margin:0 0 10px;color:var(--muted);font-size:13px;max-width:44ch}
.flinks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2px 18px}
.flinks a{color:var(--muted);text-decoration:none;font-size:13px;padding:4px 0;overflow-wrap:anywhere}
.flinks a:hover{color:var(--ember)}
.fbrand{display:flex;align-items:center;gap:10px;font:800 14px/1 var(--head);letter-spacing:.2em;margin-bottom:14px}
.fbot{padding:16px 0 32px;border-top:1px solid var(--line-2);color:var(--faint);font:500 11px/1.6 var(--mono)}
@media (max-width:1000px){.metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.hero-grid{grid-template-columns:1fr}
.proof{max-width:560px}}
@media (max-width:760px){.nav-links{display:none}.brand small{display:none}
.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.facts{grid-template-columns:minmax(0,1fr)}
.facts dt{border-top:1px solid var(--line-2);padding-bottom:2px}.facts dd{border-top:0;padding-top:2px}
.facts dt:first-of-type{border-top:0}.agent{padding:18px 16px 10px}.fgrid{grid-template-columns:1fr}
.tiles{grid-template-columns:minmax(0,1fr)}}
@media (max-width:420px){nav .row{flex-wrap:wrap;gap:8px;padding-top:8px;padding-bottom:8px}.brand{font-size:13px;letter-spacing:.09em}
.langs a,.langs strong{padding:6px 5px}h1{font-size:clamp(1.8rem,9.6vw,2.4rem)}.agent-head h3{font-size:1.15rem}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.pip,.status:before{animation:none}
.btn:hover,.tile:hover{transform:none}}
"""

LIVE_JS = """// Compares each agent's published handler (data-sha on its card) with the handler_sha256 that the
// hearth's public roster reports for the code it runs. Built by hestia-agents/scripts/build_catalog.py.
// Roster values are shown with textContent only: an owner's label is that owner's text, not markup.
(function () {
  "use strict";
  var text = JSON.parse(document.getElementById("live-text").textContent);
  var fill = function (s, v) { return s.replace(/\\{(\\w+)\\}/g, function (_, k) { return k in v ? String(v[k]) : ""; }); };
  var each = function (selector, fn) { Array.prototype.forEach.call(document.querySelectorAll(selector), fn); };
  var cards = Array.prototype.slice.call(document.querySelectorAll("section[data-agent][data-sha]"));
  var summary = document.getElementById("live-summary"), metric = document.getElementById("live-metric");
  var mark = function (slug, state, sha) {
    each('[data-live="' + slug + '"]', function (el) {
      el.setAttribute("data-state", state);
      el.textContent = el.getAttribute("data-kind") === "line"
        ? fill(text["live_card_" + state] || text["live_" + state], {sha: sha || ""})
        : text["live_" + state];
    });
  };
  each("button[data-copy]", function (button) {
    button.addEventListener("click", function () {
      var source = document.getElementById(button.getAttribute("data-copy"));
      if (!source || !navigator.clipboard) { return; }
      navigator.clipboard.writeText(source.textContent).then(function () {
        button.textContent = text.live_copied;
        button.classList.add("done");
        setTimeout(function () { button.textContent = text.live_copy; button.classList.remove("done"); }, 1600);
      }, function () {});
    });
  });
  var url = location.protocol === "file:" ? "https://hestia.modelmarket.dev/v1/hearth" : "/v1/hearth";
  fetch(url, {cache: "no-store"}).then(function (r) {
    if (!r.ok) { throw new Error("HTTP " + r.status); }
    return r.json();
  }).then(function (roster) {
    var rows = Array.isArray(roster.tenants) ? roster.tenants : [];
    var bySlug = {};
    rows.forEach(function (row) { if (row && typeof row.slug === "string") { bySlug[row.slug] = row; } });
    var count = {same: 0, differs: 0, absent: 0, nohash: 0};
    var known = {};
    cards.forEach(function (card) {
      var slug = card.getAttribute("data-agent"), row = bySlug[slug];
      known[slug] = true;
      var live = row && typeof row.handler_sha256 === "string" ? row.handler_sha256 : "";
      var state = !row ? "absent" : !live ? "nohash" : live === card.getAttribute("data-sha") ? "same" : "differs";
      count[state] += 1;
      mark(slug, state, live);
      each('[data-live-sha="' + slug + '"]', function (el) {
        el.textContent = live ? live.slice(0, 16) + "…" + live.slice(-8) : "—";
      });
      each('[data-live-eq="' + slug + '"]', function (el) { el.textContent = state === "same" ? "=" : "≠"; });
    });
    var all = count.same === cards.length;
    summary.textContent = fill(all ? text.live_summary_all : text.live_summary, {same: count.same,
      total: cards.length, differs: count.differs + count.nohash, absent: count.absent});
    summary.setAttribute("data-state", all ? "same" : count.differs + count.nohash ? "differs" : "absent");
    metric.textContent = count.same + "/" + cards.length;
    metric.className = all ? "v ok" : "v";
    var body = document.getElementById("others-body"), none = document.getElementById("others-none");
    var others = rows.filter(function (row) { return row && !known[row.slug]; });
    others.forEach(function (row) {
      var tr = document.createElement("tr");
      var owner = row.owner && row.owner.kind === "owner"
        ? text.owner_other + (row.owner.label ? " · " + String(row.owner.label) : "")
        : text.owner_operator;
      [String(row.slug || ""), String(row.capability_id || ""), owner,
       typeof row.handler_sha256 === "string" ? row.handler_sha256 : "—"].forEach(function (value, i) {
        var td = document.createElement("td");
        if (i === 1 || i === 3) { var code = document.createElement("code"); code.textContent = value; td.appendChild(code); }
        else { td.textContent = value; }
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    none.hidden = others.length > 0;
    document.getElementById("others-table").hidden = others.length === 0;
  }).catch(function (err) {
    cards.forEach(function (card) { mark(card.getAttribute("data-agent"), "error", ""); });
    summary.textContent = fill(text.live_failed, {error: String(err && err.message || err)});
    summary.setAttribute("data-state", "error");
    metric.textContent = "—";
  });
})();
"""

NAMES = {"": "English", ".ru": "Русский", ".es": "Español", ".fr": "Français", ".zh": "中文"}
CODES = {"": "EN", ".ru": "RU", ".es": "ES", ".fr": "FR", ".zh": "ZH"}


def blurb(text: str, limit: int = 140) -> str:
    """The first sentence of an agent's text, without links or code blocks, for its tile."""
    para = re.split(r"\n\s*\n|```", text.strip(), maxsplit=1)[0]
    para = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", " ".join(para.split()))
    first = re.split(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁ0-9`])|(?<=[。！？])", para, maxsplit=1)[0]
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0].rstrip(",;:—–-") + "…"
    out = html.escape(first, quote=False)
    return re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", out)


def _num(value) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def page(lang: str, cards: list[dict], lim: dict) -> str:
    t = {**T[lang], **T_LIVE[lang], **T_UI[lang]}
    if len(LIMIT_LABELS[lang]) != len(lim):
        raise SystemExit("LIMIT_LABELS" + lang + " does not name every limit")
    intro, texts = sections(lang)
    langs = "".join(
        f'<strong aria-current="page">{CODES[other]}</strong>' if other == lang
        else f'<a href="index{other}.html" hreflang="{T[other]["lang"]}" title="{NAMES[other]}">{CODES[other]}</a>'
        for other in LANGS)
    alternates = "".join(f'<link rel="alternate" hreflang="{T[other]["lang"]}" href="index{other}.html">'
                         for other in LANGS)
    tiles, body = [], []
    for card in cards:
        slug = card["slug"]
        offline = not card["egress_hosts"] and not card["egress_input_fields"]
        net = t["none"] if offline else (
            t["reaches"] + " " + ", ".join(f"<code>{h}</code>" for h in card["egress_hosts"])
            + ((" " + t["named"] + " " + ", ".join(f"<code>{f}</code>" for f in card["egress_input_fields"]))
               if card["egress_input_fields"] else ""))
        amount = f"{card['price_per_call_usd']:.3f}"
        price = t["free"] if not card["price_per_call_usd"] else (
            amount.replace(".", ",") + " $" if lang == ".fr" else "$" + amount)
        price_tag = f'<span class="tag {"free" if not card["price_per_call_usd"] else "paid"}">{price}</span>'
        reach = card["egress_hosts"] + [t["caller_host"] for _ in card["egress_input_fields"][:1]]
        reach_tag = html.escape(t["offline"] if offline else reach[0] + (f" +{len(reach) - 1}" if len(reach) > 1 else ""))
        net_tag = f'<span class="tag" title="{html.escape(", ".join(reach))}">{reach_tag}</span>'
        lang_tag = f'<span class="tag">{"JavaScript" if card["language"] == "javascript" else "Python"}</span>'
        text = texts.get(slug, card["description"])
        tiles.append(f'<a class="tile" href="#{slug}"><span class="tile-top"><span class="slug">{slug}</span>'
                     f'<span class="chip" data-live="{slug}">{t["live_wait"]}</span></span>'
                     f'<code class="cap">{card["capability_id"]}</code><span class="blurb">{blurb(text)}</span>'
                     f'<span class="tags">{price_tag}{net_tag}{lang_tag}</span></a>')
        runtime = lim["javascript"] if card["language"] == "javascript" else lim["python"]
        tests = ", ".join(f'<a href="{x["file"]}"><code>{x["file"]}</code></a> ({x["tests"]})'
                          for x in card["tests"]) or "—"
        data = ", ".join(f'<a href="{d}"><code>{d}</code></a>' for d in card["data"]) or "—"
        body.append(f"""<section class="agent" id="{slug}" data-agent="{slug}" data-sha="{card['handler_sha256']}">
<header class="agent-head"><div><h3>{slug}</h3><code>{card['capability_id']}</code></div>
<div class="tags">{price_tag}{lang_tag}<span class="chip" data-live="{slug}">{t['live_wait']}</span></div></header>
{markdown(text)}
<dl class="facts">
<dt>{t['network']}</dt><dd>{net}</dd>
<dt>{t['sandbox']}</dt><dd>{html.escape(t['sandbox_text'].format(runtime=runtime, timeout=lim['timeout_s'],
    memory=lim['memory_mb'], rounds=lim['max_requests_per_call'], kib=lim['max_response_kib']))}</dd>
<dt>{t['code']}</dt><dd>{html.escape(t['code_text'].format(bytes=card['handler_bytes'], sha=card['handler_sha256']))}
 <a href="{card['source_file']}">{t['source']}</a></dd>
<dt>{t['now']}</dt><dd data-live="{slug}" data-kind="line">{t['live_wait']}</dd>
<dt>{t['signature']}</dt><dd>{html.escape(t['sig_text'])}</dd>
<dt>{t['tests']}</dt><dd>{tests}</dd>
<dt>{t['data']}</dt><dd>{data}</dd>
<dt>{t['price']}</dt><dd>{price}</dd>
</dl>
<details><summary>{t['schema']}</summary><pre><code>{html.escape(json.dumps(card['input_schema'], indent=1,
    ensure_ascii=False))}</code></pre></details>
</section>""")
    how = t["how_text"].format(hub="https://modelmarket.dev", hearth=HEARTH)
    how_html = re.sub(r"POST (https://(?:&[a-z]+;|[^\s;,，；&])+)", r"<code>POST \1</code>",
                      html.escape(how, quote=False))
    limit_tiles = "".join(
        f'<div class="limit"><div class="v{" word" if isinstance(value, str) else ""}">{html.escape(_num(value))}</div>'
        f'<div class="k">{label}</div></div>'
        for label, value in zip(LIMIT_LABELS[lang], lim.values()))  # noqa: B905 — lengths checked above
    example = cards[-1]
    check = (f"curl -s {HEARTH}/v1/hearth \\\n  | jq -r '.tenants[] | select(.slug == \"{example['slug']}\") "
             f"| .handler_sha256'\ncurl -s {HEARTH}/agents/{example['source_file']} | sha256sum")
    live_text = {k: v for k, v in t.items() if k.startswith(("live_", "owner_"))}
    live_json = json.dumps(live_text, ensure_ascii=False).replace("<", "\\u003c")
    free = sum(1 for c in cards if not c["price_per_call_usd"])
    offline = sum(1 for c in cards if not c["egress_hosts"] and not c["egress_input_fields"])
    return f"""<!doctype html>
<html lang="{t['lang']}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{t['title']}</title><meta name="theme-color" content="#140c08">
<meta name="description" content="{html.escape(t['foot_about'])}">
<link rel="canonical" href="{HEARTH}/agents/index{lang}.html">{alternates}
<link href="/fonts/fonts.css" rel="stylesheet"><style>{CSS}</style></head><body>
<div class="nebula" aria-hidden="true"></div><div class="grain" aria-hidden="true"></div>
<div class="vignette" aria-hidden="true"></div>
<nav><div class="wrap row"><a class="brand" href="/"><span class="pip" aria-hidden="true"></span>HESTIA
<small>{t['kicker']}</small></a>
<div class="nav-links"><a href="/">{t['nav_hearth']}</a><a href="#agents">{t['nav_agents']}</a>
<a href="#verify">{t['nav_verify']}</a><a href="#limits">{t['nav_limits']}</a><a href="#others">{t['nav_others']}</a></div>
<div class="langs" role="navigation" aria-label="Language">{langs}</div></div></nav>
<main class="wrap">
<header class="hero"><div class="hero-grid"><div><p class="kicker">{t['kicker']} · {len(cards)}</p>
<h1>{t['h1']}</h1>
<div class="lead">{markdown(intro)}</div></div>
<aside class="proof" aria-label="handler_sha256"><div class="proof-in">
<div class="proof-top"><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span><span>handler_sha256</span></div>
<div class="p-slug">{example['slug']}<code>{example['capability_id']}</code></div>
<div class="p-row"><span class="p-k">{t['proof_pub']}</span>
<code class="p-v">{example['handler_sha256'][:16]}…{example['handler_sha256'][-8:]}</code></div>
<div class="p-eq" aria-hidden="true" data-live-eq="{example['slug']}">?</div>
<div class="p-row live"><span class="p-k">{t['proof_live']}</span><code class="p-v" data-live-sha="{example['slug']}">…</code></div>
<div class="p-verdict"><span class="chip" data-live="{example['slug']}">{t['live_wait']}</span></div>
</div></aside></div>
<p class="status" id="live-summary" role="status">{t['live_wait']}</p>
<div class="cta"><a class="btn btn-primary" href="catalog.json">catalog.json</a>
<a class="btn btn-ghost" href="SHA256SUMS">{t['sums']}</a><a class="btn btn-ghost" href="/v1/hearth">{t['roster']}</a>
<a class="btn btn-ghost" href="docs/AGENTS{lang}.md">{t['full_text']}</a></div>
<div class="metrics">
<div class="metric"><div class="v">{len(cards)}</div><div class="k">{t['m_agents']}</div></div>
<div class="metric"><div class="v">{free}</div><div class="k">{t['m_free']}</div></div>
<div class="metric"><div class="v">{offline}</div><div class="k">{t['m_offline']}</div></div>
<div class="metric"><div class="v" id="live-metric">…</div><div class="k">{t['m_live']}</div></div>
<div class="metric"><div class="v word">Ed25519</div><div class="k">{t['m_signed']}</div></div>
</div></header>
<section class="section" id="agents" aria-labelledby="agents-h"><p class="eyebrow">{len(cards)} · WebAssembly</p>
<h2 id="agents-h">{t['agents']}</h2><p class="lede">{t['lede_agents']}</p>
<div class="tiles">{''.join(tiles)}</div>
<div class="agents">{''.join(body)}</div></section>
<section class="section" id="verify" aria-labelledby="verify-h"><p class="eyebrow">handler_sha256</p>
<h2 id="verify-h">{t['verify']}</h2>
<div class="panel"><p>{html.escape(t['verify_text'])}</p>
<div class="cmd"><pre><code id="check-cmd">{html.escape(check)}</code></pre>
<button class="copy" type="button" data-copy="check-cmd">{t['live_copy']}</button></div>
<p class="note">{html.escape(t['verify_note'])}</p></div></section>
<section class="section" id="call" aria-labelledby="call-h"><p class="eyebrow">x402</p>
<h2 id="call-h">{t['how']}</h2><div class="panel"><p>{how_html}</p></div></section>
<section class="section" id="limits" aria-labelledby="limits-h"><p class="eyebrow">hestia/sandbox.py</p>
<h2 id="limits-h">{t['limits']}</h2><div class="limits">{limit_tiles}</div></section>
<section class="section" id="others" aria-labelledby="others-h"><p class="eyebrow">/v1/hearth</p>
<h2 id="others-h">{t['others']}</h2><p class="lede">{html.escape(t['others_text'])}</p>
<p class="muted" id="others-none">{t['others_none']}</p>
<div class="table" id="others-table" hidden><table><thead><tr><th>slug</th><th>id</th><th>{t['owner']}</th>
<th>handler_sha256</th></tr></thead><tbody id="others-body"></tbody></table></div></section>
</main>
<footer><div class="wrap"><div class="fgrid"><div><div class="fbrand"><span class="pip" aria-hidden="true"></span>HESTIA</div>
<p>{html.escape(t['foot_about'])}</p><p>{html.escape(t['license'])}</p></div>
<div><h5>{t['foot_links']}</h5><div class="flinks"><a href="/">{t['nav_hearth']}</a>
<a href="https://modelmarket.dev">modelmarket.dev</a><a href="catalog.json">catalog.json</a>
<a href="SHA256SUMS">SHA256SUMS</a><a href="/v1/hearth">/v1/hearth</a><a href="docs/AGENTS{lang}.md">{t['full_text']}</a></div></div></div>
<p class="fbot">{html.escape(t['data_note'])}</p></div></footer>
<script type="application/json" id="live-text">{live_json}</script>
<script src="live.js"></script>
</body></html>
"""


def build(out: Path) -> int:
    """Write the catalogue into ``out`` (replaced whole); return the number of agents."""
    if out.exists():
        shutil.rmtree(out)
    (out / "src").mkdir(parents=True)
    lim = limits()
    cards, published = [], []
    for slug, meta in AGENTS.items():
        source = handler_source(slug)
        raw = source.encode("utf-8")
        ext = "js" if language(slug) == "javascript" else "py"
        name = f"src/{slug}.{ext}"
        (out / name).write_bytes(raw)
        published.append(name)
        cards.append({
            "slug": slug, "capability_id": meta["capability_id"], "name": meta["name"],
            "description": meta["description"], "price_per_call_usd": meta["price_per_call_usd"],
            "language": language(slug), "sandbox_only": bool(meta.get("sandbox_only")),
            "egress_hosts": list(meta.get("egress_hosts") or []),
            "egress_input_fields": list(meta.get("egress_input_fields") or []),
            "input_schema": meta.get("input_schema", {"type": "object"}),
            "handler_sha256": hashlib.sha256(raw).hexdigest(), "handler_bytes": len(raw), "source_file": name,
            "tests": tests_for(slug), "data": data_for(slug),
        })
    copies = sorted({x["file"] for c in cards for x in c["tests"]} | {d for c in cards for d in c["data"]}
                    | set(SUPPORT) | {f"docs/AGENTS{lang}.md" for lang in LANGS})
    removed = {}
    for name in copies:
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / name).read_bytes()
        if name.startswith("tests/") and name.endswith(".json"):
            raw, counts = redacted(raw)
            if counts:
                removed[name] = counts
        (out / name).write_bytes(raw)
    published += copies
    sums = [f"{hashlib.sha256((out / name).read_bytes()).hexdigest()}  {name}" for name in sorted(published)]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    (out / "catalog.json").write_text(json.dumps(
        {"hearth": HEARTH, "roster": HEARTH + "/v1/hearth", "limits": lim, "agents": cards,
         "removed_from_recorded_data": removed},
        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "live.js").write_text(LIVE_JS, encoding="utf-8")
    for lang in LANGS:
        (out / f"index{lang}.html").write_text(page(lang, cards, lim), encoding="utf-8")
    return len(cards)


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else OUT
    print(f"wrote {build(out)} agents into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
