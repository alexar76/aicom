"""Tests for the enforceable charter blocks and the two gates that enforce them.

The uniformity tests are the important ones. The first version of
``property_contract_gate`` reported a sampler doing ``byte % 12`` as uniform, because
``chi2=19.17`` did not exceed the ``31.43`` critical value at ``n=24000`` — a real bias the
test lacked the power to see. A fairness gate answering "probably fine" when it means "I
could not tell" is worse than no gate, so ``test_underpowered_run_is_not_a_pass`` exists to
keep that behaviour from coming back.
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

import pytest

from core.charter_contracts import (
    charter_contract_report,
    executable_properties,
    pinned_dependencies,
)
from web.backend.services.pinned_dependency_gate import check_pinned_dependencies
from web.backend.services.property_contract_gate import (
    UNIFORM_POWER,
    chi2_upper,
    judge_uniform,
    modulo_bias_w,
    noncentrality_for_power,
    run_properties,
)

# --------------------------------------------------------------------------- charter parsing


CHARTER = textwrap.dedent(
    """
    Engineering charter — verifiable sampling desk.

    ====== pinned dependency ======
    module: sortes.vrf
    symbols: prove, verify, proof_to_hash
    requires: aimarket-oracle-core
    why: RFC 9381 ECVRF, byte-exact against the Appendix B.3 vectors. A reimplementation
         produces proofs that verify anything.

    ====== executable property ======
    name: the selection depends on the randomness
    kind: sensitive
    target: app.sampling:good
    vary: alpha
    args: {"roster_digest": "a3f1", "alpha": "seed", "k": 1, "population": 12}

    ====== operator requirement — pricing ======
    Free tier is five calls per caller per hour.
    """
)


def test_pinned_block_is_parsed_with_a_folded_continuation():
    pins = pinned_dependencies(CHARTER)
    assert len(pins) == 1
    pin = pins[0]
    assert pin["module"] == "sortes.vrf"
    assert pin["symbols"] == ["prove", "verify", "proof_to_hash"]
    # The indented second line of `why:` must fold into the value, not start a new key.
    assert pin["why"].endswith("verify anything.")
    # `requires` was absent from the parsed entry for a while, which silently disabled the
    # gate's `pinned_dependency_undeclared` check — the gate's own tests hand-built their pin
    # dicts and supplied it themselves, so the parser was never exercised on this field.
    assert pin["requires"] == "aimarket-oracle-core"
    assert "malformed" not in pin


def test_property_block_is_parsed_with_json_args():
    props = executable_properties(CHARTER)
    assert len(props) == 1
    prop = props[0]
    assert prop["kind"] == "sensitive"
    assert prop["target"] == "app.sampling:good"
    assert prop["vary"] == "alpha"
    assert prop["args"]["population"] == 12
    assert "malformed" not in prop


def test_operator_requirement_sections_are_left_alone():
    """charter_fidelity owns those; this parser must not claim them."""
    assert pinned_dependencies(CHARTER + "\n") == pinned_dependencies(CHARTER)
    assert len(executable_properties(CHARTER)) == 1


@pytest.mark.parametrize(
    "block,expected",
    [
        ("kind: sensitive\ntarget: a:b", "vary"),
        ("kind: uniform\ntarget: a:b\nvary: x", "buckets"),
        ("kind: roundtrip\ntarget: a:b", "inverse"),
        ("kind: nonsense\ntarget: a:b", "unknown kind"),
        ("kind: deterministic\ntarget: no_colon", "module.path:callable"),
        ("kind: deterministic", "missing required key: target"),
        ('kind: deterministic\ntarget: a:b\nargs: [1,2]', "JSON object"),
    ],
)
def test_malformed_properties_are_reported_not_dropped(block, expected):
    """A mistyped property must never read as a satisfied one."""
    charter = f"====== executable property ======\n{block}\n"
    props = executable_properties(charter)
    assert len(props) == 1, "the block must still be returned so it can be reported"
    assert expected in props[0]["malformed"]
    report = charter_contract_report(charter)
    assert report["executable_properties"] == []
    assert len(report["malformed"]) == 1
    assert report["declared"]["properties"] == 1


def test_sensitive_vary_must_name_a_declared_arg():
    charter = (
        "====== executable property ======\n"
        "kind: sensitive\ntarget: a:b\nvary: nope\nargs: {\"alpha\": 1}\n"
    )
    assert "nope" in executable_properties(charter)[0]["malformed"]


def test_no_blocks_is_not_an_error():
    report = charter_contract_report("Just prose, no marked blocks.")
    assert report["malformed"] == []
    assert report["declared"] == {"pinned": 0, "properties": 0}


# ------------------------------------------------------------------- pinned dependency gate


def _product(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


PIN = [{"module": "sortes.vrf", "symbols": ["prove", "verify"], "why": "RFC 9381",
        "requires": "aimarket-oracle-core"}]


def test_importing_the_pin_is_clean(tmp_path):
    code = _product(tmp_path, {
        "app/draw.py": """
            from sortes.vrf import prove, verify

            def draw(alpha):
                return prove(alpha)
        """,
        "requirements.txt": "fastapi\naimarket-oracle-core==0.3.0\n",
    })
    assert check_pinned_dependencies(code, PIN) == []


def test_a_local_reimplementation_is_critical(tmp_path):
    """The reflex this gate exists for: a well-formed local `prove` instead of the pinned one."""
    code = _product(tmp_path, {
        "app/crypto.py": """
            import hashlib

            def prove(alpha):
                return hashlib.sha256(alpha.encode()).hexdigest()

            def verify(pk, alpha, pi):
                return True
        """,
        "app/draw.py": """
            from app.crypto import prove, verify
        """,
        "requirements.txt": "fastapi\naimarket-oracle-core\n",
    })
    findings = check_pinned_dependencies(code, PIN)
    # The pinned module is imported nowhere, so the one actionable finding is that — not two
    # per-symbol findings repeating it.
    assert [f["code"] for f in findings] == ["pinned_dependency_unused"]
    assert "sortes.vrf" in findings[0]["detail"]
    assert "RFC 9381" in findings[0]["detail"]


def test_reimplementation_alongside_a_partial_import(tmp_path):
    code = _product(tmp_path, {
        "app/draw.py": """
            from sortes.vrf import prove

            def verify(pk, alpha, pi):
                return True
        """,
        "requirements.txt": "aimarket-oracle-core\n",
    })
    findings = check_pinned_dependencies(code, PIN)
    codes = [f["code"] for f in findings]
    assert "pinned_dependency_reimplemented" in codes
    detail = next(f for f in findings if f["code"] == "pinned_dependency_reimplemented")["detail"]
    assert "`verify`" in detail and "from sortes.vrf import verify" in detail


def test_a_same_named_wrapper_does_not_block(tmp_path):
    """A product may legitimately wrap a pinned call; charter_fidelity's rule is that a gate
    which cries wolf gets switched off.

    The severity has to come from the repair pipeline's own vocabulary. `core.repair_batches`
    maps an unknown severity to medium priority, so an invented word like "advisory" would turn
    an informational note into scheduled developer work — which is why `blocking` is a separate
    flag rather than a severity value.
    """
    code = _product(tmp_path, {
        "app/draw.py": """
            from sortes.vrf import prove, verify as _verify

            def verify(pk, alpha, pi):
                return _verify(pk, alpha, pi)
        """,
        "requirements.txt": "aimarket-oracle-core\n",
    })
    findings = check_pinned_dependencies(code, PIN)
    assert findings, "the shadow should still be reported"
    assert all(f["blocking"] is False for f in findings), findings
    assert all(f["severity"] in {"critical", "high", "medium", "low"} for f in findings), findings


def test_undeclared_distribution_is_critical(tmp_path):
    """Resolving in the build environment and not in the deployed one is the same defect,
    discovered later."""
    code = _product(tmp_path, {
        "app/draw.py": "from sortes.vrf import prove, verify\n",
        "requirements.txt": "fastapi\nuvicorn\n",
    })
    codes = [f["code"] for f in check_pinned_dependencies(code, PIN)]
    assert codes == ["pinned_dependency_undeclared"]


def test_nested_backend_requirements_are_found(tmp_path):
    code = _product(tmp_path, {
        "app/draw.py": "from sortes.vrf import prove, verify\n",
        "backend/requirements.txt": "aimarket-oracle-core\n",
    })
    assert check_pinned_dependencies(code, PIN) == []


def test_tests_and_frontend_are_not_accused(tmp_path):
    code = _product(tmp_path, {
        "app/draw.py": "from sortes.vrf import prove, verify\n",
        "tests/test_draw.py": "def prove(a):\n    return 'stub'\n",
        "frontend/src/shim.py": "def verify(*a):\n    return True\n",
        "requirements.txt": "aimarket-oracle-core\n",
    })
    assert check_pinned_dependencies(code, PIN) == []


def test_no_python_surface_is_not_this_gates_finding(tmp_path):
    code = _product(tmp_path, {"index.html": "<h1>landing</h1>"})
    assert check_pinned_dependencies(code, PIN) == []


# ----------------------------------------------------------------------- statistical sizing


def test_modulo_bias_w_is_zero_when_buckets_divide_the_draw_space():
    assert modulo_bias_w(16, 8) == 0.0
    assert modulo_bias_w(256, 8) == 0.0


def test_modulo_bias_w_matches_the_hand_computed_case():
    """256 = 21*12 + 4: four buckets get 22/256, eight get 21/256."""
    w = modulo_bias_w(12, 8)
    assert w == pytest.approx(0.0221, abs=5e-4)


def test_bigger_draws_shrink_the_bias():
    assert modulo_bias_w(12, 32) < modulo_bias_w(12, 16) < modulo_bias_w(12, 8)


def test_noncentrality_rises_with_power():
    crit = chi2_upper(0.001, 11)
    assert noncentrality_for_power(crit, 11, 0.50) < noncentrality_for_power(crit, 11, 0.95)


def test_chi2_upper_is_close_to_the_published_table():
    # chi2(0.001, df=11) = 31.264 in the standard table; Wilson-Hilferty is an approximation,
    # so a couple of percent is expected and anything worse means the formula drifted.
    assert chi2_upper(0.001, 11) == pytest.approx(31.264, rel=0.02)
    assert chi2_upper(0.05, 10) == pytest.approx(18.307, rel=0.02)


def test_a_significant_chi2_fails():
    verdict = judge_uniform({"chi2": 99.0, "df": 11, "n": 100_000, "buckets": 12, "alpha": 0.001})
    assert verdict["ok"] is False
    assert verdict["reason"] == "distribution is not uniform"


def test_underpowered_run_is_not_a_pass():
    """THE regression. These are the real numbers from the run that fooled the first version:
    `byte % 12` gave chi2=19.17 against a critical value of 31.43 at n=24000, and it passed."""
    verdict = judge_uniform({"chi2": 19.17, "df": 11, "n": 24_000, "buckets": 12, "alpha": 0.001})
    assert verdict["ok"] is False
    assert verdict["reason"] == "uniformity test is underpowered"
    assert "raise trials" in verdict["detail"]


def test_a_powered_clean_run_passes():
    verdict = judge_uniform({"chi2": 15.8, "df": 11, "n": 200_000, "buckets": 12, "alpha": 0.001})
    assert verdict["ok"] is True
    assert "powered to detect" in verdict["detail"]


def test_low_df_declines_to_judge_rather_than_judging_badly():
    verdict = judge_uniform({"chi2": 3.0, "df": 4, "n": 10, "buckets": 5, "alpha": 0.001})
    assert verdict["ok"] is True
    assert "not judged" in verdict["detail"]


def test_exact_bucket_count_needs_an_explicit_target():
    """With buckets dividing 256 there is no canonical bias, so the gate must say so instead
    of inventing an effect size."""
    verdict = judge_uniform({"chi2": 5.0, "df": 15, "n": 1000, "buckets": 16, "alpha": 0.001})
    assert verdict["ok"] is True
    assert "detect: <w>" in verdict["detail"]


def test_an_explicit_detect_target_overrides_the_default():
    m = {"chi2": 5.0, "df": 15, "n": 1000, "buckets": 16, "alpha": 0.001}
    verdict = judge_uniform(m, detect=0.30)
    assert verdict["ok"] is True, "a large effect is detectable at small n"
    assert judge_uniform(m, detect=0.001)["ok"] is False, "a tiny effect needs far more n"


def test_uniform_power_default_is_stricter_than_the_textbook():
    assert UNIFORM_POWER > 0.80


# ------------------------------------------------------------------- executing the properties


SAMPLERS = '''
import hashlib, random


def _stream(alpha, n):
    out, ctr = b"", 0
    while len(out) < n:
        out += hashlib.sha512(f"{alpha}:{ctr}".encode()).digest()
        ctr += 1
    return out[:n]


def good(roster_digest, alpha, k, population):
    """Rejection sampling: no modulo bias, no replacement."""
    stream, i, picked = _stream(alpha, 4096), 0, []
    remaining = list(range(population))
    while len(picked) < k and i + 4 <= len(stream):
        val = int.from_bytes(stream[i:i + 4], "big"); i += 4
        m = len(remaining)
        limit = (2 ** 32 // m) * m
        if val >= limit:
            continue
        picked.append(remaining.pop(val % m))
    return picked


def vacuous(roster_digest, alpha, k, population):
    """The platon defect: the output ignores the randomness entirely."""
    return list(range(k))


def nondeterministic(roster_digest, alpha, k, population):
    return random.sample(range(population), k)


def with_duplicates(roster_digest, alpha, k, population):
    return [0] * k


def boom(roster_digest, alpha, k, population):
    raise RuntimeError("needs a database")
'''

ARGS = {"roster_digest": "a3f1", "alpha": "seed", "k": 3, "population": 12}


@pytest.fixture()
def sampler_product(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "sampling.py").write_text(SAMPLERS, encoding="utf-8")
    return tmp_path


def _one(code_dir, prop):
    out = run_properties(code_dir, [prop], timeout_sec=180)
    assert not out.get("error"), out
    return out["properties"][0]["result"]


def test_deterministic_catches_an_unseeded_random(sampler_product):
    assert _one(sampler_product, {
        "name": "d", "kind": "deterministic", "trials": 8,
        "target": "app.sampling:nondeterministic", "args": ARGS,
    })["ok"] is False
    assert _one(sampler_product, {
        "name": "d", "kind": "deterministic", "trials": 8,
        "target": "app.sampling:good", "args": ARGS,
    })["ok"] is True


def test_sensitive_catches_the_vacuous_proof_shape(sampler_product):
    """The generalisation of the platon bug: the output does not depend on what it claims to."""
    bad = _one(sampler_product, {
        "name": "s", "kind": "sensitive", "vary": "alpha", "trials": 24,
        "target": "app.sampling:vacuous", "args": ARGS,
    })
    assert bad["ok"] is False
    assert "does not depend on alpha" in bad["reason"]
    assert _one(sampler_product, {
        "name": "s", "kind": "sensitive", "vary": "alpha", "trials": 24,
        "target": "app.sampling:good", "args": ARGS,
    })["ok"] is True


def test_distinct_catches_a_draw_that_repeats_itself(sampler_product):
    bad = _one(sampler_product, {
        "name": "x", "kind": "distinct", "trials": 4,
        "target": "app.sampling:with_duplicates", "args": ARGS,
    })
    assert bad["ok"] is False
    assert "duplicate" in bad["reason"]
    assert _one(sampler_product, {
        "name": "x", "kind": "distinct", "trials": 4,
        "target": "app.sampling:good", "args": ARGS,
    })["ok"] is True


def test_a_target_that_raises_is_reported_not_swallowed(sampler_product):
    result = _one(sampler_product, {
        "name": "b", "kind": "deterministic", "trials": 2,
        "target": "app.sampling:boom", "args": ARGS,
    })
    assert result["ok"] is False
    assert "RuntimeError" in result["reason"]


def test_a_missing_target_is_reported(sampler_product):
    result = _one(sampler_product, {
        "name": "m", "kind": "deterministic", "trials": 2,
        "target": "app.sampling:nope", "args": ARGS,
    })
    assert result["ok"] is False
    assert "AttributeError" in result["reason"] or "raised" in result["reason"]


def test_uniform_rejects_a_sampler_that_cannot_reach_every_bucket(sampler_product):
    result = _one(sampler_product, {
        "name": "u", "kind": "uniform", "vary": "alpha", "buckets": 12,
        "trials": 500, "alpha": 0.001,
        "target": "app.sampling:vacuous",
        "args": {**ARGS, "k": 1},
    })
    assert result["ok"] is False
    assert "does not match the declared" in result["reason"]


def test_the_gate_does_not_run_without_a_code_directory(tmp_path):
    out = run_properties(tmp_path / "missing", [{"kind": "deterministic", "target": "a:b"}])
    assert out["skipped"] is True


def test_prose_after_a_block_does_not_contaminate_the_last_field():
    """A section runs to the next `======` marker, so the paragraph an operator writes under a
    block used to be appended to its last value — the real charter's `uniform` property came
    back malformed with `args is not valid JSON (Extra data: line 1 column 74)`, because the
    sentence explaining the trial count had been folded into the JSON. Indented lines continue a
    value; unindented prose ends the field list."""
    charter = textwrap.dedent(
        """
        ====== executable property ======
        name: every seat is equally likely
        kind: uniform
        target: app.sampling:select
        vary: alpha
        buckets: 50
        trials: 20000
        alpha: 0.001
        args: {"roster_digest": "a3f1c2", "alpha": "hex:00", "k": 1, "population": 50}

        Note on that last property: 20000 trials is chosen, not guessed. Single-byte modulo bias
        over 50 buckets is Cohen's w = 0.0635, and detecting it needs 16902 observations.
        """
    )
    props = executable_properties(charter)
    assert len(props) == 1
    prop = props[0]
    assert "malformed" not in prop, prop.get("malformed")
    assert prop["args"] == {
        "roster_digest": "a3f1c2",
        "alpha": "hex:00",
        "k": 1,
        "population": 50,
    }
    assert prop["trials"] == 20000
    assert prop["buckets"] == 50


def test_indented_continuation_still_folds():
    """The other half of the same rule — the `why:` continuation must keep working."""
    charter = textwrap.dedent(
        """
        ====== pinned dependency ======
        module: sortes.vrf
        symbols: prove, verify
        why: RFC 9381 ECVRF, byte-exact against the Appendix B.3 vectors.
             A reimplementation produces proofs that verify anything.

        Prose underneath, which must be ignored entirely.
        """
    )
    pins = pinned_dependencies(charter)
    assert len(pins) == 1
    assert "malformed" not in pins[0]
    assert pins[0]["why"].endswith("verify anything.")
    assert "Prose underneath" not in pins[0]["why"]


def test_a_wrong_target_says_which_half_is_wrong(sampler_product):
    """This gate blocks, so a bad target holds every round. "could not import" makes the
    developer agent guess between a missing module, a typo and a renamed function, and a guess
    costs a round. Both failures must name themselves."""
    missing_module = _one(sampler_product, {
        "name": "m", "kind": "deterministic", "trials": 2,
        "target": "app.nope:select", "args": ARGS,
    })
    assert missing_module["ok"] is False
    assert "cannot import module" in missing_module["detail"]
    assert "app.nope" in missing_module["detail"]

    missing_attr = _one(sampler_product, {
        "name": "a", "kind": "deterministic", "trials": 2,
        "target": "app.sampling:selekt", "args": ARGS,
    })
    assert missing_attr["ok"] is False
    assert "no attribute 'selekt'" in missing_attr["detail"]
    # and it lists what IS there, so the fix is visible without another round
    assert "good" in missing_attr["detail"]


def test_a_non_callable_target_is_named_as_such(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "sampling.py").write_text("select = 42\n", encoding="utf-8")
    result = _one(tmp_path, {
        "name": "n", "kind": "deterministic", "trials": 2,
        "target": "app.sampling:select", "args": {},
    })
    assert result["ok"] is False
    assert "not a callable" in result["detail"]
