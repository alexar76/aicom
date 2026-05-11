from __future__ import annotations

import hashlib
import os
import random
import sqlite3
import string
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def _resolve_customer_jwt_secret() -> str:
    """Production: set CUSTOMER_JWT_SECRET or persist file via entrypoint."""
    env = os.environ.get("CUSTOMER_JWT_SECRET", "").strip()
    if env:
        return env
    path = os.environ.get("CUSTOMER_JWT_SECRET_FILE", "/app/data/secrets/customer_jwt.key")
    p = Path(path)
    if p.is_file():
        return p.read_text().strip()
    return hashlib.sha256(os.urandom(32)).hexdigest()


class CommerceService:
    """Persistent commerce primitives: customers, licenses, and downloads."""

    def __init__(self, base_dir: str = "/app/data/store"):
        preferred_base = Path(base_dir)
        fallback_base = Path(os.environ.get("AIFACTORY_DATA_DIR", "./data")) / "store"
        try:
            preferred_base.mkdir(parents=True, exist_ok=True)
            self.base = preferred_base
        except Exception:
            fallback_base.mkdir(parents=True, exist_ok=True)
            self.base = fallback_base
        self.db_path = self.base / "commerce.db"
        self._conn: sqlite3.Connection | None = None
        self.downloads_dir = self.base / "downloads"
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.jwt_secret = _resolve_customer_jwt_secret()
        self.jwt_algorithm = "HS256"
        self.jwt_expiry_seconds = 60 * 60 * 24 * 7  # 7 days
        self._init_db()
        self._migrate_legacy_json()

    def _data_root_for_artifacts(self) -> Path:
        """Root directory containing `store/` and `code/` (matches pipeline output layout)."""
        env = os.environ.get("AIFACTORY_DATA_DIR", "").strip()
        if env:
            return Path(env)
        if self.base.name == "store":
            return self.base.parent
        return Path("./data")

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            # Starlette TestClient (and some ASGI workers) invoke sync route code from a
            # thread pool — allow reuse across threads for this embedded commerce DB.
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_usage (
                customer_id TEXT NOT NULL,
                period_ym TEXT NOT NULL,
                runs_count INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                PRIMARY KEY (customer_id, period_ym)
            )
            """
        )
        # Lightweight migration for older DBs.
        try:
            cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(customers)").fetchall()]
            if "plan" not in cols:
                self.conn.execute("ALTER TABLE customers ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'")
        except Exception:
            pass
        try:
            order_cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(orders)").fetchall()]
            if "referral_source" not in order_cols:
                self.conn.execute("ALTER TABLE orders ADD COLUMN referral_source TEXT")
        except Exception:
            pass
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                payment_id TEXT NOT NULL UNIQUE,
                product_id TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                referral_source TEXT,
                status TEXT NOT NULL,
                license_key TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_referrals (
                customer_id TEXT PRIMARY KEY,
                referral_code TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS licenses (
                license_key TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stripe_checkout_sessions (
                session_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                target_plan TEXT NOT NULL,
                amount_total INTEGER NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                payment_status TEXT NOT NULL,
                idempotency_key TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stripe_webhook_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                session_id TEXT,
                processed_at REAL NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_referral_source ON orders(referral_source)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stripe_sessions_customer_id ON stripe_checkout_sessions(customer_id)"
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_demo_notes (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_customer_demo_notes_customer ON customer_demo_notes(customer_id)"
        )
        self.conn.commit()

    def _migrate_legacy_json(self) -> None:
        customers_file = self.base / "customers.json"
        orders_file = self.base / "orders.json"
        licenses_file = self.base / "licenses.json"
        try:
            existing = self.conn.execute("SELECT COUNT(*) AS cnt FROM customers").fetchone()["cnt"]
            if existing > 0:
                return
            if customers_file.exists():
                import json

                with open(customers_file, "r") as f:
                    customers = json.load(f)
                for email, c in customers.items():
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO customers (id, email, password_hash, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            c.get("id"),
                            email,
                            c.get("password_hash", ""),
                            float(c.get("created_at") or time.time()),
                            float(c.get("updated_at") or time.time()),
                        ),
                    )
            if orders_file.exists():
                import json

                with open(orders_file, "r") as f:
                    orders = json.load(f)
                for o in orders.values():
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO orders
                        (id, customer_id, customer_email, payment_id, product_id, amount, currency, tx_hash, referral_source, status, license_key, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            o.get("id"),
                            o.get("customer_id"),
                            o.get("customer_email", ""),
                            o.get("payment_id"),
                            o.get("product_id"),
                            float(o.get("amount") or 0),
                            o.get("currency", ""),
                            o.get("tx_hash", ""),
                            o.get("referral_source"),
                            o.get("status", "paid"),
                            o.get("license_key", ""),
                            float(o.get("created_at") or time.time()),
                        ),
                    )
            if licenses_file.exists():
                import json

                with open(licenses_file, "r") as f:
                    licenses = json.load(f)
                for lic in licenses.values():
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO licenses
                        (license_key, order_id, customer_id, product_id, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            lic.get("license_key"),
                            lic.get("order_id"),
                            lic.get("customer_id"),
                            lic.get("product_id"),
                            lic.get("status", "active"),
                            float(lic.get("created_at") or time.time()),
                        ),
                    )
            self.conn.commit()
        except Exception:
            # Migration is best-effort; service must remain operational.
            self.conn.rollback()

    def _norm_email(self, email: str) -> str:
        return email.strip().lower()

    def register_customer(self, email: str, password: str) -> dict:
        email = self._norm_email(email)
        existing = self.conn.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
        if existing is not None:
            raise ValueError("Customer with this email already exists")
        customer_id = f"cust-{uuid.uuid4().hex[:12]}"
        now = time.time()
        self.conn.execute(
            """
            INSERT INTO customers (id, email, password_hash, plan, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (customer_id, email, pwd_context.hash(password), "free", now, now),
        )
        self.conn.commit()
        return {"id": customer_id, "email": email, "plan": "free", "created_at": now}

    def authenticate_customer(self, email: str, password: str) -> Optional[dict]:
        email = self._norm_email(email)
        customer = self.conn.execute(
            "SELECT id, email, password_hash, plan FROM customers WHERE email = ?",
            (email,),
        ).fetchone()
        if customer is None:
            return None
        if not pwd_context.verify(password, customer["password_hash"]):
            return None
        return {"id": customer["id"], "email": customer["email"], "plan": customer["plan"] or "free"}

    def create_token(self, customer_id: str, email: str) -> str:
        profile = self.get_customer(customer_id)
        plan = (profile or {}).get("plan") or "free"
        now = int(time.time())
        payload = {
            "sub": customer_id,
            "email": email,
            "plan": plan,
            "iat": now,
            "exp": now + self.jwt_expiry_seconds,
            "jti": uuid.uuid4().hex[:16],
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def get_customer(self, customer_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT id, email, plan, created_at, updated_at FROM customers WHERE id = ?",
            (customer_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_customer_plan(self, customer_id: str, plan: str) -> bool:
        plan_norm = (plan or "free").strip().lower()
        if plan_norm not in {"free", "maker", "studio", "enterprise"}:
            return False
        now = time.time()
        cur = self.conn.execute(
            "UPDATE customers SET plan = ?, updated_at = ? WHERE id = ?",
            (plan_norm, now, customer_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_customer_by_email(self, email: str) -> Optional[dict]:
        email = self._norm_email(email)
        row = self.conn.execute(
            "SELECT id, email, plan, created_at, updated_at FROM customers WHERE email = ?",
            (email,),
        ).fetchone()
        return dict(row) if row else None

    def _generate_referral_code(self, email: str) -> str:
        seed = "".join(ch for ch in email.lower() if ch.isalnum())[:10] or "creator"
        suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
        return f"af-{seed}-{suffix}"[:32]

    def get_or_create_referral_code(self, customer_id: str, customer_email: str) -> str:
        existing = self.conn.execute(
            "SELECT referral_code FROM customer_referrals WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        if existing is not None:
            return str(existing["referral_code"])
        now = time.time()
        for _ in range(16):
            code = self._generate_referral_code(customer_email)
            taken = self.conn.execute(
                "SELECT customer_id FROM customer_referrals WHERE referral_code = ?",
                (code,),
            ).fetchone()
            if taken is None:
                self.conn.execute(
                    """
                    INSERT INTO customer_referrals (customer_id, referral_code, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (customer_id, code, now, now),
                )
                self.conn.commit()
                return code
        fallback = f"af-{customer_id[-8:]}"
        self.conn.execute(
            """
            INSERT OR REPLACE INTO customer_referrals (customer_id, referral_code, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (customer_id, fallback, now, now),
        )
        self.conn.commit()
        return fallback

    def get_referral_stats(self, customer_id: str, customer_email: str) -> dict:
        code = self.get_or_create_referral_code(customer_id, customer_email)
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS conversions, COALESCE(SUM(amount), 0) AS revenue
            FROM orders
            WHERE referral_source = ?
            """,
            (code,),
        ).fetchone()
        conversions = int(row["conversions"]) if row and row["conversions"] is not None else 0
        revenue = float(row["revenue"]) if row and row["revenue"] is not None else 0.0
        return {
            "referral_code": code,
            "conversions": conversions,
            "attributed_revenue": round(revenue, 2),
            "share_link": f"https://aifactory.dev/?ref={code}",
        }

    def save_stripe_checkout_session(
        self,
        session_id: str,
        customer_id: str,
        customer_email: str,
        target_plan: str,
        amount_total: int,
        currency: str,
        status: str,
        payment_status: str,
        idempotency_key: str | None = None,
    ) -> None:
        now = time.time()
        self.conn.execute(
            """
            INSERT INTO stripe_checkout_sessions
            (session_id, customer_id, customer_email, target_plan, amount_total, currency, status, payment_status, idempotency_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              status = excluded.status,
              payment_status = excluded.payment_status,
              updated_at = excluded.updated_at
            """,
            (
                session_id,
                customer_id,
                self._norm_email(customer_email),
                (target_plan or "maker").strip().lower(),
                int(amount_total),
                (currency or "usd").strip().lower(),
                status,
                payment_status,
                idempotency_key,
                now,
                now,
            ),
        )
        self.conn.commit()

    def apply_stripe_webhook_event(
        self,
        event_id: str,
        event_type: str,
        session_id: str,
        payment_status: str,
        session_status: str,
        customer_email: str | None = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        now = time.time()
        existing = self.conn.execute(
            "SELECT event_id FROM stripe_webhook_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if existing is not None:
            return {"already_processed": True, "plan_upgraded": False}

        session = self.conn.execute(
            "SELECT * FROM stripe_checkout_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        customer_id = None
        target_plan = "maker"
        if session is not None:
            customer_id = session["customer_id"]
            target_plan = session["target_plan"] or "maker"
        else:
            md = metadata or {}
            customer_id = md.get("customer_id")
            target_plan = str(md.get("target_plan") or "maker")
            if not customer_id and customer_email:
                customer = self.get_customer_by_email(customer_email)
                customer_id = (customer or {}).get("id")
            if customer_id:
                self.save_stripe_checkout_session(
                    session_id=session_id,
                    customer_id=customer_id,
                    customer_email=customer_email or "",
                    target_plan=target_plan,
                    amount_total=0,
                    currency="usd",
                    status=session_status,
                    payment_status=payment_status,
                    idempotency_key=None,
                )

        self.conn.execute(
            """
            INSERT INTO stripe_webhook_events (event_id, event_type, session_id, processed_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_id, event_type, session_id, now),
        )
        self.conn.execute(
            """
            UPDATE stripe_checkout_sessions
            SET status = ?, payment_status = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (session_status, payment_status, now, session_id),
        )

        plan_upgraded = False
        if payment_status == "paid" and customer_id:
            plan_upgraded = self.set_customer_plan(customer_id, target_plan)

        self.conn.commit()
        return {"already_processed": False, "plan_upgraded": plan_upgraded}

    def get_monthly_run_usage(self, customer_id: str, ts: Optional[float] = None) -> dict:
        now = ts or time.time()
        period_ym = time.strftime("%Y-%m", time.gmtime(now))
        row = self.conn.execute(
            "SELECT runs_count FROM customer_usage WHERE customer_id = ? AND period_ym = ?",
            (customer_id, period_ym),
        ).fetchone()
        runs = int(row["runs_count"]) if row else 0
        return {"period_ym": period_ym, "runs_count": runs}

    def consume_monthly_run(self, customer_id: str, limit: int, ts: Optional[float] = None) -> dict:
        now = ts or time.time()
        period_ym = time.strftime("%Y-%m", time.gmtime(now))
        current = self.get_monthly_run_usage(customer_id, now)
        used = int(current.get("runs_count", 0))
        allowed = used < max(0, int(limit))
        if allowed:
            self.conn.execute(
                """
                INSERT INTO customer_usage (customer_id, period_ym, runs_count, updated_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(customer_id, period_ym)
                DO UPDATE SET runs_count = runs_count + 1, updated_at = excluded.updated_at
                """,
                (customer_id, period_ym, now),
            )
            self.conn.commit()
            used += 1
        return {
            "allowed": allowed,
            "limit": int(limit),
            "used_after": used,
            "remaining": max(0, int(limit) - used),
            "period_ym": period_ym,
        }

    def decode_token(self, token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
        except JWTError:
            return None

    def create_order_and_license(
        self,
        customer_id: str,
        customer_email: str,
        payment_id: str,
        product_id: str,
        amount: float,
        currency: str,
        tx_hash: str,
        referral_source: str | None = None,
    ) -> dict:
        existing = self.conn.execute(
            "SELECT * FROM orders WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if existing is not None:
            return dict(existing)

        order_id = f"ord-{uuid.uuid4().hex[:12]}"
        license_key = f"lic-{uuid.uuid4().hex}-{uuid.uuid4().hex[:8]}"
        now = time.time()
        order = {
            "id": order_id,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "payment_id": payment_id,
            "product_id": product_id,
            "amount": amount,
            "currency": currency,
            "tx_hash": tx_hash,
            "referral_source": referral_source,
            "status": "paid",
            "license_key": license_key,
            "created_at": now,
        }
        self.conn.execute(
            """
            INSERT INTO orders
            (id, customer_id, customer_email, payment_id, product_id, amount, currency, tx_hash, referral_source, status, license_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                customer_id,
                customer_email,
                payment_id,
                product_id,
                amount,
                currency,
                tx_hash,
                referral_source,
                "paid",
                license_key,
                now,
            ),
        )
        self.conn.execute(
            """
            INSERT INTO licenses
            (license_key, order_id, customer_id, product_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (license_key, order_id, customer_id, product_id, "active", now),
        )
        self.conn.commit()
        return order

    def get_orders_for_customer(self, customer_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC",
            (customer_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def build_download_archive(self, order: dict) -> Path:
        product_id = order["product_id"]
        source_dir = self._data_root_for_artifacts() / "code" / product_id
        if not source_dir.exists():
            raise FileNotFoundError("Generated product files are missing")
        archive_name = f"{order['id']}-{product_id}.zip"
        archive_path = self.downloads_dir / archive_name
        if archive_path.exists():
            return archive_path
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in source_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=path.relative_to(source_dir))
            readme = (
                f"Order: {order['id']}\n"
                f"Product: {product_id}\n"
                f"License: {order['license_key']}\n"
            )
            zf.writestr("LICENSE.txt", readme)
        return archive_path

    # --- Demo notes (E2E / teaching CRUD; scoped per customer) -----------------

    def create_demo_note(self, customer_id: str, title: str, body: str) -> dict:
        note_id = f"note-{uuid.uuid4().hex[:12]}"
        now = time.time()
        t = (title or "").strip()[:500]
        b = (body or "").strip()[:8000]
        if len(t) < 1:
            raise ValueError("title_required")
        self.conn.execute(
            """
            INSERT INTO customer_demo_notes (id, customer_id, title, body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (note_id, customer_id, t, b, now, now),
        )
        self.conn.commit()
        return {"id": note_id, "customer_id": customer_id, "title": t, "body": b, "created_at": now, "updated_at": now}

    def list_demo_notes(self, customer_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT id, customer_id, title, body, created_at, updated_at
            FROM customer_demo_notes
            WHERE customer_id = ?
            ORDER BY updated_at DESC
            """,
            (customer_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_demo_note(self, customer_id: str, note_id: str, title: str | None, body: str | None) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT id FROM customer_demo_notes WHERE id = ? AND customer_id = ?",
            (note_id, customer_id),
        ).fetchone()
        if row is None:
            return None
        cur = self.conn.execute(
            "SELECT title, body FROM customer_demo_notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        new_title = (title.strip()[:500] if title is not None else cur["title"])
        new_body = (body.strip()[:8000] if body is not None else cur["body"])
        if isinstance(title, str) and len(new_title) < 1:
            raise ValueError("title_required")
        now = time.time()
        self.conn.execute(
            """
            UPDATE customer_demo_notes
            SET title = ?, body = ?, updated_at = ?
            WHERE id = ? AND customer_id = ?
            """,
            (new_title, new_body, now, note_id, customer_id),
        )
        self.conn.commit()
        return {
            "id": note_id,
            "customer_id": customer_id,
            "title": new_title,
            "body": new_body,
            "updated_at": now,
        }

    def delete_demo_note(self, customer_id: str, note_id: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM customer_demo_notes WHERE id = ? AND customer_id = ?",
            (note_id, customer_id),
        )
        self.conn.commit()
        return cur.rowcount > 0
