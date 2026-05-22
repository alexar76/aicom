# aimarket-personas

**Auto-generated AI agent personas for every capability.**
Instead of "capability prod-83a7b", discovery returns "Hi, I'm Lyra. I do legal translation. 412 tasks, 96% success, $0.40 avg." Makes the marketplace chat-native. Claude/GPT recommend "try Lyra", not "try product-7d8f...".

## When to Use
- Chat-native AI discovery (Claude, GPT, Gemini recommending capabilities)
- Human-readable marketplace storefront
- Building agent directories and catalogs
- Marketing pages for AI products

## Installation
```bash
pip install aimarket-personas
```

## Example
```python
from aimarket_personas.agent_personas import PersonaGenerator

gen = PersonaGenerator(seed=42)
lyra = gen.generate("translate.multi@v2", "prod-001",
    description="Translate text to multiple locales",
    stats={"total_invocations": 412, "success_rate": 0.96, "avg_price_usd": 0.40})

print(lyra.introduce())
# "Hi, I'm Lyra. I do Multilingual Translator. Tried me on 412 tasks, 96% success rate, $0.40 avg."

print(lyra.discovery_entry())
# {"persona": {"name": "Lyra", "role": "Multilingual Translator", ...}, "capability_id": "translate.multi@v2"}
```

## Generated Personas Include
- **Name** (Lyra, Nova, Atlas, Kai, Rune, Sage, Echo...)
- **Role** (auto-inferred from capability keywords)
- **Tone** (professional, friendly, precise, creative, analytical, warm)
- **Specialty** (one-liner describing what makes this persona unique)
- **CV blurb** (invocation count + success rate + price)
- **Avatar emoji** (consistent per name)
- **Voice ID** (for future TTS integration)

## License
MIT · Maintained by AI-Factory
