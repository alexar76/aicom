from pathlib import Path

from orchestrator.director_integration import DirectorIntegration


class _StateMachine:
    pass


class _TimeoutManager:
    def __init__(self):
        self.calls = []

    def set_agent_timeout(self, agent, timeout):
        self.calls.append((agent, timeout))


def test_apply_timeout_decision(tmp_path: Path):
    tm = _TimeoutManager()
    di = DirectorIntegration(_StateMachine(), tm, decisions_path=str(tmp_path / "decisions.json"))
    ok = di.apply_decision(
        {
            "id": "d1",
            "action": "increase_agent_timeout",
            "target": "developer",
            "new_value": 55,
            "requires_approval": False,
        }
    )
    assert ok is True
    assert ("developer", 55) in tm.calls
    assert any(d.get("id") == "d1" for d in di.get_recent_decisions())


def test_approve_pending_decision(tmp_path: Path):
    tm = _TimeoutManager()
    di = DirectorIntegration(_StateMachine(), tm, decisions_path=str(tmp_path / "decisions.json"))
    di.apply_decision(
        {
            "id": "d2",
            "action": "increase_agent_timeout",
            "target": "qa",
            "new_value": 40,
            "requires_approval": True,
        }
    )
    assert len(di.get_pending_decisions()) == 1
    assert di.approve_decision("d2") is True
    assert len(di.get_pending_decisions()) == 0


def test_director_integration_uses_sqlite_storage(tmp_path: Path):
    tm = _TimeoutManager()
    decisions_json = tmp_path / "decisions.json"
    di = DirectorIntegration(_StateMachine(), tm, decisions_path=str(decisions_json))
    assert di.apply_decision(
        {
            "id": "d3",
            "action": "increase_agent_timeout",
            "target": "architect",
            "new_value": 37,
            "requires_approval": False,
        }
    )
    assert (tmp_path / "decisions.db").exists()
