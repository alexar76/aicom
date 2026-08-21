#!/usr/bin/env python3
"""Patch developer-guides.json with community supply-security fields (all 20 langs)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "argus" / "docs" / "i18n" / "developer-guides.json"

FOOTER_SUPPLY = (
    "- [Supply security (EN)](https://github.com/alexar76/aicom/blob/main/aimarket-hub/docs/supply-security.md)"
)

STAKE_CMD = (
    'curl -s -X POST "$HUB/ai-market/v2/supply/stake" \\\n'
    '  -H "Authorization: Bearer $AIMARKET_PUBLISH_TOKEN" \\\n'
    '  -H "Content-Type: application/json" \\\n'
    '  -d \'{"publisher_id":"0xYou","amount_usd":15,"tx_hash":"0x..."}\''
)

PATCHES: dict[str, dict[str, str]] = {
    "en": {
        "s1_body": (
            "Clone the hello example and start it:\n\n"
            "`cd aimarket-hub/examples/hello-capability && python3 server.py`\n\n"
            "It listens on `http://127.0.0.1:3456/invoke`, prints **`provider_pubkey`**, "
            "and signs each `result` with Ed25519 (`X-Provider-Signature` header)."
        ),
        "s2_body": (
            "Edit `capability.json`: `product_id`, `capability_id` (`tool@v1`), `invoke_url` "
            "(public HTTPS), `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`** "
            "(from server startup), and JSON schemas. Local dev: `export AIMARKET_ALLOW_LOCAL_PUBLISH=1`."
        ),
        "s2_sec_title": "2b · Stake & security (production)",
        "s2_sec_body": (
            "Production hubs gate community publish with **stake** (default ≥ $10 USDC bookkeeping), "
            "**rate limits**, **LUMEN trust** scoring, and **signed provider responses**. "
            "Deposit stake before your first publish:"
        ),
        "stake_cmd": STAKE_CMD,
        "s3_body": (
            "Install Hub CLI (`pip install -e aimarket-hub/`), set `AIMARKET_PUBLISH_TOKEN`, "
            "deposit stake on production hubs, then publish:"
        ),
        "s4_body": (
            "Verify search and invoke. Hub verifies `X-Provider-Signature` on provider responses. "
            "When crypto is enabled, buyers pay USDC per call; revenue flows to your listing."
        ),
        "s5_body": (
            "Agents with wallet enabled run `argus economy discover` and `argus economy invoke`. "
            "ARGUS filters listings below `ARGUS_MIN_HUB_TRUST` (default 0.25). "
            "Write a clear description with keywords your capability solves."
        ),
    },
    "ru": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Сервер печатает `provider_pubkey` и подписывает ответы (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake и безопасность (prod)",
        "s2_sec_body": "На production: **stake** (≥ $10), лимиты публикаций, **LUMEN trust**, подпись ответов Ed25519. Сначала депозит stake:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "`pip install -e aimarket-hub/`, `AIMARKET_PUBLISH_TOKEN`, stake (prod), затем publish:",
        "s4_body": "`aimarket search` + invoke. Hub проверяет подпись провайдера. Покупатель платит USDC за вызов.",
        "s5_body": "`argus economy discover/invoke`. ARGUS отсекает caps с trust ниже `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "zh": {
        "s1_body": "`hello-capability` — `python3 server.py` → 3456。启动时输出 `provider_pubkey`，响应带 `X-Provider-Signature`。",
        "s2_body": "`capability.json`：`product_id`、`capability_id@v1`、`invoke_url`、`price_per_call_usd`、**`publisher_id`**、**`provider_pubkey`**、schemas。",
        "s2_sec_title": "2b · 质押与安全（生产）",
        "s2_sec_body": "生产环境需 **stake**（默认 ≥$10）、发布限速、**LUMEN 信任分**、Ed25519 签名响应。先质押：",
        "stake_cmd": STAKE_CMD,
        "s3_body": "安装 CLI，设置 `AIMARKET_PUBLISH_TOKEN`，生产环境先 stake，再 publish。",
        "s5_body": "ARGUS 按 `ARGUS_MIN_HUB_TRUST`（默认 0.25）过滤低信任 listing。",
    },
    "es": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Imprime `provider_pubkey` y firma respuestas (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake y seguridad (prod)",
        "s2_sec_body": "En producción: **stake** (≥ $10), límites de publicación, confianza **LUMEN**, respuestas firmadas Ed25519. Deposita stake primero:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "`pip install -e aimarket-hub/`, token, stake (prod), luego publish.",
        "s5_body": "ARGUS filtra listings bajo `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "hi": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. `provider_pubkey` प्रिंट करता है; `X-Provider-Signature` हेडर।",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake और सुरक्षा (prod)",
        "s2_sec_body": "Production: **stake** (≥ $10), rate limits, **LUMEN trust**, Ed25519 signed responses. पहले stake जमा करें:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI install, token, prod पर stake, फिर publish.",
        "s5_body": "ARGUS `ARGUS_MIN_HUB_TRUST` (0.25) से नीचे की listings हटाता है।",
    },
    "ar": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. يطبع `provider_pubkey` ويوقّع الردود (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · الضمان والأمان (prod)",
        "s2_sec_body": "في الإنتاج: **stake** (≥ $10)، حدود النشر، ثقة **LUMEN**، توقيع Ed25519. أودع stake أولاً:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "ثبّت CLI، عيّن token، stake في prod، ثم publish.",
        "s5_body": "ARGUS يصفّي القوائم دون `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "pt": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Imprime `provider_pubkey` e assina respostas (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake e segurança (prod)",
        "s2_sec_body": "Em produção: **stake** (≥ $10), limites de publicação, confiança **LUMEN**, respostas Ed25519. Deposite stake primeiro:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), depois publish.",
        "s5_body": "ARGUS filtra listings abaixo de `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "ja": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456。起動時に `provider_pubkey` を表示し、`X-Provider-Signature` で署名。",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · ステークとセキュリティ（本番）",
        "s2_sec_body": "本番: **stake**（≥$10）、公開レート制限、**LUMEN** 信頼、Ed25519 署名応答。先に stake:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI 導入、token、本番では stake 後に publish。",
        "s5_body": "ARGUS は `ARGUS_MIN_HUB_TRUST`（0.25）未満を除外。",
    },
    "fr": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Affiche `provider_pubkey` et signe les réponses (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake et sécurité (prod)",
        "s2_sec_body": "En prod : **stake** (≥ $10), limites de publication, confiance **LUMEN**, réponses Ed25519. Déposez le stake d'abord :",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), puis publish.",
        "s5_body": "ARGUS filtre sous `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "de": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Gibt `provider_pubkey` aus; signiert Antworten (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake & Sicherheit (Prod)",
        "s2_sec_body": "Prod: **Stake** (≥ $10), Publish-Limits, **LUMEN**-Trust, Ed25519-signierte Antworten. Zuerst Stake einzahlen:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, Token, Stake (Prod), dann publish.",
        "s5_body": "ARGUS filtert unter `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "ko": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. `provider_pubkey` 출력, `X-Provider-Signature` 서명.",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · 스테이크 및 보안 (prod)",
        "s2_sec_body": "프로덕션: **stake**(≥$10), 게시 제한, **LUMEN** 신뢰, Ed25519 서명 응답. 먼저 stake:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, prod에서 stake 후 publish.",
        "s5_body": "ARGUS는 `ARGUS_MIN_HUB_TRUST`(0.25) 미만을 필터링.",
    },
    "it": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Stampa `provider_pubkey` e firma le risposte (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake e sicurezza (prod)",
        "s2_sec_body": "In prod: **stake** (≥ $10), limiti publish, fiducia **LUMEN**, risposte Ed25519. Deposita stake prima:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), poi publish.",
        "s5_body": "ARGUS filtra sotto `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "tr": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. `provider_pubkey` yazdırır; `X-Provider-Signature` ile imzalar.",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake ve güvenlik (prod)",
        "s2_sec_body": "Prod: **stake** (≥ $10), yayın limiti, **LUMEN** güveni, Ed25519 imzalı yanıtlar. Önce stake:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, prod'da stake, sonra publish.",
        "s5_body": "ARGUS `ARGUS_MIN_HUB_TRUST` (0.25) altını filtreler.",
    },
    "id": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Mencetak `provider_pubkey`; menandatangani respons (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake & keamanan (prod)",
        "s2_sec_body": "Prod: **stake** (≥ $10), batas publish, kepercayaan **LUMEN**, respons Ed25519. Setor stake dulu:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), lalu publish.",
        "s5_body": "ARGUS menyaring di bawah `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "vi": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. In `provider_pubkey`; ký phản hồi (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake & bảo mật (prod)",
        "s2_sec_body": "Prod: **stake** (≥ $10), giới hạn publish, tin cậy **LUMEN**, phản hồi Ed25519. Nạp stake trước:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), rồi publish.",
        "s5_body": "ARGUS lọc dưới `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "th": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. แสดง `provider_pubkey`; ลงนาม `X-Provider-Signature`.",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake และความปลอดภัย (prod)",
        "s2_sec_body": "Prod: **stake** (≥ $10), จำกัดการเผยแพร่, **LUMEN** trust, ลายเซ็น Ed25519. ฝาก stake ก่อน:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), แล้ว publish.",
        "s5_body": "ARGUS กรองต่ำกว่า `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "hr": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Ispisuje `provider_pubkey`; potpisuje odgovore (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake i sigurnost (prod)",
        "s2_sec_body": "Prod: **stake** (≥ $10), limiti objave, **LUMEN** trust, Ed25519 potpisani odgovori. Prvo stake:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), zatim publish.",
        "s5_body": "ARGUS filtrira ispod `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "sk": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Vypíše `provider_pubkey`; podpisuje odpovede (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake a bezpečnosť (prod)",
        "s2_sec_body": "Prod: **stake** (≥ $10), limity publikácie, **LUMEN** trust, Ed25519 podpisy. Najprv stake:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), potom publish.",
        "s5_body": "ARGUS filtruje pod `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "nl": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. Toont `provider_pubkey`; tekent antwoorden (`X-Provider-Signature`).",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · Stake & beveiliging (prod)",
        "s2_sec_body": "Prod: **stake** (≥ $10), publish-limieten, **LUMEN**-trust, Ed25519-antwoorden. Eerst stake storten:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI, token, stake (prod), dan publish.",
        "s5_body": "ARGUS filtert onder `ARGUS_MIN_HUB_TRUST` (0.25).",
    },
    "fa": {
        "s1_body": "`hello-capability` — `python3 server.py` → :3456. `provider_pubkey` را چاپ می‌کند؛ `X-Provider-Signature` امضا می‌زند.",
        "s2_body": "`capability.json`: `product_id`, `capability_id@v1`, `invoke_url`, `price_per_call_usd`, **`publisher_id`**, **`provider_pubkey`**, schemas.",
        "s2_sec_title": "2b · سهام‌گذاری و امنیت (prod)",
        "s2_sec_body": "Prod: **stake** (≥ $10)، محدودیت انتشار، اعتماد **LUMEN**، پاسخ‌های Ed25519. ابتدا stake:",
        "stake_cmd": STAKE_CMD,
        "s3_body": "CLI، token، stake در prod، سپس publish.",
        "s5_body": "ARGUS زیر `ARGUS_MIN_HUB_TRUST` (0.25) را فیلتر می‌کند.",
    },
}


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    for lang, patch in PATCHES.items():
        if lang not in data:
            continue
        data[lang].update(patch)
        footer = data[lang].get("footer", "")
        if FOOTER_SUPPLY not in footer:
            data[lang]["footer"] = footer.rstrip() + "\n" + FOOTER_SUPPLY
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"patched {PATH.relative_to(ROOT)} ({len(PATCHES)} langs)")


if __name__ == "__main__":
    main()
