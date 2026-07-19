"""ACEX monorepo documentation and layout smoke tests."""

from __future__ import annotations

from pathlib import Path

ACEX = Path(__file__).resolve().parents[1] / "acex"


def test_acex_readme_and_protocol_exist():
    assert (ACEX / "README.md").is_file()
    assert (ACEX / "protocol" / "spec-capital-markets.md").is_file()
    assert (ACEX / "docs" / "security" / "audit-2026-05.md").is_file()


def test_evm_contract_sources_present():
    src = ACEX / "contracts" / "evm" / "src"
    for name in (
        "AgentListingRegistry.sol",
        "AgentCollateralVault.sol",
        "AgentShareToken.sol",
        "AgentNoteToken.sol",
        "AgentLendingPool.sol",
        "PulseAMM.sol",
    ):
        assert (src / name).is_file(), name


def test_solana_program_present():
    assert (ACEX / "contracts" / "solana" / "programs" / "acex-capital" / "src" / "lib.rs").is_file()


def test_deploy_scripts_executable_docs():
    assert (ACEX / "contracts" / "evm" / "deploy.sh").is_file()
    assert (ACEX / "contracts" / "solana" / "deploy.sh").is_file()


def test_phase2_integrations_present():
    assert (ACEX / "integrations" / "pricing.py").is_file()
    assert (ACEX / "integrations" / "jupiter.py").is_file()
    assert (ACEX / "docs" / "jupiter-routing.md").is_file()
    lib = (ACEX / "contracts" / "solana" / "programs" / "acex-capital" / "src" / "lib.rs").read_text()
    assert "CapsenseSeries" in lib
