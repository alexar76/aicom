"""Opening and closing channels: deposit verification and claims, escrow funding, proven opens
and the channel row itself.
"""

from __future__ import annotations

import hmac
import logging
import math
import secrets
import uuid
from typing import Any

logger = logging.getLogger("aimarket_hub.channels")


class LedgerOpeningMixin:
    """Open and close channels, with deposit and escrow checks."""

    # ── Channel operations ────────────────────────────────────────

    def open(
        self,
        deposit_usd: float,
        token: str = "",
        chain: str = "",
        wallet: str = "",
        tx_hash: str = "",
        with_secret: bool = True,
        payer_signature: str = "",
        escrow_channel_id: str = "",
    ) -> dict[str, Any]:
        """Open a pre-funded payment channel.

        with_secret: mint a one-time debit secret (returned ONCE as `channel_secret`); debit
            then requires it. Both this primitive and open_channel default to ON.
            Explicitly opting out creates a frozen channel: debit/hold/close/refund cannot
            authenticate it. There is no implicit internal or legacy authorization bypass.
        payer_signature: EIP-191 signature by the PAYING wallet over
            payer_proof_challenge(payer=..., tx_hash=..., chain=...). Required on the
            on-chain-verified path: without it the channel_secret goes to whoever quotes
            the (public) deposit tx first. See the module docstring.
        escrow_channel_id: an AIMarketEscrow channel that already holds the funds. Only
            honoured when the (opt-in, default-off) escrow bridge is enabled. It replaces
            the transfer-hash path entirely: the contract records the depositor, so there
            is no public tx hash for a bystander to quote and no EIP-191 proof to collect,
            and the remainder is refundable BY THE CONTRACT instead of becoming an
            operator payout obligation.
        """
        # NaN/inf first: `nan <= 0` and `nan > 10_000` are BOTH False, so a non-finite
        # deposit slipped through the range check and blew up in round(nan * 100) —
        # a 500 from the HTTP endpoint instead of a 400.
        try:
            deposit_usd = float(deposit_usd)
        except (TypeError, ValueError):
            return {"error": "deposit must be a number"}
        if not math.isfinite(deposit_usd):
            return {"error": "deposit must be a finite number"}
        if deposit_usd <= 0 or deposit_usd > 10_000:
            return {"error": "deposit must be between 0 and 10,000 USD"}

        if not self._check_rate(
            wallet, self._rate_state, channels._MAX_OPENS_PER_WALLET_PER_HOUR,
            channels._anon_opens_per_hour(),
        ):
            return {
                "error": (
                    f"rate limit exceeded — max {channels._MAX_OPENS_PER_WALLET_PER_HOUR} channel "
                    "opens per hour per wallet"
                )
            }

        deposit_cents = channels._dollars_to_cents(deposit_usd)
        token = token or channels._DEFAULT_TOKEN
        chain = chain or channels._DEFAULT_CHAIN

        # ── Escrow-backed funding (opt-in bridge) ────────────────────────────
        # Verified by READING the contract rather than by trusting a transfer hash, so
        # the depositor is bound by construction. Deliberately an early, separate branch:
        # it must never fall through into the transfer path, and the transfer path must be
        # byte-for-byte unchanged for every hub that has not enabled the bridge.
        escrow_channel_id = (escrow_channel_id or "").strip()
        if escrow_channel_id:
            ok, err, claim_id = self._verify_escrow_funding(
                escrow_channel_id=escrow_channel_id,
                wallet=wallet,
                deposit_usd=deposit_usd,
            )
            if not ok:
                return {"error": err}
            if payer_signature:
                # The escrow channel id is public (the contract emits it), so anyone could open
                # the ledger channel first and squat it: they cannot spend it (every debit needs
                # the depositor's EIP-712 signature) but the depositor was locked out. A proof
                # from the depositor's own wallet takes the escrow channel back from an opener
                # who never proved anything, as long as nothing was charged on it.
                recovered = channels._recover_payer_address(
                    payer=wallet, tx_hash=escrow_channel_id, chain=chain,
                    deposit_usd=deposit_usd, signature=payer_signature,
                )
                if not recovered or not channels._wallet_matches(recovered, wallet):
                    return {
                        "error": "invalid payer proof for this escrow channel",
                        "challenge": channels.payer_proof_challenge(
                            payer=wallet, tx_hash=escrow_channel_id, chain=chain,
                            deposit_usd=deposit_usd,
                        ),
                    }
                self._release_unproven_escrow_squat(escrow_channel_id, chain=chain, claim_id=claim_id)
            return self._insert_channel(
                deposit_cents=deposit_cents, token=token, chain=chain, wallet=wallet,
                tx_hash="", with_secret=with_secret, escrow_channel=escrow_channel_id,
                claim_identifier=claim_id, deposit_usd=deposit_usd, proven=bool(payer_signature),
            )

        # ── The custodial path, and the switch that closes it ───────────────
        # Everything below funds a channel by transferring to the operator's settlement
        # wallet, which makes the balance an operator liability rather than escrowed
        # funds — KI-11's first consequence. `AIMARKET_ESCROW_REQUIRED=1` makes this
        # branch unreachable, so an operator can actually deliver the non-custodial
        # guarantee their contract describes instead of merely offering it as an option.
        # The refusal names what to send, because a client that reaches here has already
        # transferred money and needs to know the deposit was not credited.
        if channels._escrow_required():
            return {
                "error": (
                    "this hub funds channels through AIMarketEscrow only "
                    "(AIMARKET_ESCROW_REQUIRED=1). Open a channel on the contract and "
                    "pass its escrow_channel_id; a transfer to the settlement wallet is "
                    "not credited here and is not held on your behalf."
                )
            }

        # On-chain verification (fail-closed). In stub mode (dev) any tx_hash is
        # accepted — unchanged. With stub OFF and AIFACTORY_PROD=1 we require a
        # real, verified deposit transaction before crediting the channel: the
        # tx must pay the configured recipient the expected amount/token with
        # enough confirmations. If no verifier is reachable, we reject rather
        # than silently credit an unverified tx (PAYAUTH-001).
        # Whether this channel is being funded by a real, on-chain-verified deposit.
        # Only such deposits are single-use-guarded (see consumed_deposits claim
        # below): stub/demo channels carry no real tx to replay.
        verified_onchain = False
        proven_payer = ""  # the wallet whose signature recovered below, and only that
        if not channels._VERIFY_STUB:
            if channels._is_production_mode():
                result = channels._verify_tx_onchain(
                    tx_hash=tx_hash,
                    amount_usd=deposit_usd,
                    chain=chain,
                    token=token,
                )
                if not result.get("ok"):
                    logger.warning(
                        "Rejected channel open for wallet %s: %s",
                        (wallet[:10] or "anonymous"),
                        result.get("error"),
                    )
                    return {"error": result.get("error", "on-chain verification failed")}

                # Bind the deposit to the wallet that ACTUALLY paid (PAYAUTH-003).
                # Every deposit lands in the same platform settlement wallet, so
                # recipient+amount proves only that *someone* paid: without this check
                # anyone watching inbound transfers could quote a stranger's tx hash and
                # have the deposit credited to their own channel.
                payer = str(result.get("sender") or "").strip()
                if not payer:
                    logger.error(
                        "Rejected channel open: verifier confirmed tx %s but reported no "
                        "sender — deposit cannot be bound to a payer",
                        (tx_hash or "")[:12],
                    )
                    return {
                        "error": (
                            "on-chain verification did not report the paying wallet — "
                            "refusing to credit a deposit that cannot be bound to its payer"
                        )
                    }
                claimed = (wallet or "").strip()
                if claimed and not channels._wallet_matches(claimed, payer):
                    logger.warning(
                        "Rejected channel open: deposit tx %s was sent by %s, not by the "
                        "claimed wallet %s",
                        (tx_hash or "")[:12], payer[:10], claimed[:10],
                    )
                    return {
                        "error": (
                            "deposit sender does not match the claimed wallet — a channel "
                            "is credited only to the wallet that paid on-chain"
                        )
                    }
                # Proof of CONTROL, not just of identity (PAYAUTH-003b). The payer's
                # address is public — it is printed in the transaction the claimant is
                # quoting — so "claimed == payer" is satisfied by anyone who read the
                # chain. Whoever calls open() receives the channel_secret, and the
                # invoke path authorizes debits on that secret alone, so without a
                # signature a front-runner spends the victim's whole deposit and the
                # victim is locked out by the single-use guard.
                if channels._allow_unproven_payer():
                    logger.warning(
                        "AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER=1 — crediting deposit %s "
                        "to %s without proof of control (deposit front-running is OPEN)",
                        (tx_hash or "")[:12], payer[:10],
                    )
                elif not channels._is_evm_address(payer):
                    # No proof scheme is implemented for base58/Solana payers; refuse
                    # rather than credit an unproven deposit (mirrors uni_wallet).
                    logger.error(
                        "Rejected channel open: payer %s is not an EVM address and has "
                        "no implemented proof-of-control scheme", payer[:10],
                    )
                    return {
                        "error": (
                            "proof of control over the paying wallet is only implemented "
                            "for EVM addresses — contact the operator"
                        )
                    }
                else:
                    recovered = channels._recover_payer_address(
                        payer=payer, tx_hash=tx_hash, chain=chain,
                        deposit_usd=deposit_usd, signature=payer_signature,
                    )
                    if not recovered or not channels._wallet_matches(recovered, payer):
                        logger.warning(
                            "Rejected channel open: deposit %s claimed for payer %s "
                            "without a valid payer proof (recovered %s)",
                            (tx_hash or "")[:12], payer[:10],
                            (recovered or "none")[:10],
                        )
                        # Hand back the exact text to sign: the challenge is amount- and
                        # tx-bound, so a client that has to reconstruct it by hand gets
                        # it wrong and reads the refusal as "proofs are broken".
                        return {
                            "error": (
                                "missing or invalid payer proof — sign the challenge from "
                                "payer_proof_challenge(payer, tx_hash, chain, deposit_usd) "
                                "with the wallet that paid and resend it as payer_signature"
                            ),
                            "challenge": channels.payer_proof_challenge(
                                payer=payer, tx_hash=tx_hash, chain=chain,
                                deposit_usd=deposit_usd,
                            ),
                        }
                    proven_payer = payer

                # Store the on-chain payer (the verified truth). An empty claim is not a
                # bypass: the channel is bound to the payer, never left anonymous.
                wallet = payer
                verified_onchain = True
            elif not channels._allow_demo_credit():
                # Not production, not stub, not explicitly demo → fail closed. A misconfigured
                # public hub must never credit an unverified deposit (free channels).
                logger.warning("Rejected channel open: unverified deposit and demo credit not allowed")
                return {
                    "error": (
                        "refusing to credit channel without on-chain verification — set "
                        "AIFACTORY_PROD=1 to verify deposits, or AIMARKET_ALLOW_DEMO_CREDIT=1 "
                        "for dev/demo"
                    )
                }

        with self._lock, self._get_conn() as conn:
            # DoS check
            open_count = conn.execute(
                "SELECT COUNT(*) FROM channels WHERE status = 'open'"
            ).fetchone()[0]
            if open_count >= self._max_channels:
                return {"error": "too many open channels, try again later"}

            channel_id = f"ch_{uuid.uuid4().hex[:16]}"
            # Per-channel debit secret — returned ONCE to the owner; only its hash is stored.
            # Debit requires it, so a leaked channel id alone cannot drain the channel.
            channel_secret = secrets.token_urlsafe(24) if with_secret else ""
            secret_hash = channels._hash_secret(channel_secret) if with_secret else ""
            now = channels._now_iso()
            expires = channels._expiry_iso()

            # Single-use deposit guard (PAYAUTH-002). A verified on-chain deposit may
            # fund exactly one channel. Claim (chain, tx_hash) atomically before the
            # channel INSERT so one real deposit can't be replayed to mint unlimited
            # funded channels. SELECT-then-INSERT under self._lock is atomic for the
            # single-process SQLite deployment; the PRIMARY KEY guards the rare
            # multi-process/PG race (its INSERT then fails and we reject cleanly).
            if verified_onchain:
                # Canonical claim key: an EVM hash/chain differing only in case is the
                # SAME deposit, and claiming it verbatim let one transaction fund a new
                # fully-credited channel per capitalisation. The lookup stays
                # case-insensitive (not just the insert) so rows written before this fix
                # still block the replay; base58 Solana ids keep their case, where it is
                # part of the identifier.
                tx = channels._normalize_tx_hash(tx_hash)
                claim_chain = channels._normalize_chain(chain)
                if tx.startswith("0x"):
                    already = conn.execute(
                        "SELECT 1 FROM consumed_deposits "
                        "WHERE LOWER(chain) = ? AND LOWER(tx_hash) = ?",
                        (claim_chain, tx),
                    ).fetchone()
                else:
                    already = conn.execute(
                        "SELECT 1 FROM consumed_deposits "
                        "WHERE LOWER(chain) = ? AND tx_hash = ?",
                        (claim_chain, tx),
                    ).fetchone()
                if already:
                    logger.warning(
                        "Rejected channel open: deposit tx %s on %s already consumed",
                        tx[:12], chain,
                    )
                    return {"error": "deposit transaction already used to fund a channel"}

                # CROSS-STACK single-use (PAYAUTH-002b). consumed_deposits above is
                # THIS ledger's store; the factory's v1 channel door keeps its own. Each
                # enforced single-use over its own rows only, so one real transfer bought
                # a funded channel at BOTH doors — $5 paid, $10 credited. The shared
                # registry is the one record both doors write before crediting, so the
                # claim is exclusive system-wide.
                #
                # Taken BEFORE the local INSERT deliberately: every rejection below this
                # point returns without committing, and a claim taken after a local write
                # would have to unwind one of them. Nothing local is written yet here, so
                # a refusal costs nothing; the two failure paths that CAN still fire after
                # the claim (local race, unexpected error) release it explicitly.
                claim = channels._claim_deposit_shared(
                    chain=chain, tx_hash=tx, channel_id=channel_id,
                    amount_cents=deposit_cents, db_path=self._db_path,
                )
                if not claim.get("ok"):
                    logger.warning(
                        "Rejected channel open: deposit tx %s on %s not claimable (%s)",
                        tx[:12], chain, claim.get("error"),
                    )
                    if claim.get("error") == "deposit_registry_unavailable":
                        return {
                            "error": (
                                "shared deposit registry unavailable — refusing to credit "
                                "a channel that cannot be made exclusive across settlement "
                                "doors (set AIMARKET_DEPOSIT_CLAIMS_DIR)"
                            )
                        }
                    return {"error": "deposit transaction already used to fund a channel"}

                try:
                    conn.execute(
                        "INSERT INTO consumed_deposits "
                        "(chain, tx_hash, channel_id, amount_cents, consumed_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (chain, tx, channel_id, deposit_cents, now),
                    )
                except Exception as exc:  # UNIQUE/PK violation → concurrent claim won
                    channels._release_deposit_shared(
                        chain=chain, tx_hash=tx, channel_id=channel_id,
                        db_path=self._db_path,
                    )
                    msg = str(exc).lower()
                    if any(k in msg for k in ("unique", "constraint", "duplicate")):
                        logger.warning(
                            "Rejected channel open: deposit tx %s on %s already consumed (race)",
                            tx[:12], chain,
                        )
                        return {"error": "deposit transaction already used to fund a channel"}
                    raise

            conn.execute(
                """INSERT INTO channels
                   (channel_id, balance_cents, original_deposit_cents, used_cents,
                    token, chain, wallet, tx_hash, recipient, status,
                    opened_at, expires_at, secret_hash)
                   VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, 'open', ?, ?, ?)""",
                (channel_id, deposit_cents, deposit_cents,
                 token, chain, wallet, tx_hash, channels._RECIPIENT, now, expires,
                 secret_hash),
            )
            if proven_payer:
                self._record_proven_payer(conn, channel_id, proven_payer)
            conn.commit()

        balance_usd = channels._cents_to_dollars(deposit_cents)
        channel: dict[str, Any] = {
            "channel_id": channel_id,
            "balance_usd": balance_usd,
            "original_deposit_usd": balance_usd,
            "used_usd": 0.0,
            "token": token,
            "chain": chain,
            "wallet": wallet,
            "tx_hash": tx_hash,
            "recipient": channels._RECIPIENT,
            "verify_stub": channels._VERIFY_STUB,
            "status": "open",
            "opened_at": now,
            "expires_at": expires,
        }
        if channel_secret:
            # Returned ONCE — the owner must store it and present it on debit
            # (X-Payment-Channel-Secret). Never persisted in plaintext.
            channel["channel_secret"] = channel_secret
        return {"channel": channel}

    # ── Escrow-backed funding (opt-in bridge) ────────────────────────────────

    @staticmethod
    def _ensure_proven_opens(conn) -> None:
        """Ledger channels whose opener proved control of the escrow depositor's wallet.

        Created on first use rather than by a migration: it is a side set read only by the
        squat release below, and the ledger's migration chain is shared with other work."""
        conn.execute("CREATE TABLE IF NOT EXISTS escrow_proven_opens (channel_id TEXT PRIMARY KEY)")

    def _release_unproven_escrow_squat(self, escrow_channel_id: str, *, chain: str, claim_id: str) -> None:
        """Close an open ledger channel on this escrow channel that was opened without a payer
        proof and never charged, and hand its deposit claim back. Anything charged, held or
        proven stays: then the escrow channel is genuinely in use."""
        with self._lock, self._get_conn() as conn:
            self._ensure_proven_opens(conn)
            rows = conn.execute(
                "SELECT channel_id, used_cents, balance_cents, original_deposit_cents "
                "FROM channels WHERE escrow_channel = ? AND status = 'open'",
                (escrow_channel_id,),
            ).fetchall()
            for row in rows:
                cid, used, balance, original = row[0], row[1], row[2], row[3]
                proven = conn.execute(
                    "SELECT 1 FROM escrow_proven_opens WHERE channel_id = ?", (cid,)
                ).fetchone()
                held = conn.execute(
                    "SELECT 1 FROM channel_holds WHERE channel_id = ? AND status = 'held' LIMIT 1", (cid,)
                ).fetchone()
                if proven or used or held or balance != original:
                    continue
                conn.execute(
                    "UPDATE channels SET status = 'superseded', balance_cents = 0 WHERE channel_id = ?",
                    (cid,),
                )
                conn.commit()
                channels._release_deposit_shared(chain=chain, tx_hash=claim_id, channel_id=cid, db_path=self._db_path)
                logger.warning("escrow channel %s: an unproven, unused ledger channel %s was superseded "
                               "by the depositor's proven open", escrow_channel_id[:14], cid)

    def _verify_escrow_funding(
        self, *, escrow_channel_id: str, wallet: str, deposit_usd: float
    ) -> tuple[bool, str, str]:
        """Verify an AIMarketEscrow channel backs this credit. Returns (ok, error, claim_id).

        Fails closed on every axis: the bridge being off, the module being unavailable,
        the chain being unreadable, or the contract's state not matching. None of those
        are reasons to fall back to the transfer path — a caller that supplied an escrow
        channel id is telling us where the money is, and if we cannot confirm it there we
        must not credit at all.
        """
        try:
            from aimarket_hub.escrow_bridge import config as bridge_config
            from aimarket_hub.escrow_bridge import escrow_verify
            from aimarket_hub.escrow_bridge.errors import BridgeError
        except Exception as exc:
            logger.error("escrow-backed open requested but the bridge is unavailable: %s", exc)
            return False, "escrow settlement is not available on this hub", ""

        if not bridge_config.enabled():
            return (
                False,
                "escrow-backed channels are disabled on this hub "
                "(AIMARKET_ESCROW_BRIDGE_ENABLED=0)",
                "",
            )
        try:
            funding = escrow_verify.verify_funding(
                channel_id=escrow_channel_id,
                claimed_wallet=wallet,
                deposit_usd=deposit_usd,
            )
        except BridgeError as exc:
            logger.warning(
                "Rejected escrow-backed open for %s: %s", escrow_channel_id[:14], exc
            )
            return False, str(exc), ""
        return True, "", funding.claim_id

    def _insert_channel(
        self,
        *,
        deposit_cents: int,
        token: str,
        chain: str,
        wallet: str,
        tx_hash: str,
        with_secret: bool,
        escrow_channel: str,
        claim_identifier: str,
        deposit_usd: float,
        proven: bool = False,
    ) -> dict[str, Any]:
        """Create the ledger row for an escrow-backed channel.

        Separate from the transfer path's tail on purpose: the two funding models differ in
        what must be claimed (an escrow channelId, not a tx hash) and in what a refund
        means (the contract's job, not an operator obligation), and entangling them is how
        one model's guard silently stops covering the other.
        """
        with self._lock, self._get_conn() as conn:
            open_count = conn.execute(
                "SELECT COUNT(*) FROM channels WHERE status = 'open'"
            ).fetchone()[0]
            if open_count >= self._max_channels:
                return {"error": "too many open channels, try again later"}

            already = conn.execute(
                "SELECT 1 FROM channels WHERE escrow_channel = ? AND status = 'open'",
                (escrow_channel,),
            ).fetchone()
            if already:
                return {"error": "this escrow channel already backs an open payment channel"}

            channel_id = f"ch_{uuid.uuid4().hex[:16]}"
            channel_secret = secrets.token_urlsafe(24) if with_secret else ""
            secret_hash = channels._hash_secret(channel_secret) if with_secret else ""
            now = channels._now_iso()
            expires = channels._expiry_iso()

            # Same system-wide exclusivity the transfer path gets, keyed on the escrow
            # channelId (namespaced by the bridge so it cannot collide with a tx hash).
            claim = channels._claim_deposit_shared(
                chain=chain, tx_hash=claim_identifier, channel_id=channel_id,
                amount_cents=deposit_cents, db_path=self._db_path,
            )
            if not claim.get("ok"):
                if claim.get("error") == "deposit_registry_unavailable":
                    return {
                        "error": (
                            "shared deposit registry unavailable — refusing to credit a "
                            "channel that cannot be made exclusive across settlement doors"
                        )
                    }
                return {"error": "this escrow channel has already funded a payment channel"}

            try:
                conn.execute(
                    """INSERT INTO channels
                       (channel_id, balance_cents, original_deposit_cents, used_cents,
                        token, chain, wallet, tx_hash, recipient, status,
                        opened_at, expires_at, secret_hash, escrow_channel)
                       VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
                    (channel_id, deposit_cents, deposit_cents, token, chain, wallet,
                     tx_hash, channels._RECIPIENT, now, expires, secret_hash, escrow_channel),
                )
                if proven:
                    self._ensure_proven_opens(conn)
                    conn.execute("INSERT INTO escrow_proven_opens (channel_id) VALUES (?)", (channel_id,))
                    self._record_proven_payer(conn, channel_id, wallet)
                conn.commit()
            except Exception:
                channels._release_deposit_shared(
                    chain=chain, tx_hash=claim_identifier, channel_id=channel_id,
                    db_path=self._db_path,
                )
                raise

        balance_usd = channels._cents_to_dollars(deposit_cents)
        channel: dict[str, Any] = {
            "channel_id": channel_id,
            "balance_usd": balance_usd,
            "original_deposit_usd": balance_usd,
            "used_usd": 0.0,
            "token": token,
            "chain": chain,
            "wallet": wallet,
            "tx_hash": "",
            "recipient": channels._RECIPIENT,
            "verify_stub": False,
            "status": "open",
            "opened_at": now,
            "expires_at": expires,
            "escrow_channel": escrow_channel,
            # Unlike a transfer-funded channel, the remainder here is still the
            # depositor's on chain: they refund it themselves, and no operator debt is
            # recorded at close.
            "refund_source": "escrow_contract",
        }
        if channel_secret:
            channel["channel_secret"] = channel_secret
        return {"channel": channel}

    # ── The payer a channel's opener proved ──────────────────────────────────

    @staticmethod
    def _ensure_proven_payers(conn) -> None:
        """Ledger channels whose opener proved control of the paying wallet, and that wallet.

        Created on first use, like escrow_proven_opens. ``channels.wallet`` is not the same
        thing: a stub or demo-credit open stores whatever wallet the caller typed there.
        This table only ever holds an address a signature recovered at open."""
        conn.execute(
            "CREATE TABLE IF NOT EXISTS channel_proven_payers "
            "(channel_id TEXT PRIMARY KEY, payer TEXT NOT NULL)"
        )

    def _record_proven_payer(self, conn, channel_id: str, payer: str) -> None:
        self._ensure_proven_payers(conn)
        conn.execute(
            "INSERT INTO channel_proven_payers (channel_id, payer) VALUES (?, ?)",
            (channel_id, payer),
        )

    def proven_payer_for(self, channel_id: str) -> str:
        """The wallet that proved it paid for this channel when it was opened, or ""."""
        with self._get_conn() as conn:
            self._ensure_proven_payers(conn)
            row = conn.execute(
                "SELECT payer FROM channel_proven_payers WHERE channel_id = ?", (channel_id,)
            ).fetchone()
        return str(row[0] or "") if row else ""

    def escrow_channel_for(self, channel_id: str) -> str:
        """The escrow channel backing a ledger channel, or "" for a transfer-funded one."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT escrow_channel FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
        if not row:
            return ""
        try:
            return str(row["escrow_channel"] or "")
        except (KeyError, IndexError):  # pre-018 row shape
            return ""

    def close(
        self,
        channel_id: str,
        settle_tx_hash: str = "",
        wallet: str = "",
        secret: str = "",
    ) -> dict[str, Any]:
        """Close a channel and compute settlement.

        Args:
            secret: The required per-channel debit secret returned at open. This is the
                PRIMARY authorization, exactly as in :meth:`debit` and :meth:`hold` — a
                wallet address is public (it is on-chain, and /stats/live labelled paid
                invokes with the channel id), so "present the depositor's address" let any
                stranger who could read or guess it force the channel closed and strand the
                remainder as an obligation. Channels with no stored hash fail closed;
                a public wallet address is not proof of ownership.
            wallet: Must match the wallet that opened the channel. An anonymous channel
                (opened with no wallet — only reachable in stub/demo mode, since an
                on-chain-verified deposit is bound to its payer) has no owner to
                authenticate by address, so the channel secret is still required.

        Settlement is bookkeeping only: `refund_executed_usd` is always 0.0 here and the
        remainder is reported as `refund_owed_usd` plus a durable obligation row.
        """
        if not self._check_rate(
            wallet, self._close_rate, channels._MAX_CLOSES_PER_WALLET_PER_HOUR,
            channels._anon_closes_per_hour(),
        ):
            return {
                "error": (
                    f"rate limit exceeded — max {channels._MAX_CLOSES_PER_WALLET_PER_HOUR} closes "
                    "per hour per wallet"
                )
            }

        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if not row:
                return {"error": "channel not found"}
            if row["status"] != "open":
                return {"error": f"channel is {row['status']}"}

            # The secret is mandatory, including for anonymous and legacy channels.
            # The wallet check below is only defense in depth.
            stored_hash = (row["secret_hash"] if "secret_hash" in row.keys() else "") or ""
            if not stored_hash or not secret or not hmac.compare_digest(stored_hash, channels._hash_secret(secret)):
                return {"error": "unauthorized: invalid or missing channel secret"}

            owner = (row["wallet"] or "").strip()
            claimed = (wallet or "").strip()
            authorized = channels._wallet_matches(owner, claimed) if owner else not claimed
            if not authorized:
                return {"error": "unauthorized: wallet does not match channel owner"}

            # Settle only if still open, in one statement: another hub process may have
            # closed it, or debited it, since the row above was read. The settlement and
            # the obligation are then computed from the row as it is under this write,
            # not from the earlier read — a close racing a debit used to book the whole
            # deposit as owed after part of it was spent.
            now = channels._now_iso()
            if not _move(
                conn,
                "UPDATE channels SET status = 'settled', settle_tx_hash = ?, "
                "closed_at = ? WHERE channel_id = ? AND status = 'open'",
                (settle_tx_hash, now, channel_id),
            ):
                current = conn.execute(
                    "SELECT status FROM channels WHERE channel_id = ?", (channel_id,),
                ).fetchone()
                return {"error": f"channel is {current['status'] if current else 'gone'}"}

            # Outstanding Pay-on-Verified holds must resolve (capture or release)
            # before close — the reserved cents are in neither balance nor used yet,
            # so settling now would strand them. Counted after the status change, so a
            # hold placed by another process just before it is seen here and one placed
            # just after it finds the channel no longer open.
            pending_holds = conn.execute(
                "SELECT COUNT(*) FROM channel_holds "
                "WHERE channel_id = ? AND status = 'held'",
                (channel_id,),
            ).fetchone()[0]
            if pending_holds:
                conn.rollback()
                return {
                    "error": (
                        f"channel has {pending_holds} pending verified settlement(s) — "
                        "retry close after they resolve"
                    )
                }

            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            # The remainder is a DEBT, not a transfer: the deposit was paid to the
            # platform's settlement wallet and this process never sends value.
            obligation = self._record_payout_obligation(
                conn, row, kind="close_remainder", now=now,
            )
            conn.commit()

            used = channels._cents_to_dollars(row["used_cents"])
            refund = channels._cents_to_dollars(row["balance_cents"])
            original = channels._cents_to_dollars(row["original_deposit_cents"])

        return {
            "settlement": {
                "channel_id": channel_id,
                "used_usd": used,
                # Kept for API back-compat: the unspent remainder. It is NOT proof of a
                # transfer — read refund_executed_usd / refund_owed_usd for that.
                "refund_usd": refund,
                "refund_executed_usd": 0.0,
                "refund_owed_usd": refund,
                "refund_status": "owed" if refund > 0 else "none",
                "obligation": obligation,
                "original_deposit_usd": original,
                "status": "settled",
                "settle_tx_hash": settle_tx_hash,
            }
        }


# Imported after the class on purpose: methods read aimarket_hub.channels at call time
# (where its settings and test patches live), and either module may load first.
from aimarket_hub import channels  # noqa: E402
from aimarket_hub.channel_ledger.spending import _move  # noqa: E402
