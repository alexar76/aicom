"""Dashboard password settings UI (admin panel + wizard).

Passwords set here are hashed (PBKDF2) and stored in the database — only the
hash is persisted, never the plaintext. The legacy ``SKOPOS_DASHBOARD_PASSWORD``
env var is still honoured for bootstrap, but saving here supersedes it and the
plaintext line is stripped from ``.env``.
"""

from __future__ import annotations

import os

import streamlit as st

from skopos.app_auth import clear_dashboard_auth
from skopos.auth_store import (
    clear_dashboard_password,
    generate_strong_password,
    password_age_days,
    password_expires_in_days,
    password_max_age_days,
    password_source,
    set_dashboard_password,
)
from skopos.config import load_app_env
from skopos.env_io import remove_env_var, upsert_env_var
from skopos.i18n import t
from skopos.password_policy import (
    configured_password_meets_policy,
    min_password_length,
    password_rules,
    validate_dashboard_password,
)


def _rule_caption(locale: str, key: str) -> str:
    if key == "auth.policy.min_length":
        return t("auth.policy.min_length", locale, min=min_password_length())
    return t(key, locale)


def render_password_requirements(locale: str, password: str = "") -> None:
    rules = password_rules(password)
    for rule in rules:
        icon = "✅" if rule.passed else "⬜"
        st.caption(f"{icon} {_rule_caption(locale, rule.key)}")


def _persist_session_hours(session_hours: float | None) -> None:
    if session_hours is None:
        return
    hours = max(0.25, min(168.0, float(session_hours)))
    upsert_env_var("SKOPOS_DASHBOARD_SESSION_HOURS", str(hours))
    load_app_env()


def save_dashboard_password(
    new_password: str,
    *,
    session_hours: float | None = None,
    clear: bool = False,
) -> tuple[bool, str]:
    """Store only the salted hash in the DB. Clearing removes hash + env plaintext."""
    if clear:
        clear_dashboard_password()
        remove_env_var("SKOPOS_DASHBOARD_PASSWORD")
        load_app_env()
        clear_dashboard_auth()
        return True, "auth.password_cleared"

    ok, failed = validate_dashboard_password(new_password)
    if not ok:
        return False, failed[0]

    set_dashboard_password(new_password)
    # Drop any legacy plaintext so the DB hash is the single source of truth.
    remove_env_var("SKOPOS_DASHBOARD_PASSWORD")
    _persist_session_hours(session_hours)
    load_app_env()
    clear_dashboard_auth()
    return True, "auth.password_saved"


def _render_status(locale: str) -> None:
    source = password_source()
    max_age = password_max_age_days()
    if source == "none":
        st.error(t("auth.status_open", locale))
        return

    policy_ok, _ = configured_password_meets_policy()
    if source == "db":
        label = t("auth.status_protected_hashed", locale)
    else:
        label = t("auth.status_protected_env", locale)
    (st.success if policy_ok else st.warning)(label)

    if source == "db" and max_age > 0:
        remaining = password_expires_in_days()
        age = password_age_days()
        if remaining is not None:
            if remaining < 0:
                st.error(t("auth.expired", locale, days=int(abs(remaining))))
            elif remaining <= 7:
                st.warning(t("auth.expiring_soon", locale, days=int(remaining)))
            else:
                st.caption(
                    t(
                        "auth.age_status",
                        locale,
                        age=int(age or 0),
                        remaining=int(remaining),
                    )
                )
    elif source == "db":
        st.caption(t("auth.expiry_disabled", locale))


def _render_generated_reveal(locale: str, key_prefix: str) -> None:
    reveal_key = f"{key_prefix}_generated_password"
    generated = st.session_state.get(reveal_key)
    if not generated:
        return
    st.success(t("auth.generated_saved", locale))
    st.code(generated, language=None)
    st.caption(t("auth.generated_copy_hint", locale))
    if st.button(t("auth.generated_dismiss", locale), key=f"{key_prefix}_dismiss_generated"):
        st.session_state.pop(reveal_key, None)
        st.rerun()


def render_dashboard_auth_settings(locale: str, *, key_prefix: str = "settings") -> None:
    """Password set/change/regenerate block for admin (Fleet) and the wizard."""
    _render_status(locale)
    _render_generated_reveal(locale, key_prefix)

    try:
        session_hours = float(os.environ.get("SKOPOS_DASHBOARD_SESSION_HOURS", "12"))
    except ValueError:
        session_hours = 12.0

    new_session_hours = st.number_input(
        t("auth.session_hours", locale),
        min_value=0.25,
        max_value=168.0,
        value=float(session_hours),
        step=0.5,
        help=t("auth.session_hours_help", locale),
        key=f"{key_prefix}_dashboard_session_hours",
    )

    st.caption(t("auth.password_requirements_intro", locale))
    render_password_requirements(locale)

    with st.form(f"{key_prefix}_dashboard_password_form", clear_on_submit=False):
        pwd1 = st.text_input(t("auth.new_password", locale), type="password")
        pwd2 = st.text_input(t("auth.confirm_password", locale), type="password")
        if pwd1:
            render_password_requirements(locale, pwd1)

        c1, c2 = st.columns(2)
        with c1:
            save_btn = st.form_submit_button(
                t("auth.save_password", locale), type="primary", use_container_width=True
            )
        with c2:
            clear_btn = st.form_submit_button(t("auth.clear_password", locale), use_container_width=True)

        if save_btn:
            if not pwd1:
                st.error(t("auth.password_empty", locale))
            elif pwd1 != pwd2:
                st.error(t("auth.password_mismatch", locale))
            else:
                ok, msg_key = save_dashboard_password(pwd1, session_hours=new_session_hours)
                if ok:
                    st.session_state.pop(f"{key_prefix}_generated_password", None)
                    st.success(t(msg_key, locale))
                    st.rerun()
                else:
                    st.error(_rule_caption(locale, msg_key))

        if clear_btn:
            from skopos.app_auth import dashboard_auth_required

            if dashboard_auth_required():
                st.error(t("auth.clear_blocked_when_required", locale))
            elif password_source() != "none":
                ok, msg_key = save_dashboard_password("", clear=True)
                if ok:
                    st.success(t(msg_key, locale))
                    st.rerun()
                else:
                    st.error(t(msg_key, locale))
            else:
                st.info(t("auth.already_open", locale))

    st.markdown("---")
    st.caption(t("auth.generate_intro", locale))
    if st.button(
        t("auth.generate_password", locale),
        use_container_width=True,
        key=f"{key_prefix}_generate_password",
    ):
        generated = generate_strong_password()
        ok, _msg = save_dashboard_password(generated, session_hours=new_session_hours)
        if ok:
            st.session_state[f"{key_prefix}_generated_password"] = generated
            st.rerun()
        else:
            st.error(t("auth.generate_failed", locale))
