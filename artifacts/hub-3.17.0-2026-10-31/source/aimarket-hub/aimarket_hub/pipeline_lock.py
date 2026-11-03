"""Host-local locking and durable wallet ownership across separate order files."""
import hashlib
import json
import os
import time
from pathlib import Path


class FileLock:
    def __init__(self, path):
        path = Path(path)
        if path.is_symlink():
            raise ValueError("lock file cannot be a symlink")
        self.fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(self.fd).st_size == 0:
                    os.write(self.fd, b"0")
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.fd)
            raise ValueError("another client is using this recovery file or wallet") from exc

    def close(self):
        os.close(self.fd)


async def wallet_lease(state, state_path, save, client, rpc):
    """Reserve the wallet until this bundle completes. Never silently steal a lease."""
    root = Path(os.environ.get("AIMARKET_WALLET_STATE_DIR", str(Path.home()/".aimarket"/"wallets")))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = hashlib.sha256((str(state["quote"]["offers"][0]["terms"]["chain_id"])+":" + state["wallet"].lower()).encode()).hexdigest()
    path = root / (identity + ".json")
    lock = FileLock(str(path) + ".lock")
    try:
        if path.is_symlink():
            raise ValueError("wallet lease cannot be a symlink")
        owner = json.loads(path.read_text()) if path.exists() else {}
        current = str(state_path)
        if owner.get("state_path") not in (None, current):
            previous = Path(owner["state_path"])
            old = json.loads(previous.read_text()) if previous.is_file() else {}
            # Only a verified completed success consumes the entire signed nonce sequence.
            released = old.get("phase") == "completed" and old.get("verified") and old.get("result", {}).get("success")
            if not released and old.get("phase") in (None, "preparing", "prepared") and not old.get("tx_hashes"):
                # It never signed a transaction: no wallet nonce or authorization is outstanding.
                released = True
            if not released and old.get("rpc_url") and old.get("quote", {}).get("offers"):
                # Whatever phase it stopped in — a failed delivery, or a submit the Hub refused
                # (quote or invoice expired) and the order never reached a terminal answer — its
                # signed nonces are spent or harmless once all were consumed, or once every
                # authorization expired with nothing pending. Before, only a completed order was
                # checked, so a refused submit held the wallet forever.
                pending = int(await rpc(client, old["rpc_url"], "eth_getTransactionCount", [old["wallet"], "pending"]), 16)
                latest = int(await rpc(client, old["rpc_url"], "eth_getTransactionCount", [old["wallet"], "latest"]), 16)
                offers = old["quote"]["offers"]
                consumed = old.get("nonce_start") is not None and latest >= old["nonce_start"] + len(offers)
                expired = all(time.time() > o["invoice"]["expires_at"] + 30 for o in offers)
                released = pending == latest and (consumed or expired)
            if not released:
                raise ValueError(f"wallet reserved by another order; resume {owner['state_path']}; after terminal failure wait for authorizations to expire")
        save(path, {"state_path": current, "wallet": state["wallet"]})
        return lock, path
    except BaseException:
        lock.close()
        raise
