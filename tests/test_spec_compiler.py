from web.backend.services.spec_compiler import compile_product_brief


def test_spec_compiler_extracts_structure():
    out = compile_product_brief(
        "Build fintech dashboard for product managers",
        "production mode with security and accessibility focus",
    )
    assert out["domain"] in {"fintech", "general"}
    assert "constraints" in out
    assert isinstance(out["primary_outcomes"], list)
