"""Judge the delivery survey's answers with the hub's own Pay-on-Verified verifier.

Runs INSIDE the apex hub container, so the audit prompt, the Metis call and the verdict reader are the very
ones that release escrow, and the verifier key never leaves the container:

    docker cp judge_in_hub.py modelmarket-hub:/tmp/ && docker cp judge-in.jsonl modelmarket-hub:/tmp/
    docker exec modelmarket-hub python /tmp/judge_in_hub.py /tmp/judge-in.jsonl > judge-out.jsonl

Input: one task per line, {id, intent, output_json} (survey.mjs tasks). Output: one line per task, the
verdict (a genuine pass or fail with score and reasons) or why there is none.
"""

import asyncio
import json
import secrets
import sys

from aimarket_hub import verified_settlement as vs

CONCURRENCY = 3
ATTEMPTS = 3


async def judge(task: dict, gate: asyncio.Semaphore) -> dict:
    async with gate:
        last: dict = {}
        for attempt in range(ATTEMPTS):
            # A fresh fence nonce per attempt, as the hub does: a reused one could leak into an answer.
            audit_id = secrets.token_hex(vs._FENCE_NONCE_BYTES)
            payload = {
                "input": vs.VerifiedSettlementService._compose_audit_prompt(task["intent"], task["output_json"], audit_id),
                "route": "fast",   # the jury decides every /v1/verify (jury_default_for_verify), whatever the route
                "min_verify_score": vs.audit_threshold(),
                "audit_id": audit_id,
            }
            kind, env = await vs.VerifiedSettlementService._post_verify(
                None, vs.metis_url(), vs.metis_key(), payload, audit_id)
            if kind == "verdict":
                reading = vs._read_verdict(env, vs.score_threshold(), label=task["id"], audit_bar=vs.audit_threshold())
                d = reading.delivery
                return {"id": task["id"], "kind": "verdict", "genuine": reading.genuine,
                        "passed": reading.passed if reading.genuine else None, "cause": reading.cause or None,
                        "score": d.score if d else None, "reasons": list(d.reasons)[:6] if d else [],
                        "audit_score": reading.audit_score, "trace_id": reading.trace_id}
            detail = env if isinstance(env, str) else str((env or {}).get("error") or (env or {}).get("status") or "")
            last = {"id": task["id"], "kind": kind, "detail": detail[:200]}
            if kind == "fatal":
                break
            await asyncio.sleep(5 * (attempt + 1))
        return last


async def main(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        tasks = [json.loads(line) for line in fh if line.strip()]
    gate = asyncio.Semaphore(CONCURRENCY)
    for pending in asyncio.as_completed([judge(t, gate) for t in tasks]):
        print(json.dumps(await pending, default=str), flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
