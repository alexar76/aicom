"""Database settings block for Settings UI."""

from __future__ import annotations

import streamlit as st

from skopos.config import AppConfig, load_app_env
from skopos.config_io import load_config_with_commands, save_config
from skopos.db_dialect import resolve_db_target
from skopos.db_migrate import migrate_database, source_row_total, check_database_connection
from skopos.db_settings import DbSettings, active_backend_label, config_from_db_settings, db_settings_from_config
from skopos.env_io import remove_env_var, upsert_env_var
from skopos.i18n import t


def _init_db_session(cfg: AppConfig, config_path: str) -> None:
    loaded = st.session_state.get("_db_settings_loaded_path")
    if loaded == config_path and st.session_state.get("_db_settings_loaded"):
        return
    s = db_settings_from_config(cfg)
    st.session_state.settings_db_mode = s.mode
    st.session_state.settings_db_path = s.db_path
    st.session_state.settings_pg_host = s.pg_host
    st.session_state.settings_pg_port = s.pg_port
    st.session_state.settings_pg_user = s.pg_user
    st.session_state.settings_pg_password = s.pg_password
    st.session_state.settings_pg_database = s.pg_database
    st.session_state._db_settings_loaded = True
    st.session_state._db_settings_loaded_path = config_path


def draft_settings_from_session(cfg: AppConfig) -> DbSettings:
    if "settings_db_mode" not in st.session_state:
        return db_settings_from_config(cfg)
    return _draft_settings(cfg)


def _draft_settings(cfg: AppConfig) -> DbSettings:
    return DbSettings(
        mode=st.session_state.settings_db_mode,
        db_path=st.session_state.settings_db_path,
        pg_host=st.session_state.settings_pg_host,
        pg_port=int(st.session_state.settings_pg_port),
        pg_user=st.session_state.settings_pg_user,
        pg_password=st.session_state.settings_pg_password,
        pg_database=st.session_state.settings_pg_database,
    )


def apply_database_settings(
    cfg: AppConfig,
    config_path: str,
    *,
    locale: str,
    migrate: bool = True,
) -> tuple[bool, str]:
    draft = _draft_settings(cfg)
    if draft.mode == "postgres" and not draft.pg_host.strip():
        return False, t("settings.db_host_required", locale)

    old_target = resolve_db_target(cfg)
    new_cfg = config_from_db_settings(cfg, draft)
    new_target = resolve_db_target(new_cfg)

    if migrate and old_target.strip() != new_target.strip():
        src_rows = source_row_total(old_target)
        if src_rows:
            result = migrate_database(old_target, new_target, replace_dest=True)
            if not result.ok:
                return False, result.error or t("settings.db_migrate_fail", locale)
            summary = ", ".join(f"{k}={v}" for k, v in result.rows_copied.items() if v)
            migrate_msg = t("settings.db_migrate_ok", locale, summary=summary or "0")
        else:
            migrate_msg = t("settings.db_migrate_empty", locale)
    else:
        migrate_msg = t("settings.db_no_migrate", locale)

    save_config(config_path, new_cfg, ssh_commands=load_config_with_commands(config_path)[1])
    if draft.mode == "postgres":
        upsert_env_var("SKOPOS_DATABASE_URL", new_target)
    else:
        remove_env_var("SKOPOS_DATABASE_URL")
    load_app_env()
    st.cache_data.clear()
    st.cache_resource.clear()
    return True, migrate_msg


def render_database_settings(cfg: AppConfig, *, config_path: str, locale: str) -> None:
    _init_db_session(cfg, config_path)
    active = active_backend_label(cfg)
    current = resolve_db_target(cfg)

    if active == "sqlite":
        st.info(t("settings.db_prod_recommend", locale))
    else:
        st.success(t("settings.db_postgres_active", locale))

    c1, c2 = st.columns(2)
    with c1:
        st.caption(t("settings.db_current_backend", locale, backend=active))
    with c2:
        show = current if active == "sqlite" else current.split("@")[-1]
        st.caption(t("settings.db_current_target", locale, target=show))

    mode = st.radio(
        t("settings.db_mode", locale),
        options=["sqlite", "postgres"],
        index=0 if st.session_state.settings_db_mode == "sqlite" else 1,
        format_func=lambda x: t("settings.db_mode_sqlite", locale)
        if x == "sqlite"
        else t("settings.db_mode_postgres", locale),
        horizontal=True,
        key="settings_db_mode_radio",
    )
    st.session_state.settings_db_mode = mode

    if mode == "sqlite":
        st.session_state.settings_db_path = st.text_input(
            t("settings.db_sqlite_path", locale),
            value=st.session_state.settings_db_path,
            key="settings_db_path_input",
        )
    else:
        pg1, pg2 = st.columns(2)
        with pg1:
            st.session_state.settings_pg_host = st.text_input(
                t("settings.db_pg_host", locale),
                value=st.session_state.settings_pg_host,
                key="settings_pg_host_input",
            )
            st.session_state.settings_pg_user = st.text_input(
                t("settings.db_pg_user", locale),
                value=st.session_state.settings_pg_user,
                key="settings_pg_user_input",
            )
            st.session_state.settings_pg_database = st.text_input(
                t("settings.db_pg_name", locale),
                value=st.session_state.settings_pg_database,
                key="settings_pg_db_input",
            )
        with pg2:
            st.session_state.settings_pg_port = st.number_input(
                t("settings.db_pg_port", locale),
                min_value=1,
                max_value=65535,
                value=int(st.session_state.settings_pg_port),
                key="settings_pg_port_input",
            )
            st.session_state.settings_pg_password = st.text_input(
                t("settings.db_pg_password", locale),
                value=st.session_state.settings_pg_password,
                type="password",
                key="settings_pg_password_input",
            )

    draft = _draft_settings(cfg)
    b1, b2 = st.columns(2)
    with b1:
        if st.button(t("settings.db_test", locale), use_container_width=True, key="settings_db_test_btn"):
            ok, msg = check_database_connection(draft.target)
            st.success(msg) if ok else st.error(msg)
    with b2:
        if st.button(
            t("settings.db_apply", locale),
            type="primary",
            use_container_width=True,
            key="settings_db_apply_btn",
        ):
            ok, msg = apply_database_settings(cfg, config_path, locale=locale, migrate=True)
            if ok:
                st.session_state._db_settings_loaded = False
                st.session_state.pop("_db_settings_loaded_path", None)
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.caption(t("settings.db_apply_hint", locale))
