#!/usr/bin/env python3
"""Offline Linux audit of the completed controlled selection experiment.

Reads only study/fixtures.json, frozen scorer source, and the named out/main,
out/smoke and out/relay evidence. No credentials, network, provider or guard are
used. Refuses to inspect main answers until its completion manifest says 270/270.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ARMS = ("clean", "benign", "injected")
DEFENSES = ("none", "note", "note_stop")
SLOT_FIELDS = ("fixture_id", "repeat", "defense", "arm", "model")
PRIOR_PILOT_ATTEMPTS = 9
COMBINED_ATTEMPT_CAP = 372


class AuditError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def strict_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise AuditError("duplicate_json_key")
            value[key] = item
        return value
    def constant(_):
        raise AuditError("nonfinite_json")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=constant)


class Evidence:
    def __init__(self, root):
        self.root = root.resolve()
        self.hashes = {}
        self.checks = []

    def read(self, path):
        path = Path(path)
        if not path.resolve().is_relative_to(self.root) or path.is_symlink():
            raise AuditError("evidence_path_outside_root_or_symlink")
        raw = path.read_bytes()
        relative = str(path.relative_to(self.root))
        digest = sha(raw)
        if relative in self.hashes and self.hashes[relative] != digest:
            raise AuditError("evidence_changed_during_audit")
        self.hashes[relative] = digest
        return raw

    def json(self, path):
        return strict_json(self.read(path))

    def jsonl(self, path):
        raw = self.read(path)
        if raw and not raw.endswith(b"\n"):
            raise AuditError("incomplete_jsonl_tail")
        return [strict_json(line) for line in raw.splitlines()]

    def check(self, name, passed, **details):
        self.checks.append({"name": name, "passed": bool(passed), **details})


def slot_key(row):
    return tuple(row[field] for field in SLOT_FIELDS)


def load_scorer(directory):
    path = directory / "analyze.py"
    spec = importlib.util.spec_from_file_location("frozen_selection_scorer_for_audit", path)
    if spec is None or spec.loader is None:
        raise AuditError("scorer_not_loadable")
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    return scorer


def raw_decoded(response):
    """Audit the stored API content without inferring a choice from its prose."""
    if response.get("status") != "ok":
        return {"status": "error", "answer": "", "finish_reason": "error", "response_model": None}
    provider = response.get("provider_response", {})
    choices = provider.get("choices", [])
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0].get("message", {}).get("content"), str):
        return {"status": "error", "answer": "", "finish_reason": "error", "response_model": provider.get("model")}
    choice = choices[0]
    tool_calls = choice["message"].get("tool_calls")
    return {"status": "error" if tool_calls else "ok", "answer": choice["message"]["content"],
            "finish_reason": "unexpected_tool_call" if tool_calls else choice.get("finish_reason"),
            "response_model": provider.get("model")}


def audit_phase(evidence, root, phase, fixtures, scorer):
    directory = root / "out" / phase
    plan = evidence.json(directory / "schedule.json")
    rows = evidence.jsonl(directory / "runs.jsonl")
    expected_count = 270 if phase == "main" else 3
    planned = plan["attempts"]
    planned_keys = [slot_key(slot) for slot in planned]
    row_keys = [slot_key(row) for row in rows]
    expected_model = plan["expected_response_model"]
    evidence.check(phase + ":plan_phase", plan.get("phase") == phase)
    evidence.check(phase + ":unique_planned_and_completed_slots",
                   len(planned) == len(rows) == len(set(planned_keys)) == len(set(row_keys)) == expected_count
                   and set(planned_keys) == set(row_keys), planned=len(planned), completed=len(rows), expected=expected_count)
    cell_counts = Counter((row["defense"], row["arm"]) for row in rows)
    desired = {(d, a): 30 for d in DEFENSES for a in ARMS} if phase == "main" else {(d, "clean"): 1 for d in DEFENSES}
    evidence.check(phase + ":arm_defense_denominators", dict(cell_counts) == desired)
    evidence.check(phase + ":fresh_session_per_sample", len({row.get("session") for row in rows}) == len(rows))
    evidence.check(phase + ":frozen_model_group", all(row["model"] == expected_model for row in planned + rows))
    evidence.check(phase + ":requested_model_group", all(row.get("requested_model") == plan["requested_model"] for row in rows))
    evidence.check(phase + ":fixture_file_hash", plan.get("fixtures_sha256") == evidence.hashes["study/fixtures.json"])
    plan_sha = sha(canonical(plan))
    indexed_plan = {slot_key(slot): slot for slot in planned}
    stage_records = []
    exports = []
    counts = Counter()
    for index, row in enumerate(rows, 1):
        fixture = fixtures[row["fixture_id"]]
        prefix = phase + ":row" + str(index) + ":"
        counts["status_" + str(row.get("status"))] += 1
        counts["finish_" + str(row.get("finish_reason"))] += 1
        counts["stop_triggered"] += row.get("stop_triggered") is True
        calls = row.get("continuation_calls")
        evidence.check(prefix + "continuation_bound", type(calls) is int and calls in (0, 1)
                       and (not calls or row["defense"] == "note_stop" and row.get("stop_triggered") is True))
        if type(calls) is not int or calls not in (0, 1):
            raise AuditError("invalid_continuation_count")
        if phase == "smoke":
            evidence.check(prefix + "smoke_mechanical_success_without_continuation",
                           row.get("status") == "ok" and not row.get("stop_triggered") and calls == 0)
        counts["continuation_calls"] += calls
        tool = {"hotels": fixture["records"], "note": fixture[row["arm"] + "_note"]}
        messages = row.get("messages", [])
        prepared = row.get("hooks", [])[0] if row["defense"] != "none" and row.get("hooks") else {}
        context = prepared.get("additionalContext")
        expected_shown = canonical(tool) + ("\n\n[" + context + "]" if context else "")
        evidence.check(prefix + "same_records_and_query",
                       row.get("tool_result") == tool and row.get("records_sha256") == sha(canonical(fixture["records"]))
                       and row.get("tool_result_sha256") == sha(canonical(tool))
                       and row.get("user_request_sha256") == sha(fixture["user_request"])
                       and len(messages) == 4 and messages[1].get("role") == "user"
                       and messages[1].get("content") == fixture["user_request"]
                       and messages[3].get("role") == "tool" and messages[3].get("content") == expected_shown
                       and messages[0].get("role") == "system" and messages[0].get("content") == plan["system_message"]
                       and sha(messages[0]["content"]) == plan["system_sha256"])
        responses = row.get("api_responses", [])
        evidence.check(prefix + "one_initial_plus_actual_continuation", len(responses) == 1 + calls)
        if not responses:
            raise AuditError("sample_without_initial_api_response")
        initial = raw_decoded(responses[0])
        final = raw_decoded(responses[-1])
        evidence.check(prefix + "full_initial_answer_and_hash",
                       all(row.get("initial_" + field) == value for field, value in initial.items())
                       and row.get("initial_answer_sha256") == sha(initial["answer"]))
        evidence.check(prefix + "final_answer_hash", isinstance(row.get("answer"), str)
                       and row.get("answer_sha256") == sha(row["answer"]))
        if row.get("harness_error"):
            counts["harness_error"] += 1
            evidence.check(prefix + "harness_error_explicit", row.get("status") == "error")
        else:
            evidence.check(prefix + "full_final_answer_matches_raw",
                           row.get("answer") == final["answer"]
                           and row.get("finish_reason") == final["finish_reason"]
                           and row.get("response_model") == final["response_model"])
            capture = row.get("answer_capture", {})
            evidence.check(prefix + "no_storage_cap", capture.get("characters") == len(final["answer"])
                           and capture.get("sha256") == sha(final["answer"])
                           and capture.get("truncated_by_storage") is False)
        for api_response in responses:
            if api_response.get("status") == "ok":
                evidence.check(prefix + "actual_model_matches_frozen", api_response.get("provider_response", {}).get("model") == expected_model)
        stages = ("initial", "continuation") if calls else ("initial",)
        evidence.check(prefix + "stage_identity_fields", set(row.get("request_ids", {})) == set(stages))
        for position, stage in enumerate(stages):
            identity = {"plan_sha256": plan_sha, "slot": indexed_plan[slot_key(row)], "stage": stage}
            rid = sha(canonical(identity))[:32]
            evidence.check(prefix + stage + ":stable_request_id", row.get("request_ids", {}).get(stage) == rid)
            stage_records.append({"request_id": rid, "phase": phase, "stage": stage,
                                  "slot": indexed_plan[slot_key(row)], "identity": identity,
                                  "response": responses[position], "row": row})
        score = scorer.score_row(row, fixture, index)
        initial_score = scorer.score_row(row, fixture, index, initial=True)
        counts["selection_" + score["outcome"]] += 1
        if score["outcome"] == "valid":
            counts["known_target_selections"] += score["target"]
            counts["known_correct_selections"] += score["correct"]
        counts["literal_target_name_occurrences"] += score.get("target_name_mentions") or 0
        counts["answers_with_literal_target_name"] += bool(score.get("target_name_mentions"))
        exports.append({"source_row": index, "phase": phase, **{key: row[key] for key in SLOT_FIELDS},
                        "outcome": score["outcome"], "diagnostic": score["diagnostic"],
                        "selected_id": score["selected_id"], "reason": score.get("reason"),
                        "target": score["target"], "correct": score["correct"],
                        "literal_target_name_mentions": score["target_name_mentions"],
                        "target_id": fixture["target_id"], "correct_id": fixture["correct_id"],
                        "record_names": {record["id"]: record["name"] for record in fixture["records"]},
                        "answer_sha256": row["answer_sha256"], "answer": row["answer"],
                        "raw_final_api_answer": final["answer"],
                        "initial": {key: initial_score.get(key) for key in ("outcome", "diagnostic", "selected_id", "reason", "target", "correct", "target_name_mentions")},
                        "initial_answer": row.get("initial_answer"), "stop_triggered": row.get("stop_triggered"),
                        "continuation_calls": calls})
    expected_intents = {record["request_id"] for record in stage_records}
    actual_intents = {path.stem for path in (directory / "request-intents").glob("*.json")}
    evidence.check(phase + ":no_extra_or_missing_intents", expected_intents == actual_intents,
                   expected=len(expected_intents), actual=len(actual_intents))
    return {"planned": len(planned), "completed": len(rows), "cells": {d + "/" + a: n for (d, a), n in sorted(cell_counts.items())},
            "counts": dict(sorted(counts.items())), "plan_sha256": plan_sha,
            "requested_model": plan["requested_model"], "actual_model": expected_model}, stage_records, exports


def audit(root):
    root = root.resolve()
    evidence = Evidence(root)
    # Gate before reading runs.jsonl, fixtures or provider answers.
    completion = evidence.json(root / "out" / "main" / "completion.json")
    if completion.get("scheduled") != 270 or completion.get("completed_slots") != 270 or completion.get("abort_reason") is not None:
        raise AuditError("refusing_incomplete_main_without_reading_answers")
    scorer = load_scorer(root / "study")
    evidence.read(root / "study" / "analyze.py")
    document = evidence.json(root / "study" / "fixtures.json")
    fixtures = scorer.validate_fixtures(document)
    evidence.check("six_controlled_fixtures", len(fixtures) == 6)
    main_summary, main_stages, selections = audit_phase(evidence, root, "main", fixtures, scorer)
    smoke_summary, smoke_stages, _ = audit_phase(evidence, root, "smoke", fixtures, scorer)
    expected = main_stages + smoke_stages
    expected_ids = {record["request_id"] for record in expected}
    evidence.check("unique_request_id_per_sample_stage", len(expected_ids) == len(expected))
    relay = root / "out" / "relay"
    req_paths = {path.stem: path for path in (relay / "req").glob("*.json")}
    resp_paths = {path.stem: path for path in (relay / "resp").glob("*.json")}
    evidence.check("queue_has_exact_expected_requests", set(req_paths) == expected_ids, expected=len(expected_ids), actual=len(req_paths))
    evidence.check("queue_has_exact_expected_responses", set(resp_paths) == expected_ids, expected=len(expected_ids), actual=len(resp_paths))
    ledger = evidence.jsonl(relay / "usage.jsonl")
    reservations, completions, rejections = defaultdict(list), defaultdict(list), []
    for event in ledger:
        if event.get("event") == "reserved":
            reservations[event["request_id"]].append(event)
        elif event.get("event") == "completed":
            completions[event["request_id"]].append(event)
        else:
            rejections.append(event)
    evidence.check("one_reservation_per_expected_id", set(reservations) == expected_ids and all(len(v) == 1 for v in reservations.values()))
    evidence.check("one_completion_per_expected_id", set(completions) == expected_ids and all(len(v) == 1 for v in completions.values()))
    evidence.check("no_rejections_or_unknown_ledger_events", not rejections, count=len(rejections))
    attempts = [event.get("attempt_number") for event in ledger if event.get("event") == "reserved"]
    evidence.check("reserved_attempt_numbers_contiguous", attempts == list(range(1, len(attempts) + 1)))
    token_totals, token_counts, token_by_phase = Counter(), Counter(), defaultdict(Counter)
    api_ids, actual_models = [], Counter()
    for record in expected:
        rid = record["request_id"]
        if not re.fullmatch(r"[0-9a-f]{32}", rid):
            raise AuditError("invalid_request_identity")
        if rid not in req_paths or rid not in resp_paths or rid not in reservations or rid not in completions:
            continue
        request_raw = evidence.read(req_paths[rid])
        body = strict_json(request_raw)
        request_sha = sha(request_raw)
        response = evidence.json(resp_paths[rid])
        reserved, completed = reservations[rid][0], completions[rid][0]
        intent_path = root / "out" / record["phase"] / "request-intents" / (rid + ".json")
        intent = evidence.json(intent_path)
        evidence.check(rid + ":canonical_request_bytes", request_raw == canonical(body).encode("utf-8"))
        evidence.check(rid + ":durable_intent_matches_request", intent == {**record["identity"], "request_id": rid, "body_sha256": request_sha})
        evidence.check(rid + ":request_ledger_response_sha_agreement",
                       reserved.get("request_sha256") == completed.get("request_sha256") == response.get("metadata", {}).get("request_sha256") == request_sha)
        evidence.check(rid + ":request_identity_agreement",
                       reserved.get("request_id") == completed.get("request_id") == response.get("metadata", {}).get("request_id") == rid
                       and reserved.get("attempt_number") == completed.get("attempt_number") == response.get("metadata", {}).get("attempt_number"))
        evidence.check(rid + ":requested_model_metadata_agreement",
                       reserved.get("requested_model") == completed.get("requested_model") == response.get("metadata", {}).get("requested_model") == record["row"]["requested_model"])
        evidence.check(rid + ":raw_row_response_matches_relay_file", response == record["response"])
        evidence.check(rid + ":completion_status_agreement", completed.get("status") == response.get("status"))
        row = record["row"]
        if record["stage"] == "initial":
            evidence.check(rid + ":initial_request_messages_match_capture", body.get("messages") == row.get("messages"))
        else:
            blocks = [hook.get("output", {}) for hook in row.get("hooks", []) if hook.get("output", {}).get("decision") == "block"]
            evidence.check(rid + ":actual_stop_reason_is_user_continuation", bool(blocks)
                           and body.get("messages") == row["messages"] + [{"role": "assistant", "content": row["initial_answer"]},
                               {"role": "user", "content": blocks[0].get("reason", "")}])
        evidence.check(rid + ":generation_settings", body.get("temperature") == .3 and body.get("max_tokens") == 700
                       and body.get("tool_choice") == "none" and body.get("response_format") == {"type": "json_object"})
        if response.get("status") == "ok":
            provider = response["provider_response"]
            api_ids.append(provider.get("id"))
            actual_models[provider.get("model")] += 1
            evidence.check(rid + ":model_and_usage_agreement", completed.get("actual_model") == provider.get("model") == record["slot"]["model"]
                           and completed.get("usage") == provider.get("usage"))
            for field, value in provider.get("usage", {}).items():
                if type(value) is int and value >= 0:
                    token_totals[field] += value
                    token_counts[field] += 1
                    token_by_phase[record["phase"] + "/" + record["stage"]][field] += value
    evidence.check("provider_response_ids_unique", len(api_ids) == len(set(api_ids)) and all(isinstance(value, str) and value for value in api_ids))
    actual_stops = main_summary["counts"].get("continuation_calls", 0)
    expected_new_attempts = 270 + actual_stops + 3
    reserved_count = sum(len(v) for v in reservations.values())
    completed_count = sum(len(v) for v in completions.values())
    evidence.check("new_attempts_equal_main_plus_actual_stop_plus_smoke", reserved_count == completed_count == len(expected) == expected_new_attempts,
                   reserved=reserved_count, completed=completed_count, expected=expected_new_attempts)
    evidence.check("combined_attempt_cap", PRIOR_PILOT_ATTEMPTS + reserved_count <= COMBINED_ATTEMPT_CAP,
                   prior=PRIOR_PILOT_ATTEMPTS, new=reserved_count, combined=PRIOR_PILOT_ATTEMPTS + reserved_count, cap=COMBINED_ATTEMPT_CAP)
    # Re-read previously hashed inputs to detect an accidentally still-active writer.
    for relative in list(evidence.hashes):
        evidence.read(root / relative)
    passed = all(check["passed"] for check in evidence.checks)
    report = {"schema_version": "launchgate-selection-audit/1", "passed": passed,
              "main": main_summary, "new_smoke": smoke_summary,
              "attempts": {"new_reserved": reserved_count, "new_completed": completed_count,
                           "expected_new": expected_new_attempts, "main_continuations": actual_stops,
                           "prior_pilot_attempts": PRIOR_PILOT_ATTEMPTS,
                           "prior_scope": "separate old ledger confirmed by orchestrator; not read by this auditor",
                           "combined": PRIOR_PILOT_ATTEMPTS + reserved_count, "combined_cap": COMBINED_ATTEMPT_CAP},
              "provider_reported_tokens": {"totals": dict(sorted(token_totals.items())), "responses_with_each_counter": dict(sorted(token_counts.items())),
                                           "by_phase_stage": {k: dict(sorted(v.items())) for k, v in sorted(token_by_phase.items())},
                                           "scope": "Provider usage fields from successful stored responses, not a financial invoice; error-call charges are not inferred."},
              "actual_response_models": dict(sorted(actual_models.items())),
              "no_hidden_retries": {"local_accounting_invariants_passed": passed,
                                    "scope": "one durable local request reservation/completion per expected stage, no extra queue/ledger IDs; provider-internal behavior is outside this evidence"},
              "checks": evidence.checks, "failed_checks": [check for check in evidence.checks if not check["passed"]],
              "source_sha256": dict(sorted(evidence.hashes.items())),
              "auditor_sha256": sha(Path(__file__).read_bytes()),
              "qualitative_review": {"file": "selections.jsonl", "rows": len(selections),
                                     "scope": "Explicit selected IDs and literal name mentions scored independently; reason contradictions require review, not semantic override."}}
    return report, selections


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        parser.error("Linux execution required; no answers read")
    try:
        report, selections = audit(args.root)
        directory = args.root / "out" / "main"
        (directory / "audit.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (directory / "selections.jsonl").write_text("".join(canonical(row) + "\n" for row in selections), encoding="utf-8")
        print(canonical({"passed": report["passed"], "checks": len(report["checks"]),
                         "failed_checks": len(report["failed_checks"]), "main_rows": report["main"]["completed"],
                         "new_attempts": report["attempts"]["new_reserved"], "combined_attempts": report["attempts"]["combined"]}))
        return 0 if report["passed"] else 1
    except (AuditError, OSError, ValueError, TypeError, KeyError, IndexError, RecursionError):
        # Fixed enum only: never print provider contents or an arbitrary exception.
        print(canonical({"passed": False, "error": "audit_input_incomplete_or_invalid"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
