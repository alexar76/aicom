# aimarket-bridges 0.2.0 — AIMarket capabilities as LangChain/LangGraph, CrewAI, AutoGen and Agent Framework tools

Since 0.1.0 (July):

- **Free trial first, then a visible price.** Tools join the hub's free-trial model and say plainly when the next call costs money.
- **Receipts bound to the right key.** The signing-key fetch can no longer be steered by `source_hub`; receipt-binding tests run against a real hub signer and fail loudly when it is missing.
- **Microsoft Agent Framework** joins LangChain/LangGraph, CrewAI and AutoGen.
- **Honest packaging.** Published wheels state their real version, and the `mcp` ceiling no longer lets 2.x break imports.

```bash
pip install "aimarket-bridges[langgraph]"
```
