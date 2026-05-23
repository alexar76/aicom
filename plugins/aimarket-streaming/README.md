# aimarket-streaming

## Value in plain words

Streams long AI answers token by token and charges fairly for what you actually read — stop early, pay less. Better for chat UIs and long reports.

**Простыми словами:** Длинные ответы AI идут по токенам, платите за то, что реально получили — остановили раньше, заплатили меньше. Удобно для чата и длинных отчётов.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**SSE/WS streaming + per-chunk billing with micro-receipts.**
Capability streams tokens. Every N tokens → signed micro-receipt. Consumer can cancel mid-stream — pays only for what was received. Channel balance debited incrementally.

## When to Use
- LLM text generation (tokens streamed → billed per 10 tokens)
- Long-running AI tasks where consumer wants partial results
- Budget-sensitive consumers who want to cancel mid-stream
- Audit: every chunk has a signed receipt for compliance

## Installation
```bash
pip install aimarket-streaming
```

## Example
```python
from aimarket_hub.signing import Signer
from aimarket_streaming.streaming import StreamingBiller

signer = Signer()
biller = StreamingBiller(signer)

session = biller.open_session(
    capability_id="text.generate@v1", product_id="prod-gpt",
    channel_id="ch_abc123", price_per_token_usd=0.001,
    tokens_per_chunk=10
)

async def token_stream():
    for word in ["The", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog", ".", "..."]:
        yield word  # In production: yield actual LLM tokens

import asyncio
async def main():
    async for chunk in biller.stream_tokens(session, token_stream()):
        print(f"Chunk {chunk['chunk_receipt']['chunk_index']}: "
              f"${chunk['cumulative_price_usd']:.6f} "
              f"({chunk['cumulative_tokens']} tokens)")

asyncio.run(main())

# Cancel mid-stream — pays only for received
result = biller.cancel_session(session.session_id)
print(f"Cancelled. Total paid: ${result['total_price_usd']:.6f}")
```

## Per-Chunk Billing
- `price_per_token_usd`: 0.001 (0.1 cent per token)
- `tokens_per_chunk`: 10 (micro-receipt every 10 tokens)
- Each chunk receipt is Ed25519-signed — verifiable audit trail

## License
MIT · Maintained by AI-Factory
