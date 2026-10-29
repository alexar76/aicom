from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import time

import streamlit as st

from skopos.auth_store import (
    clear_login_lockout,
    dashboard_password_configured,
    login_lockout_remaining_seconds,
    login_pace_seconds,
    password_expired,
    password_expires_in_days,
    register_failed_login,
    session_secret_material,
    verify_dashboard_password,
)
from skopos.i18n import t
from skopos.password_policy import configured_password_meets_policy, min_password_length

_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300

# Browser-persistent "remember me" — a signed cookie so a page refresh keeps the
# operator logged in until the TTL, instead of dropping them at the gate every
# reload (st.session_state alone dies with the websocket). The cookie is bound to
# the current credential via session_secret_material(), so rotating the password
# invalidates every outstanding cookie.
_COOKIE_NAME = "skopos_session"


def dashboard_auth_required() -> bool:
    """Fail closed in production: fleet pages need a configured password."""
    return os.environ.get("SKOPOS_REQUIRE_DASHBOARD_AUTH", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _websocket_peer() -> str | None:
    """The websocket's socket peer, before any forwarded-header middleware.

    Streamlit's Starlette client keeps Uvicorn's bound ASGI receive method. Its
    transport retains the actual peer even when Uvicorn has replaced scope["client"]
    from X-Forwarded-For. Neither st.context.ip_address nor client_context.remote_ip
    can establish proxy trust. If the server adapter changes, fail closed rather
    than recovering an address from client-supplied headers.
    """
    try:
        from streamlit import runtime
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is None or not runtime.exists():
            return None
        client = runtime.get_instance().get_client(ctx.session_id)
        websocket = getattr(client, "_websocket", None)
        receive = getattr(websocket, "_receive", None)
        protocol = getattr(receive, "__self__", None)
        transport = getattr(protocol, "transport", None)
        peer = transport.get_extra_info("peername") if transport is not None else None
        if not isinstance(peer, tuple) or not peer or not isinstance(peer[0], str):
            return None
        return str(ipaddress.ip_address(peer[0]))
    except Exception:
        return None


def _client_ip() -> str:
    """Key login budgets by the socket peer, or by its trusted proxy's headers.

    Unknown peers share one bucket; headers cannot establish their identity or
    claim a recently successful address's exemption from login pacing.
    """
    from skopos.client_ip import resolve

    peer = _websocket_peer()
    if not peer:
        return "unknown"
    try:
        headers = getattr(getattr(st, "context", None), "headers", None)

        def _h(name: str):
            if headers is not None:
                return headers.get(name) or headers.get(name.lower())
            return None

        return resolve(peer, _h)
    except Exception:
        return peer


def _token_secret() -> bytes:
    return hashlib.sha256(b"skopos-session-v1|" + session_secret_material()).digest()


def _sign_token(exp: int) -> str:
    sig = hmac.new(_token_secret(), f"v1:{exp}".encode("ascii"), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _token_valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp_s, sig = token.split(".", 1)
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if exp <= int(time.time()):
        return False
    expected = hmac.new(_token_secret(), f"v1:{exp}".encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _read_session_cookie() -> str | None:
    try:
        return st.context.cookies.get(_COOKIE_NAME)  # populated from the page-load request
    except Exception:
        return None


def _emit_cookie_js(script_body: str) -> None:
    """Run a tiny script in the PARENT document (Streamlit component iframe)."""
    import streamlit.components.v1 as components

    components.html(f"<script>{script_body}</script>", height=0, width=0)


def _write_session_cookie(ttl: float) -> None:
    token = _sign_token(int(time.time() + ttl))
    max_age = int(ttl)
    _emit_cookie_js(
        "(function(){try{var w=window.parent||window;var d=w.document;"
        "var sec=(w.location&&w.location.protocol==='https:')?'; Secure':'';"
        f"d.cookie={json.dumps(_COOKIE_NAME + '=' + token + '; Max-Age=' + str(max_age) + '; Path=/; SameSite=Lax')}+sec;"
        "}catch(e){}})();"
    )


def _clear_session_cookie() -> None:
    _emit_cookie_js(
        "(function(){try{var d=(window.parent||window).document;"
        f"d.cookie={json.dumps(_COOKIE_NAME + '=; Max-Age=0; Path=/; SameSite=Lax')};"
        "}catch(e){}})();"
    )


def _restore_session_from_cookie() -> None:
    """Auto-authenticate a fresh page load from a valid remember-me cookie."""
    if st.session_state.get("_skopos_auth_ok"):
        return
    # A logout is mid-flight: the cookie is still in the browser (cleared on the
    # gate render this same run) — must NOT re-authenticate from it.
    if st.session_state.get("_skopos_logout_cookie"):
        return
    token = _read_session_cookie()
    if not _token_valid(token):
        return
    exp = int(token.split(".", 1)[0])
    st.session_state._skopos_auth_ok = True
    # Anchor the session clock to the cookie's issue time so the in-app TTL and the
    # cookie expiry agree.
    st.session_state._skopos_auth_at = exp - _session_ttl_seconds()
    st.session_state._skopos_auth_attempts = 0


def _session_ttl_seconds() -> float:
    try:
        hours = float(os.environ.get("SKOPOS_DASHBOARD_SESSION_HOURS", "12"))
    except ValueError:
        hours = 12.0
    return max(0.25, hours) * 3600


def dashboard_password_set() -> bool:
    """True when a password is configured — DB hash (preferred) or legacy env var."""
    return dashboard_password_configured()


def is_documentation_page() -> bool:
    """True when the active Streamlit script is the in-app Documentation page."""
    import inspect

    for frame in inspect.stack():
        path = str(getattr(frame, "filename", "") or "").replace("\\", "/")
        if "4_Documentation" in path or path.endswith("/pages/4_Documentation.py"):
            return True

    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is None:
            return False
        main = str(getattr(ctx, "main_script_path", "") or "").replace("\\", "/")
        return "4_Documentation" in main or "Documentation.py" in main
    except Exception:
        return False


def is_dashboard_authenticated() -> bool:
    """True when the user passed the login gate (or auth is disabled)."""
    if not dashboard_password_set():
        return not dashboard_auth_required()
    if not st.session_state.get("_skopos_auth_ok"):
        return False
    if _session_expired():
        clear_dashboard_auth()
        return False
    return True


def clear_dashboard_auth() -> None:
    for key in (
        "_skopos_auth_ok",
        "_skopos_auth_at",
        "_skopos_auth_attempts",
        "_skopos_auth_lock_until",
    ):
        st.session_state.pop(key, None)


def _session_expired() -> bool:
    auth_at = st.session_state.get("_skopos_auth_at")
    if auth_at is None:
        return False
    return (time.time() - float(auth_at)) > _session_ttl_seconds()


def _check_login_lockout(locale: str) -> None:
    remaining = login_lockout_remaining_seconds(_client_ip())
    if remaining <= 0:
        # Legacy per-tab lockout (kept as defense-in-depth for this session).
        lock_until = float(st.session_state.get("_skopos_auth_lock_until") or 0)
        if time.time() < lock_until:
            remaining = max(1, int(lock_until - time.time()))
        else:
            return
    st.error(t("auth.lockout", locale, seconds=remaining))
    st.stop()


def _pace_login_attempt(locale: str) -> None:
    """Delay this submitted attempt once, without letting other failures postpone it.

    A shared ``until`` checked before rendering the form was still a global lockout:
    another address could move it forward before the operator reached password verification
    (GCVE-110-VULN-PYPI-2026-000644). Snapshot the bounded delay at admission instead. The
    monotonic deadline belongs to this invocation and is never extended by later failures.
    Passwords stay in the submitting call, rather than being copied into pending state.
    """
    pace = login_pace_seconds(_client_ip())
    if pace <= 0:
        return
    deadline = time.monotonic() + pace
    st.info(t("auth.slowed", locale, seconds=pace))
    while (remaining := deadline - time.monotonic()) > 0:
        time.sleep(remaining)


def _register_failed_login(locale: str) -> None:
    locked_for = register_failed_login(_client_ip())
    attempts = int(st.session_state.get("_skopos_auth_attempts") or 0) + 1
    st.session_state._skopos_auth_attempts = attempts
    if locked_for > 0:
        st.session_state._skopos_auth_lock_until = time.time() + locked_for
        st.session_state._skopos_auth_attempts = 0
        st.warning(t("auth.lockout_started", locale, seconds=locked_for))
        return
    if attempts >= _MAX_LOGIN_ATTEMPTS:
        st.session_state._skopos_auth_lock_until = time.time() + _LOCKOUT_SECONDS
        st.session_state._skopos_auth_attempts = 0
        st.warning(t("auth.lockout_started", locale, seconds=_LOCKOUT_SECONDS))


def _render_login_gate(locale: str) -> None:
    from skopos.themes import build_login_gate_css, get_active_theme

    th = get_active_theme()
    st.markdown(build_login_gate_css(th), unsafe_allow_html=True)
    st.markdown('<div class="skopos-login-page-marker" aria-hidden="true"></div>', unsafe_allow_html=True)

    st.markdown(f"### 🔐 {t('auth.title', locale)}")
    st.caption(t("auth.subtitle", locale))

    with st.expander(t("auth.password_requirements_intro", locale), expanded=False):
        st.caption(t("auth.policy.min_length", locale, min=min_password_length()))
        st.caption(t("auth.policy.has_letter", locale))
        st.caption(t("auth.policy.has_digit", locale))
        st.caption(t("auth.policy.not_weak", locale))

    with st.form("stats_login", clear_on_submit=False):
        pwd = st.text_input(
            t("auth.password", locale),
            type="password",
            autocomplete="current-password",
            placeholder=t("auth.password_placeholder", locale),
        )
        submitted = st.form_submit_button(t("auth.login", locale), type="primary", use_container_width=True)
        if submitted:
            _pace_login_attempt(locale)
            # Another attempt from this address may have exhausted its own budget while
            # this one waited. Failures from other addresses cannot close this gate.
            _check_login_lockout(locale)
            if verify_dashboard_password(pwd):
                clear_login_lockout(_client_ip())
                st.session_state._skopos_auth_ok = True
                st.session_state._skopos_auth_at = time.time()
                st.session_state._skopos_auth_attempts = 0
                st.session_state.pop("_skopos_auth_lock_until", None)
                # Persist a remember-me cookie on the next (authed) run so a
                # refresh doesn't drop back to the gate.
                st.session_state._skopos_persist_cookie = True
                st.rerun()
            _register_failed_login(locale)
            st.error(t("auth.invalid", locale))


def _warn_password_rotation(locale: str) -> None:
    """Nudge authenticated admins when the password is expired / expiring soon."""
    try:
        remaining = password_expires_in_days()
    except Exception:
        return
    if remaining is None:
        return
    if password_expired():
        st.sidebar.error(t("auth.expired", locale, days=int(abs(remaining))))
    elif remaining <= 7:
        st.sidebar.warning(t("auth.expiring_soon", locale, days=int(remaining)))


def require_dashboard_auth(locale: str = "en") -> bool:
    """Gate the dashboard when a password is configured (DB hash or env var).

    The Documentation page is always public (operator guides, no fleet data).
    When ``SKOPOS_REQUIRE_DASHBOARD_AUTH`` is on (default), a missing password
    blocks the fleet UI until one is set — production must not stay open.
    """
    if is_documentation_page():
        return True

    if not dashboard_password_configured():
        if dashboard_auth_required():
            from skopos.ui_password_gate import maybe_prompt_password_setup

            maybe_prompt_password_setup(locale, allow_dismiss=False)
            st.stop()
            return False
        return True

    # A fresh page load re-authenticates from a valid remember-me cookie.
    _restore_session_from_cookie()

    if st.session_state.get("_skopos_auth_ok"):
        if _session_expired():
            clear_dashboard_auth()
            _clear_session_cookie()
            st.info(t("auth.session_expired", locale))
        else:
            # Write / refresh the cookie once after a successful login (sliding
            # TTL is intentional — activity keeps the session alive).
            if st.session_state.pop("_skopos_persist_cookie", False):
                _write_session_cookie(_session_ttl_seconds())
            _warn_password_rotation(locale)
            return True

    # Landed on the gate — if we just logged out, clear the cookie here.
    if st.session_state.pop("_skopos_logout_cookie", False):
        _clear_session_cookie()

    _check_login_lockout(locale)

    policy_ok, _ = configured_password_meets_policy()
    if not policy_ok:
        st.warning(t("auth.weak_current_password", locale))

    _render_login_gate(locale)
    st.stop()
    return False


def render_logout_button(*, locale: str) -> None:
    if not dashboard_password_set():
        return
    if not st.session_state.get("_skopos_auth_ok"):
        return
    ttl = _session_ttl_seconds()
    auth_at = st.session_state.get("_skopos_auth_at")
    if auth_at is not None:
        remaining_h = max(0.0, (float(auth_at) + ttl - time.time()) / 3600)
        st.sidebar.caption(t("auth.session_remaining", locale, hours=f"{remaining_h:.1f}"))
    if st.sidebar.button(f"🚪 {t('auth.logout', locale)}", use_container_width=True, type="secondary"):
        clear_dashboard_auth()
        # Drop the remember-me cookie too, else the next load would silently
        # re-authenticate from it.
        st.session_state._skopos_logout_cookie = True
        st.rerun()
