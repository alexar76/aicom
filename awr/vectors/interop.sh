#!/bin/bash
# Reverse-direction AWR/2 interoperability: every implementation ISSUES, all of them VERIFY.
#
#     awr/vectors/interop.sh
#
# check_vectors.py drives one direction only — it hands fixed bytes to an implementation and
# checks what comes back. That cannot catch an issuer that writes bytes nobody else accepts,
# and an issuer is half of an interoperable format. This script closes the loop:
#
#   * each issuing implementation issues four documents with the same key, id and timestamp:
#       - a WorkReceipt whose strings are NFD and whose object keys include a non-BMP
#         character, so NFC normalization (SPEC 4.1 item 2) or code-point key sorting
#         (4.1 item 1) changes the signed bytes and is caught;
#       - a second WorkReceipt whose `parents` edge commits to the first one's canonical
#         digest, computed by the issuing implementation itself (8.1);
#       - a VerificationVerdict over the second receipt, from a different key, so L1 is
#         reachable (10.2);
#       - a BlameAttestation naming the chain and the blamed hop (3.5);
#   * every other implementation then verifies all four, at L0 and at L1;
#   * finally the two issuers' bytes are compared. Ed25519 is deterministic (RFC 8032), so
#     with the same key, --id and --now the documents must be identical down to the
#     proofValue. Anything less means the two canonicalize differently, which no amount of
#     "it verifies" would have revealed.
#
# The keys are the published RFC 8032 section 7.1 test seeds, the same ones index.json uses.
# They confer nothing and MUST NOT be used to issue a real document.
#
# Exit code 0 iff every verification succeeded and both issuers agreed byte for byte.
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/awr-interop-XXXXXX")
trap 'rm -rf "$WORK"' EXIT
export PYTHONPATH="$ROOT/awr/reference/python${PYTHONPATH:+:$PYTHONPATH}"

PY="$ROOT/aimarket-hub/.venv/bin/python"
RS="$ROOT/awr/rust/target/debug/awr"
JS_CLI="$ROOT/docs/verifier/js/cli.js"

# tag -> command. An implementation with no `issue` subcommand (exit 3, which section 17
# permits for a verify-only build) is used as a verifier only.
impl_cmd() {
  case "$1" in
    py) echo "$PY -m awr" ;;
    rs) echo "$RS" ;;
    js) echo "node $JS_CLI" ;;
  esac
}
ISSUERS="rs py"
VERIFIERS="py rs js"

NOW=2026-07-31T10:15:30Z
FAILURES=0
fail() { echo "  FAIL: $*"; FAILURES=$((FAILURES + 1)); }

printf '9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60\n' > "$WORK/hub.key"
printf '4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb\n' > "$WORK/judge.key"
printf 'f5e5767cf153319517630f226876b86c8160cc583bc013744c6bf255f5cc0ee5\n' > "$WORK/blamer.key"

# "cafe" + U+0301 (NFD) in modelId; U+1F602 and U+E000 in object keys, which sort in the
# opposite order under UTF-16 code units (4.1 item 1) than under code points.
cat > "$WORK/subject-parent.json" <<'EOF'
{
  "work": {
    "modelId": "café-retriever@vendor",
    "capability": "urn:example:capability:retrieve",
    "startedAt": "2026-07-31T10:15:20Z",
    "completedAt": "2026-07-31T10:15:24Z",
    "latencyMs": 4120,
    "status": "succeeded"
  },
  "inputDigest": "sha256-Yn5Nwt4wZ0mB0KcJ9pQ6xL3vR8sT1uV5wX7yZ9aB0cE=",
  "outputDigest": "sha256-9pFhKq2LmN4oP6rS8tU0vW2xY4zA6bC8dE0fG2hI4jE=",
  "nonce": "01J9Z8QK4T7YB2N5V6W8XA3C0D",
  "x-😂-emoji-key": "sorts BELOW U+E000 as UTF-16 code units, ABOVE it as code points",
  "x--private-use": "U+E000"
}
EOF

emit_child_subject() {   # $1 = parent digest SRI
  cat <<EOF
{
  "work": {
    "modelId": "claude-sonnet-5@anthropic",
    "capability": "urn:example:capability:summarise",
    "startedAt": "2026-07-31T10:15:28Z",
    "completedAt": "2026-07-31T10:15:30Z",
    "latencyMs": 2340,
    "status": "succeeded"
  },
  "inputDigest": "sha256-9pFhKq2LmN4oP6rS8tU0vW2xY4zA6bC8dE0fG2hI4jE=",
  "outputDigest": "sha256-Zm9vYmFyYmF6cXV1eDEyMzQ1Njc4OTBhYmNkZWZnaGk=",
  "parents": [{ "id": "urn:uuid:parent", "digestSRI": "$1", "role": "retrieval" }],
  "price": { "currency": "USD", "amount": "0.15" },
  "nonce": "01J9Z8QK4T7YB2N5V6W8XA3C0E"
}
EOF
}

echo "=============================================================================="
echo "issuing"
echo "=============================================================================="
for tag in $ISSUERS; do
  cmd=$(impl_cmd "$tag")
  d="$WORK/$tag"; mkdir -p "$d"

  $cmd issue "$WORK/subject-parent.json" --key "$WORK/hub.key" --type WorkReceipt \
      --id urn:uuid:parent --now "$NOW" --issuer-name example-hub > "$d/parent.json" 2>"$d/err" \
      || { fail "$tag cannot issue a WorkReceipt: $(cat "$d/err")"; continue; }
  psri=$($cmd digest "$d/parent.json")

  emit_child_subject "$psri" > "$d/subject-child.json"
  $cmd issue "$d/subject-child.json" --key "$WORK/hub.key" --type WorkReceipt \
      --id urn:uuid:child --now "$NOW" --issuer-name example-hub > "$d/child.json"
  csri=$($cmd digest "$d/child.json")

  cat > "$d/subject-verdict.json" <<EOF
{
  "verifiedWork": { "id": "urn:uuid:child", "digestSRI": "$csri" },
  "verdict": "pass",
  "score": "0.93",
  "method": { "id": "urn:example:method:grounded-council-v1", "name": "grounded council" },
  "policy": { "threshold": "0.80" }
}
EOF
  $cmd issue "$d/subject-verdict.json" --key "$WORK/judge.key" --type VerificationVerdict \
      --id urn:uuid:verdict --now "$NOW" --issuer-name independent-judge > "$d/verdict.json"

  cat > "$d/subject-blame.json" <<EOF
{
  "chain": { "id": "urn:uuid:child", "digestSRI": "$csri" },
  "blamedWork": { "id": "urn:uuid:parent", "digestSRI": "$psri" },
  "failureClass": "upstream-input",
  "confidence": "0.90",
  "method": { "id": "urn:example:method:hop-bisect-v1" }
}
EOF
  $cmd issue "$d/subject-blame.json" --key "$WORK/blamer.key" --type BlameAttestation \
      --id urn:uuid:blame --now "$NOW" --issuer-name hop-attributor > "$d/blame.json"

  echo "  $tag issued parent, child (chained to parent $psri), verdict, blame"
done

echo
echo "=============================================================================="
echo "cross-verification"
echo "=============================================================================="
for issuer in $ISSUERS; do
  d="$WORK/$issuer"
  for verifier in $VERIFIERS; do
    cmd=$(impl_cmd "$verifier")
    echo "-- $issuer issued -> $verifier verifies"
    # file : extra arguments : expected profile
    while IFS='|' read -r file extra profile; do
      [ -z "$file" ] && continue
      # shellcheck disable=SC2086
      out=$($cmd verify "$d/$file" $extra --now "$NOW" 2>/dev/null); rc=$?
      got=$("$PY" -c '
import json, sys
r = json.load(sys.stdin)
print("%s %s %s %s" % (r["valid"], r["profile"],
  ",".join(sorted({x["code"] for x in r["reasons"]})) or "-",
  ",".join(sorted({x["code"] for x in r["warnings"]})) or "-"))' <<< "$out" 2>/dev/null)
      set -- $got
      printf '     exit=%s valid=%-5s profile=%-5s errors=%-14s warnings=%-14s %s\n' \
        "$rc" "${1:-?}" "${2:-?}" "${3:-?}" "${4:-?}" "$file"
      [ "$rc" = 0 ] || fail "$issuer/$file rejected by $verifier"
      [ "${1:-}" = "True" ] || fail "$issuer/$file not valid under $verifier"
      [ -n "$profile" ] && [ "${2:-}" != "$profile" ] && fail "$issuer/$file: $verifier reported profile ${2:-} not $profile"
    done <<EOF
parent.json|--profile L0|L0
child.json|--parents $d/parent.json --profile L0|L0
child.json|--parents $d/verdict.json --profile L1|L1
verdict.json|--parents $d/child.json|
blame.json|--parents $d/parent.json $d/child.json|
EOF
  done
done

echo
echo "=============================================================================="
echo "byte equality between issuers (Ed25519 is deterministic, RFC 8032)"
echo "=============================================================================="
# `issue` framing is not constrained by section 17 -- the reference pretty-prints and the
# Rust build emits compact bytes -- so the comparison is over the CANONICAL form, which is
# the only thing the signature is computed over.
#
# Every issuer's document is canonicalized by EVERY implementation, and all of those byte
# strings must be equal. Canonicalizing both issuers' output with a single canonicalizer
# would prove only that one implementation cannot tell them apart: two canonicalizers that
# are each self-consistent but disagree with each other is precisely the failure that split
# AWR/1 into two dialects (section 12, Appendix D), and it is invisible to a one-sided check.
for f in parent child verdict blame; do
  ref=""; ref_issuer=""; ref_canon=""; agreed=1
  for tag in $ISSUERS; do
    for canon in $VERIFIERS; do
      bytes=$($(impl_cmd "$canon") canonicalize "$WORK/$tag/$f.json" | od -An -tx1 | tr -d ' \n')
      if [ -z "$bytes" ]; then
        fail "$f.json: $canon produced no canonical bytes for the document $tag issued"
        agreed=0
        continue
      fi
      if [ -z "$ref" ]; then ref=$bytes; ref_issuer=$tag; ref_canon=$canon; continue; fi
      if [ "$bytes" != "$ref" ]; then
        agreed=0
        fail "$f.json: $tag issued/$canon canonicalized disagrees with $ref_issuer issued/$ref_canon canonicalized"
        echo "       $ref_issuer issued / $ref_canon canonicalized:"
        $(impl_cmd "$ref_canon") canonicalize "$WORK/$ref_issuer/$f.json" | hexdump -C | head -8
        echo "       $tag issued / $canon canonicalized:"
        $(impl_cmd "$canon") canonicalize "$WORK/$tag/$f.json" | hexdump -C | head -8
      fi
    done
  done
  if [ "$agreed" = 1 ]; then
    n=$(( ${#ref} / 2 ))
    printf '  %-13s %d bytes, identical under all %d canonicalizers for all %d issuers, proofValue included\n' \
      "$f.json:" "$n" "$(set -- $VERIFIERS; echo $#)" "$(set -- $ISSUERS; echo $#)"
  fi
done

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "OK: every issued document verifies in every implementation, and the issuers agree byte for byte"
  exit 0
fi
echo "$FAILURES FAILURE(S)"
exit 1
