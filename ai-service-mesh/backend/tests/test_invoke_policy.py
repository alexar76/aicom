from ai_service_mesh.invoke import response_is_demo_marked


def test_detects_demo_marker():
    assert response_is_demo_marked(
        {"result": {"output": "[DEMO] Executed translate@v2"}},
        "invoke_ok",
    )


def test_accepts_real_output():
    assert not response_is_demo_marked(
        {"result": {"output": "executed:research trends"}},
        "invoke_ok",
    )
