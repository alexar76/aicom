from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW


def test_pipeline_flow_contains_design_and_hardening_stages():
    assert PIPELINE_AGENT_FLOW["ARCH_DESIGNED"] == ("design_critic", "DESIGN_CRITIQUED")
    assert PIPELINE_AGENT_FLOW["DESIGN_CRITIQUED"] == ("developer", "CODE_COMMITTED")
    assert PIPELINE_AGENT_FLOW["CODE_COMMITTED"] == ("__runtime_test__", "CODE_TESTING")
    assert PIPELINE_AGENT_FLOW["CODE_TESTING"] == ("hardening", "DEV_FIXING")

