from web.backend.services.product_naming import resolve_product_name


def test_resolve_name_replaces_placeholder_and_marks_template():
    used = set()
    name, is_template = resolve_product_name(
        product_id="prod-ebb",
        product={"idea": "AI landing template for fintech startups"},
        spec={"product_name": "Product prod-ebb"},
        marketing={},
        used_names=used,
    )
    assert is_template is True
    assert name.startswith("Template: ")
    assert "prod-ebb" not in name.lower()


def test_resolve_name_adds_suffix_on_collision():
    used = {"velocity-crm"}
    name, _ = resolve_product_name(
        product_id="prod-1234",
        product={"idea": "CRM assistant for sales teams"},
        spec={"product_name": "Velocity CRM"},
        marketing={},
        used_names=used,
    )
    assert name.startswith("Velocity CRM")
    assert name != "Velocity CRM"
