"""AI Security Agent settings — provider, API keys, agent.yaml path."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from skopos.agent import LLMProviderError, chat_with_agent, load_agent_config
from skopos.agent.config import get_provider
from skopos.config import load_app_env
from skopos.config_paths import resolve_config_path
from skopos.env_io import upsert_env_var
from skopos.i18n import t
from skopos.ui import hero, section_head


def _resolve_agent_path(raw: str) -> str:
    return str(resolve_config_path(raw))


def render_agent_settings(*, locale: str, agent_path: str) -> None:
    load_app_env()
    hero(t("agent_settings.title", locale), t("agent_settings.subtitle", locale))
    st.info(t("agent_settings.floating_hint", locale))

    section_head(t("agent_settings.config_title", locale))
    path_input = st.text_input(
        t("agent_settings.config_path", locale),
        value=agent_path,
        key="agent_settings_yaml_path",
        help=t("agent_settings.config_path_help", locale),
    )
    try:
        resolved = _resolve_agent_path(path_input)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    try:
        agent_cfg = load_agent_config(resolved)
    except Exception as exc:
        st.error(f"{t('common.error', locale)}: {exc}")
        st.stop()

    prov_ids = list(agent_cfg.providers.keys())
    if not prov_ids:
        st.warning(t("agent_settings.no_providers", locale))
        st.stop()

    default_idx = (
        prov_ids.index(agent_cfg.default_provider)
        if agent_cfg.default_provider in prov_ids
        else 0
    )
    if "global_agent_provider" not in st.session_state:
        st.session_state.global_agent_provider = prov_ids[default_idx]

    current_idx = (
        prov_ids.index(st.session_state.global_agent_provider)
        if st.session_state.global_agent_provider in prov_ids
        else default_idx
    )

    section_head(t("agent_settings.provider_title", locale))
    st.caption(t("agent_settings.provider_hint", locale))
    picked = st.selectbox(
        t("security.agent_provider", locale),
        prov_ids,
        index=current_idx,
        key="agent_settings_provider",
    )
    st.session_state.global_agent_provider = picked

    prov = get_provider(agent_cfg, picked)
    model = getattr(prov, "model", "") or "—"
    st.caption(t("agent_settings.model_label", locale, model=model))

    needs_key = prov.kind in ("openai_compatible", "anthropic_compatible")
    if needs_key:
        env_name = prov.api_key_env or "API_KEY"
        has_key = bool(prov.api_key)
        if has_key:
            st.success(t("agent_settings.key_set", locale, env=env_name))
        else:
            st.warning(t("security.agent_no_key", locale, env=env_name))

        new_key = st.text_input(
            t("agent_settings.api_key", locale, env=env_name),
            type="password",
            key=f"agent_settings_key_{picked}",
            placeholder="••••••••" if has_key else "",
            help=t("agent_settings.api_key_help", locale),
        )
        if st.button(t("agent_settings.save_key", locale), key="agent_settings_save_key", type="primary"):
            if not new_key.strip():
                st.error(t("agent_settings.key_required", locale))
            else:
                upsert_env_var(env_name, new_key.strip())
                load_app_env()
                st.success(t("agent_settings.key_saved", locale, env=env_name))
                st.rerun()

    section_head(t("agent_settings.test_title", locale))
    st.caption(t("agent_settings.test_hint", locale))
    if st.button(t("agent_settings.test_btn", locale), key="agent_settings_test"):
        load_app_env()
        try:
            reply = chat_with_agent(
                agent_cfg,
                [],
                t("agent_settings.test_prompt", locale),
                context=t("agent_settings.test_context", locale),
                provider_id=picked,
            )
            st.success(t("agent_settings.test_ok", locale))
            st.markdown(reply)
        except LLMProviderError as exc:
            st.error(str(exc))

    with st.expander(t("agent_settings.advanced_title", locale), expanded=False):
        st.caption(t("agent_settings.advanced_hint", locale))
        cfg_path = Path(resolved).expanduser()
        if cfg_path.is_file():
            st.code(cfg_path.read_text(encoding="utf-8"), language="yaml")
        else:
            st.warning(t("agent_settings.file_missing", locale, path=resolved))
