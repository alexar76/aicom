# Run inside the image, no network: the rule's provider wins over the default; auto / unloaded -> default;
# the fallback is only a failover target.
import sys
sys.path.insert(0, '/app')
from llm.provider import ProviderStatus
from llm.router import LLMRouter

class H:
    def __init__(s): s.status = ProviderStatus.ONLINE; s.latency_ms = 1.0
class P:
    def __init__(s): s.health = H()

r = LLMRouter.__new__(LLMRouter)
r.default_provider = 'openrouter_api'
r.providers = {'openrouter_api': P(), 'deepseek_api': P(), 'groq_api': P()}
r.routing_rules = [
    {'task_type': 'architecture_design', 'preferred_provider': 'deepseek_api', 'fallback_provider': 'groq_api'},
    {'task_type': 'qa_testing', 'preferred_provider': 'auto', 'fallback_provider': 'groq_api'},
    {'task_type': 'code_generation', 'preferred_provider': 'local_ollama', 'fallback_provider': 'deepseek_api'},
]
got = {t: r._select_provider(t) for t in ('architecture_design', 'qa_testing', 'code_generation', 'marketing_copy')}
want = {'architecture_design': 'deepseek_api', 'qa_testing': 'openrouter_api', 'code_generation': 'openrouter_api', 'marketing_copy': 'openrouter_api'}
assert got == want, got
assert r._next_failover('architecture_design', 'deepseek_api', {'deepseek_api'}) == 'groq_api'
assert r._next_failover('architecture_design', 'groq_api', {'deepseek_api', 'groq_api'}) == 'openrouter_api'
print('ok', got)
