"""Default diagnostic representations must not reveal funding credentials."""
from aimarket_hub.config import HubConfig
from aimarket_hub.subcontract import JobContext


def test_configuration_hides_database_and_federation_credentials():
    config = HubConfig(database_url="postgresql://user:repr-only-secret@localhost/db",
                       peer_api_keys={"https://peer.test": "repr-only-peer-token"},
                       federation_judge_key="repr-only-judge-token")
    printed = repr(config)
    assert "repr-only-secret" not in printed
    assert "repr-only-peer-token" not in printed
    assert "repr-only-judge-token" not in printed


def test_subcontract_context_hides_money_grant():
    context = JobContext(job_id="test-job", node="node", depth=0, max_depth=2, path=[],
                         grant_secret="repr-only-grant", grant={"private": "repr-only-row"})
    assert "repr-only-grant" not in repr(context)
    assert "repr-only-row" not in repr(context)
