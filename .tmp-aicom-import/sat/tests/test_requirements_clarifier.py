import pytest

from web.backend.services.requirements_clarifier import build_clarification_pack, build_clarification_pack_llm


def test_build_clarification_pack_has_questions():
    pack = build_clarification_pack("AI CRM for enterprise sales teams with API sync")
    assert isinstance(pack, dict)
    assert len(pack.get("questions", [])) >= 5
    assert len(pack.get("assumptions_to_validate", [])) >= 3


class _FakeRouter:
    async def generate(self, prompt: str, task_type: str = "pm_analysis"):
        return (
            '{"summary":"LLM summary","assumptions_to_validate":["a","b","c"],'
            '"questions":["q1","q2","q3","q4","q5"],'
            '"acceptance_probes":["p1","p2","p3"]}'
        )


@pytest.mark.asyncio
async def test_build_clarification_pack_llm_path():
    pack = await build_clarification_pack_llm("Create AI CRM", _FakeRouter())
    assert pack["summary"] == "LLM summary"
    assert len(pack["questions"]) >= 5
