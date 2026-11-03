"""C3 signing strategies — the only place in the hub that can put value in motion.

Three strategies, ordered by how much trust they need:

    plan      the default. Refuses to sign anything. Everything upstream of a signature
              still runs (build, simulate, record), so plan mode is genuinely useful: it
              proves an authorization WOULD be accepted, and surfaces a nonce gap, an
              expired deadline or an insufficient balance, without a transaction existing.
    external  hands an unsigned transaction to an operator-run signer and takes back a
              hash. No key material enters this process, which is the point.
    env       signs in-process with a key read from the environment. Most capable, least
              contained; gated hardest.

Two rules hold across all three:

* Nothing signs unless :func:`config.submit_policy` says so — mode, strategy AND the
  explicit confirmation phrase. A refusal raises SubmissionRefused BEFORE a transaction is
  built, so the caller's pending record is untouched and safe to retry.
* A returned transaction hash is never taken as proof of anything. The mirror confirms by
  reading the chain, so a broken or hostile signer can at worst do nothing — it cannot
  convince the hub that money moved.
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from aimarket_hub.escrow_bridge import config
from aimarket_hub.escrow_bridge.errors import SubmissionRefused

logger = logging.getLogger(__name__)

_HASH_LEN = 66  # "0x" + 32 bytes
_MAX_SIGNER_REPLY_BYTES = 64 * 1024


class _NoSignerRedirect(urllib.request.HTTPRedirectHandler):
    """A signer redirect must never receive its bearer token or transaction."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_signer(request: urllib.request.Request, *, timeout: float):
    return urllib.request.build_opener(_NoSignerRedirect()).open(request, timeout=timeout)


@dataclass(frozen=True)
class UnsignedTx:
    """Everything a signer needs, and nothing it does not."""

    to: str
    data: str
    chain_id: int
    gas: int
    value: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "to": self.to, "data": self.data, "chainId": self.chain_id,
            "gas": self.gas, "value": self.value,
        }


def _checksummed(address: str) -> str:
    """EIP-55 form of ``address``, or the input unchanged if that cannot be computed.

    Unchanged rather than raising: a signer that refuses to try is worse than one that
    hands eth-account exactly what it was given and lets it complain.
    """
    try:
        from eth_utils import to_checksum_address

        return to_checksum_address(str(address or "").strip())
    except Exception:
        return str(address or "").strip()


def _looks_like_tx_hash(value: object) -> bool:
    text = str(value or "").strip()
    if len(text) != _HASH_LEN or not text.startswith("0x"):
        return False
    try:
        bytes.fromhex(text[2:])
    except ValueError:
        return False
    return True


class Signer:
    """Base strategy. Subclasses either sign or explain why they will not."""

    name = "base"

    def submit(self, tx: UnsignedTx) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    @property
    def sender(self) -> str:
        """Address transactions will come from, or "" if this strategy cannot know."""
        return ""


class PlanOnlySigner(Signer):
    """The default: builds nothing, sends nothing, and says so clearly."""

    name = config.STRATEGY_PLAN

    def submit(self, tx: UnsignedTx) -> str:
        raise SubmissionRefused(
            "submission strategy is 'plan': the transaction was built and simulated but "
            "NOT sent. Configure AIMARKET_ESCROW_SUBMIT_STRATEGY and "
            "AIMARKET_ESCROW_SUBMIT_CONFIRM to broadcast."
        )


class ExternalSigner(Signer):
    """POSTs an unsigned transaction to an operator-run signer that signs and broadcasts.

    The endpoint is trusted to do its job, NOT to report the truth: whatever it returns is
    only a hint about where to look on chain. The mirror verifies by reading the receipt.
    """

    name = config.STRATEGY_EXTERNAL

    def __init__(self, url: str = "", token: str = "", timeout_s: float | None = None):
        self._url = url or config.signer_url()
        self._token = token or config.signer_token()
        self._timeout = timeout_s if timeout_s is not None else config.rpc_timeout_s()

    def submit(self, tx: UnsignedTx) -> str:
        if not self._url:
            raise SubmissionRefused("strategy 'external' needs AIMARKET_ESCROW_SIGNER_URL")
        body = json.dumps({"transaction": tx.as_dict()}).encode()
        request = urllib.request.Request(
            self._url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        if self._token:
            request.add_header("Authorization", f"Bearer {self._token}")
        try:
            with _open_signer(request, timeout=self._timeout) as resp:
                raw = resp.read(_MAX_SIGNER_REPLY_BYTES + 1)
                if len(raw) > _MAX_SIGNER_REPLY_BYTES:
                    raise SubmissionRefused("external signer response exceeds the size limit")
                payload = json.loads(raw.decode() or "{}")
        except urllib.error.HTTPError as exc:
            # Never echo the response body: a signer's error can quote the request, and
            # the request is about to be retried rather than debugged from a log.
            raise SubmissionRefused(f"external signer returned HTTP {exc.code}") from exc
        except SubmissionRefused:
            raise
        except Exception as exc:
            raise SubmissionRefused(
                f"external signer unreachable ({type(exc).__name__})"
            ) from exc
        tx_hash = (payload.get("tx_hash") or payload.get("transactionHash")) if isinstance(payload, dict) else None
        if not _looks_like_tx_hash(tx_hash):
            raise SubmissionRefused(
                "external signer did not return a transaction hash — treating the "
                "submission as not made"
            )
        return str(tx_hash).strip()


class EnvKeySigner(Signer):
    """Signs in-process with a key from the environment, then broadcasts via the RPC pool.

    Refuses if the configured key can be found anywhere in the repository working tree: a
    key that is committed is a key that is already public, and the failure mode of using it
    anyway is that the hub's own funds are spendable by anyone who read the repo.
    """

    name = config.STRATEGY_ENV

    def __init__(self, key: str = "", pool: Any = None):
        self._key = key or config.private_key()
        self._pool = pool
        self._address = ""

    @property
    def sender(self) -> str:
        if self._address:
            return self._address
        if not self._key:
            return ""
        try:
            from eth_account import Account

            self._address = Account.from_key(self._key).address
        except Exception:
            return ""
        return self._address

    def _guard_committed_key(self) -> None:
        """Refuse a key that is present in the working tree.

        The pattern goes to ``git grep`` on STDIN, never in argv. Passing it as an argument —
        which this did until 2026-07-30 — publishes the key to every process on the box for
        the lifetime of the child: ``/proc/<pid>/cmdline`` is world-readable on Linux and
        ``ps -ax -o args=`` shows it on any Unix. Demonstrated: a child holding a 64-hex
        secret in argv is visible to an unprivileged ``ps``; the same child reading it from
        stdin is not. A guard against a key being public must not be the thing that publishes
        it.

        Bounded and best-effort: ``git grep`` over tracked files is fast, and a failure to
        run is NOT treated as a pass — an environment where the check cannot run gets a
        warning, because the alternative (refusing to sign because git is missing) would
        break a legitimate containerised deploy. "Cannot run" now includes git answering a
        non-search error such as 128 outside a repository, which previously looked identical
        to "not found" and passed in silence.
        """
        key = self._key.strip()
        if not key:
            return
        needle = key[2:] if key.lower().startswith("0x") else key
        if len(needle) < 32:
            return
        # Repo root, so the search covers the whole tree rather than the subtree the process
        # happens to be started in. No secret in this argv either.
        root: str | None = None
        try:
            top = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, timeout=10, check=False, text=True,
            )
            if top.returncode == 0 and top.stdout.strip():
                root = top.stdout.strip()
        except Exception:
            root = None

        try:
            found = subprocess.run(
                # -f - reads the pattern from stdin. --no-pager and -I keep the child cheap
                # and stop a binary file from producing output we would then hold in memory.
                ["git", "--no-pager", "grep", "--fixed-strings", "--quiet", "-I", "-f", "-"],
                input=needle.encode(),
                cwd=root, capture_output=True, timeout=20, check=False,
            )
        except Exception as exc:
            logger.warning(
                "could not check whether the signing key is committed (%s) — proceeding, "
                "but verify this key is not in version control", type(exc).__name__,
            )
            return

        if found.returncode == 0:
            raise SubmissionRefused(
                "the configured signing key was found in the repository working tree — "
                "it must be considered public. Rotate it and supply the new key only via "
                "the environment."
            )
        if found.returncode != 1:
            # 1 is git's "no match". Anything else — 128 outside a repository, 129 for a bad
            # usage — means the search did not happen, and reporting that as a clean result
            # is the failure this branch exists to prevent. The stderr is NOT logged: it can
            # echo the pattern back.
            logger.warning(
                "the committed-key check did not run (git exited %d) — proceeding, but "
                "verify this key is not in version control", found.returncode,
            )

    def submit(self, tx: UnsignedTx) -> str:
        if not self._key:
            raise SubmissionRefused("strategy 'env' needs AIMARKET_ESCROW_PRIVATE_KEY")
        self._guard_committed_key()
        try:
            from eth_account import Account
        except Exception as exc:
            raise SubmissionRefused(f"eth-account unavailable: {type(exc).__name__}") from exc

        pool = self._pool
        if pool is None:
            from aimarket_hub.escrow_bridge import chain

            pool = chain._pool()

        sender = self.sender
        if not sender:
            raise SubmissionRefused("the configured signing key is not a usable private key")
        try:
            nonce_raw = pool.call("eth_getTransactionCount", [sender, "pending"])
            nonce = int(str(nonce_raw), 16) if str(nonce_raw).startswith("0x") else int(nonce_raw)
            fee_raw = pool.call("eth_gasPrice")
            gas_price = int(str(fee_raw), 16) if str(fee_raw).startswith("0x") else int(fee_raw)
        except Exception as exc:
            raise SubmissionRefused(
                f"could not read the account nonce or gas price ({type(exc).__name__})"
            ) from exc

        # eth-account REFUSES a `to` that is not EIP-55 checksummed — it raises
        # `TypeError: Transaction had invalid fields` — and every address on this path
        # arrives lowercase, because that is how addresses come back from an RPC receipt
        # and how they are stored. So this signer could never sign anything: the failure
        # surfaced as "signing failed (TypeError)", a message that deliberately hides the
        # payload and therefore hides the cause too. It went unnoticed because the live
        # deployment collects through an external policy signer (HORKOS) and never used
        # the env-key path at all; the first thing to exercise it was the UNI bubble.
        unsigned = {
            "to": _checksummed(tx.to), "data": tx.data, "value": tx.value, "gas": int(tx.gas),
            "nonce": nonce, "gasPrice": gas_price, "chainId": int(tx.chain_id),
        }
        try:
            signed = Account.sign_transaction(unsigned, self._key)
        except Exception as exc:
            # Deliberately type-only: a signing error can carry the payload, and the
            # payload is adjacent to the key.
            raise SubmissionRefused(f"signing failed ({type(exc).__name__})") from exc
        raw = signed.raw_transaction if hasattr(signed, "raw_transaction") else signed.rawTransaction
        try:
            tx_hash = pool.call("eth_sendRawTransaction", ["0x" + bytes(raw).hex()])
        except Exception as exc:
            raise SubmissionRefused(f"broadcast rejected ({type(exc).__name__})") from exc
        if not _looks_like_tx_hash(tx_hash):
            raise SubmissionRefused("the node did not return a transaction hash")
        return str(tx_hash).strip()


def build_signer(*, pool: Any = None) -> Signer:
    """The signer this configuration allows — ``plan`` whenever anything is missing.

    Resolution lives here so no caller can assemble a broadcasting signer by accident:
    asking for one on an under-configured hub returns the inert one.
    """
    policy = config.submit_policy()
    if not policy.may_broadcast:
        if policy.reason:
            logger.info("escrow bridge: submission held in plan mode — %s", policy.reason)
        return PlanOnlySigner()
    if policy.strategy == config.STRATEGY_EXTERNAL:
        return ExternalSigner()
    if policy.strategy == config.STRATEGY_ENV:
        return EnvKeySigner(pool=pool)
    return PlanOnlySigner()
