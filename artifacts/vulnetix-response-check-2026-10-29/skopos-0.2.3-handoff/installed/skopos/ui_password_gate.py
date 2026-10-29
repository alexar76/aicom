"""Post-deploy notice: prompt the operator to set a dashboard password.

Shown whenever no password is configured (fresh deploy). Offers a one-click
strong-password generator and a manual form with live policy validation. The
password is hashed and stored in the DB — plaintext is only revealed once so the
operator can save it.
"""

from __future__ import annotations

import streamlit as st

from skopos.auth_store import dashboard_password_configured, generate_strong_password
from skopos.i18n import t
from skopos.ui_dashboard_auth import render_password_requirements, save_dashboard_password


def _dialog_body(locale: str) -> None:
    st.caption(t("auth.setup_modal_intro", locale))

    generated = st.session_state.get("_pwgate_generated")
    if generated:
        st.success(t("auth.generated_saved", locale))
        st.code(generated, language=None)
        st.caption(t("auth.generated_copy_hint", locale))
        if st.button(t("auth.generated_dismiss", locale), key="pwgate_done", type="primary"):
            st.session_state.pop("_pwgate_generated", None)
            st.rerun()
        return

    if st.button(
        t("auth.generate_password", locale),
        use_container_width=True,
        type="primary",
        key="pwgate_generate",
    ):
        pw = generate_strong_password()
        ok, _msg = save_dashboard_password(pw)
        if ok:
            st.session_state["_pwgate_generated"] = pw
            st.rerun()
        else:
            st.error(t("auth.generate_failed", locale))

    st.caption(t("auth.password_requirements_intro", locale))
    render_password_requirements(locale)

    with st.form("pwgate_form", clear_on_submit=False):
        pwd1 = st.text_input(t("auth.new_password", locale), type="password")
        pwd2 = st.text_input(t("auth.confirm_password", locale), type="password")
        if pwd1:
            render_password_requirements(locale, pwd1)
        if st.form_submit_button(t("auth.save_password", locale), type="primary", use_container_width=True):
            if not pwd1:
                st.error(t("auth.password_empty", locale))
            elif pwd1 != pwd2:
                st.error(t("auth.password_mismatch", locale))
            else:
                ok, msg_key = save_dashboard_password(pwd1)
                if ok:
                    st.success(t(msg_key, locale))
                    st.rerun()
                else:
                    st.error(t(msg_key, locale))

    if st.button(t("auth.setup_later", locale), key="pwgate_later"):
        st.session_state["_pwgate_dismissed"] = True
        st.rerun()


def render_password_setup_banner(locale: str) -> None:
    st.warning(t("auth.setup_banner", locale), icon="🔓")
    if st.button(t("auth.setup_open", locale), key="pwgate_open_banner", type="primary"):
        st.session_state["_pwgate_reopen"] = True
        st.session_state.pop("_pwgate_dismissed", None)
        st.rerun()


def maybe_prompt_password_setup(locale: str, *, allow_dismiss: bool | None = None) -> None:
    """Open the setup modal (once/session) + a persistent banner until a password is set."""
    if dashboard_password_configured():
        return

    from skopos.app_auth import dashboard_auth_required

    if allow_dismiss is None:
        allow_dismiss = not dashboard_auth_required()

    render_password_setup_banner(locale)

    reopen = st.session_state.pop("_pwgate_reopen", False)
    already_seen = st.session_state.get("_pwgate_seen")
    dismissed = st.session_state.get("_pwgate_dismissed")
    if already_seen and not reopen and allow_dismiss:
        return
    if dismissed and not reopen and allow_dismiss:
        return

    st.session_state["_pwgate_seen"] = True

    if allow_dismiss:
        dialog = st.dialog(t("auth.setup_modal_title", locale))(lambda: _dialog_body(locale))
    else:
        dialog = st.dialog(t("auth.setup_modal_title", locale))(
            lambda: _dialog_body_required(locale)
        )
    dialog()


def _dialog_body_required(locale: str) -> None:
    """Same as setup dialog, but no 'later' escape hatch (production)."""
    st.caption(t("auth.setup_modal_intro", locale))

    generated = st.session_state.get("_pwgate_generated")
    if generated:
        st.success(t("auth.generated_saved", locale))
        st.code(generated, language=None)
        st.caption(t("auth.generated_copy_hint", locale))
        if st.button(t("auth.generated_dismiss", locale), key="pwgate_done", type="primary"):
            st.session_state.pop("_pwgate_generated", None)
            st.rerun()
        return

    if st.button(
        t("auth.generate_password", locale),
        use_container_width=True,
        type="primary",
        key="pwgate_generate",
    ):
        pw = generate_strong_password()
        ok, _msg = save_dashboard_password(pw)
        if ok:
            st.session_state["_pwgate_generated"] = pw
            st.rerun()
        else:
            st.error(t("auth.generate_failed", locale))

    st.caption(t("auth.password_requirements_intro", locale))
    render_password_requirements(locale)

    with st.form("pwgate_form", clear_on_submit=False):
        pwd1 = st.text_input(t("auth.new_password", locale), type="password")
        pwd2 = st.text_input(t("auth.confirm_password", locale), type="password")
        if pwd1:
            render_password_requirements(locale, pwd1)
        if st.form_submit_button(t("auth.save_password", locale), type="primary", use_container_width=True):
            if not pwd1:
                st.error(t("auth.password_empty", locale))
            elif pwd1 != pwd2:
                st.error(t("auth.password_mismatch", locale))
            else:
                ok, msg_key = save_dashboard_password(pwd1)
                if ok:
                    st.success(t(msg_key, locale))
                    st.rerun()
                else:
                    st.error(t(msg_key, locale))
