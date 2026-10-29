"""Interactive quick-start wizard UI."""

from __future__ import annotations

import streamlit as st

from skopos.agent.config import get_provider, load_agent_config
from skopos.collector import collect_once
from skopos.config import AppConfig
from skopos.config_io import draft_server_from_form, save_config
from skopos.i18n import safe_container_page_link, t
from skopos.security.collector import scan_all_servers
from skopos.setup_state import (
    SetupStatus,
    default_app_config,
    dismiss_wizard,
    evaluate_setup,
    suggest_wizard_step,
    try_load_config,
)
from skopos.remote_ops import ssh_info
from skopos.ssh_setup import (
    build_keygen_ed25519_cmd,
    open_interactive_terminal,
    resolve_key_path,
    test_ssh_connection,
)
from skopos.ui import hero, section_head
from skopos.ui_dashboard_auth import render_dashboard_auth_settings


WIZARD_STEPS = 6


def _t(locale: str, key: str, **kw) -> str:
    return t(key, locale, **kw)


def render_wizard_progress(*, locale: str, current_step: int) -> None:
    import html

    labels = [
        _t(locale, "wizard.step_welcome"),
        _t(locale, "wizard.step_server"),
        _t(locale, "wizard.step_ssh"),
        _t(locale, "wizard.step_security"),
        _t(locale, "wizard.step_collect"),
        _t(locale, "wizard.step_scan"),
        _t(locale, "wizard.step_done"),
    ]
    parts = ['<div class="skopos-wizard-steps">']
    for idx, label in enumerate(labels):
        if idx < current_step:
            cls, icon = "is-done", "✅"
        elif idx == current_step:
            cls, icon = "is-current", "▶️"
        else:
            cls, icon = "is-todo", "⬜"
        parts.append(
            f'<span class="skopos-wizard-step {cls}">'
            f'{icon} {html.escape(label)}</span>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
    st.progress(min(current_step, WIZARD_STEPS) / WIZARD_STEPS)


def _nav_buttons(*, locale: str, step: int, can_next: bool = True) -> None:
    left, right = st.columns(2)
    with left:
        if step > 0 and st.button(
            _t(locale, "wizard.back"),
            use_container_width=True,
            key="quickstart_wizard_back",
        ):
            st.session_state.wizard_step = max(0, step - 1)
            st.rerun()
    with right:
        if step < WIZARD_STEPS and st.button(
            _t(locale, "wizard.next"),
            type="primary",
            use_container_width=True,
            disabled=not can_next,
            key="quickstart_wizard_next",
        ):
            st.session_state.wizard_step = min(WIZARD_STEPS, step + 1)
            st.rerun()


def _save_server_config(
    config_path: str,
    server,
    *,
    auto_scan: bool,
    scan_interval: int,
    existing_servers: list | None = None,
) -> None:
    servers = list(existing_servers or [])
    replaced = False
    for idx, existing in enumerate(servers):
        if existing.name == server.name:
            servers[idx] = server
            replaced = True
            break
    if not replaced:
        servers.append(server)
    base = try_load_config(config_path) or default_app_config()
    cfg = AppConfig(
        db_path=base.db_path,
        geoip_mmdb_path=base.geoip_mmdb_path,
        poll_interval_seconds=base.poll_interval_seconds,
        batch_lines_per_server=base.batch_lines_per_server,
        security_auto_scan=auto_scan,
        security_scan_interval_minutes=scan_interval,
        servers=servers,
    )
    save_config(config_path, cfg, ssh_commands={})


def render_quick_start_wizard(*, locale: str, config_path: str, agent_path: str) -> None:
    status = evaluate_setup(config_path, agent_path)
    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = suggest_wizard_step(status)

    hero(_t(locale, "wizard.title"), _t(locale, "wizard.subtitle"))
    render_wizard_progress(locale=locale, current_step=st.session_state.wizard_step)

    if status.complete:
        st.success(_t(locale, "wizard.already_complete"))

    step = int(st.session_state.wizard_step)
    cfg = try_load_config(config_path)

    if step == 0:
        _render_welcome(locale, status)
    elif step == 1:
        _render_server_step(locale, config_path, cfg, status)
    elif step == 2:
        _render_ssh_step(locale, cfg, status)
    elif step == 3:
        _render_security_step(locale, config_path, cfg, agent_path, status)
    elif step == 4:
        _render_collect_step(locale, cfg, status)
    elif step == 5:
        _render_scan_step(locale, cfg, status)
    else:
        _render_done_step(locale, status)

    st.markdown("---")
    can_next = True
    if step == 1:
        can_next = status.config_valid and status.server_count > 0
    elif step == 2:
        can_next = status.ssh_key_exists
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button(_t(locale, "wizard.skip"), use_container_width=True, key="quickstart_wizard_skip"):
            dismiss_wizard()
            st.session_state.wizard_step = WIZARD_STEPS
            st.rerun()
    with c2:
        if step > 0 and st.button(
            _t(locale, "wizard.back"),
            use_container_width=True,
            key="quickstart_wizard_back",
        ):
            st.session_state.wizard_step = max(0, step - 1)
            st.rerun()
    with c3:
        if step < WIZARD_STEPS and st.button(
            _t(locale, "wizard.next"),
            type="primary",
            use_container_width=True,
            disabled=not can_next,
            key="quickstart_wizard_next",
        ):
            st.session_state.wizard_step = min(WIZARD_STEPS, step + 1)
            st.rerun()


def _render_welcome(locale: str, status: SetupStatus) -> None:
    section_head(_t(locale, "wizard.welcome_head"))
    st.markdown(_t(locale, "wizard.welcome_body"))
    checks = [
        (_t(locale, "wizard.check_servers"), status.server_count > 0),
        (_t(locale, "wizard.check_ssh"), status.ssh_key_exists),
        (_t(locale, "wizard.check_password"), status.password_set),
        (_t(locale, "wizard.check_ai"), status.ai_key_set),
        (_t(locale, "wizard.check_traffic"), status.has_traffic),
        (_t(locale, "wizard.check_scan"), status.has_scan),
    ]
    for label, done in checks:
        st.markdown(f"{'✅' if done else '⬜'} {label}")
    st.info(_t(locale, "wizard.welcome_hint"))


def _render_server_step(locale: str, config_path: str, cfg: AppConfig | None, status: SetupStatus) -> None:
    section_head(_t(locale, "wizard.server_head"))
    st.caption(_t(locale, "wizard.server_hint"))
    existing = cfg.servers[0] if cfg and cfg.servers else None
    with st.form("wizard_server_form"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input(_t(locale, "settings.field_name"), value=existing.name if existing else "web-1")
            host = st.text_input(_t(locale, "settings.field_host"), value=existing.ssh.host if existing else "")
            user = st.text_input(_t(locale, "settings.field_user"), value=existing.ssh.user if existing else "stats")
        with c2:
            port = st.number_input(
                _t(locale, "settings.field_port"),
                min_value=1,
                max_value=65535,
                value=int(existing.ssh.port if existing else 22),
            )
            key_path = st.text_input(
                _t(locale, "settings.field_key_path"),
                value=(existing.ssh.key_path if existing else "~/.ssh/id_ed25519") or "~/.ssh/id_ed25519",
            )
            log_path = st.text_input(
                _t(locale, "settings.field_log_path"),
                value=existing.nginx.access_log_path if existing else "/var/log/nginx/access.log",
            )
        auto_logs = st.checkbox(
            _t(locale, "settings.field_auto_logs"),
            value=existing.nginx.auto_discover_logs if existing else True,
        )
        submitted = st.form_submit_button(_t(locale, "wizard.save_server"), type="primary", use_container_width=True)
        if submitted:
            if not name.strip() or not host.strip():
                st.error(_t(locale, "settings.add_server_validation"))
            else:
                server = draft_server_from_form(
                    name=name,
                    host=host,
                    port=int(port),
                    user=user,
                    key_path=key_path,
                    key_passphrase_env="SKOPOS_SSH_KEY_PASSPHRASE",
                    access_log_path=log_path,
                    auto_discover_logs=auto_logs,
                    auto_discover_docker_logs=False,
                    docker_log_containers="",
                )
                auto_scan = cfg.security_auto_scan if cfg else True
                interval = cfg.security_scan_interval_minutes if cfg else 60
                _save_server_config(
                    config_path,
                    server,
                    auto_scan=auto_scan,
                    scan_interval=interval,
                    existing_servers=list(cfg.servers) if cfg else None,
                )
                st.cache_data.clear()
                from skopos.config import load_config
                from skopos.fleet_warmup import warm_fleet_after_save

                saved = load_config(config_path)
                with st.spinner(_t(locale, "settings.warmup_running")):
                    warm = warm_fleet_after_save(
                        saved,
                        previous_servers=list(cfg.servers) if cfg else None,
                    )
                if warm.server_names:
                    st.success(
                        _t(
                            locale,
                            "settings.warmup_ok",
                            servers=", ".join(warm.server_names),
                            collected=len(warm.collect),
                            scanned=sum(1 for s in warm.scans if s.ok),
                        )
                    )
                else:
                    st.success(_t(locale, "wizard.server_saved"))
                st.session_state.wizard_step = 2
                st.rerun()
    if status.config_valid and status.server_count > 0:
        st.success(_t(locale, "wizard.server_ready"))


def _render_ssh_step(locale: str, cfg: AppConfig | None, status: SetupStatus) -> None:
    section_head(_t(locale, "wizard.ssh_head"))
    if not cfg or not cfg.servers:
        st.warning(_t(locale, "wizard.need_server_first"))
        return
    server = cfg.servers[0]
    key_info = resolve_key_path(server.ssh.key_path)
    m1, m2 = st.columns(2)
    m1.metric(_t(locale, "settings.key_private"), "✅" if key_info.exists else "❌")
    m2.metric(_t(locale, "settings.key_path_label"), key_info.private_path)
    if not key_info.exists:
        st.info(_t(locale, "settings.key_missing"))
        cmd = build_keygen_ed25519_cmd(key_path=key_info.private_path)
        st.code(cmd, language="bash")
        if st.button(_t(locale, "settings.run_keygen_ed25519"), use_container_width=True):
            ok, msg = open_interactive_terminal(cmd)
            st.success(msg) if ok else st.error(msg)
    if server.transport == "agent-push":
        # There is nothing to test: SKOPOS never connects to a push host. Saying
        # so is better than offering a button that raises.
        st.info(
            "This host reports in on its own — SKOPOS holds no SSH credential "
            "for it, so there is no connection to test."
        )
    else:
        conn = ssh_info(server)
        if st.button(_t(locale, "settings.test_ssh"), type="primary", use_container_width=True):
            ok, detail = test_ssh_connection(conn)
            st.success(detail) if ok else st.error(detail)


def _render_security_step(
    locale: str,
    config_path: str,
    cfg: AppConfig | None,
    agent_path: str,
    status: SetupStatus,
) -> None:
    section_head(_t(locale, "wizard.security_head"))
    st.markdown(_t(locale, "wizard.security_body"))
    render_dashboard_auth_settings(locale, key_prefix="wizard")
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"{'✅' if status.password_set else '⚠️'} {_t(locale, 'wizard.password_status')}")
        if not status.password_set:
            st.caption(_t(locale, "auth.no_password_warn"))
    with c2:
        st.markdown(f"{'✅' if status.ai_key_set else '⚠️'} {_t(locale, 'wizard.ai_status')}")
        if not status.ai_key_set:
            try:
                agent_cfg = load_agent_config(agent_path)
                prov = get_provider(agent_cfg)
                env_name = prov.api_key_env or "API_KEY"
            except Exception:
                env_name = "OPENROUTER_API_KEY"
            st.caption(_t(locale, "wizard.ai_hint", env=env_name))
    auto_scan = cfg.security_auto_scan if cfg else True
    interval = cfg.security_scan_interval_minutes if cfg else 60
    auto_scan_enabled = st.toggle(_t(locale, "settings.auto_scan_enabled"), value=auto_scan)
    scan_interval = st.number_input(
        _t(locale, "settings.auto_scan_interval"),
        min_value=5,
        max_value=1440,
        value=int(interval),
        step=5,
    )
    if cfg and st.button(_t(locale, "wizard.save_security_prefs"), use_container_width=True):
        updated = AppConfig(
            db_path=cfg.db_path,
            geoip_mmdb_path=cfg.geoip_mmdb_path,
            poll_interval_seconds=cfg.poll_interval_seconds,
            batch_lines_per_server=cfg.batch_lines_per_server,
            security_auto_scan=auto_scan_enabled,
            security_scan_interval_minutes=int(scan_interval),
            servers=list(cfg.servers),
        )
        save_config(config_path, updated, ssh_commands={})
        st.success(_t(locale, "settings.save_ok"))


def _render_collect_step(locale: str, cfg: AppConfig | None, status: SetupStatus) -> None:
    section_head(_t(locale, "wizard.collect_head"))
    st.caption(_t(locale, "wizard.collect_hint"))
    if not cfg:
        st.warning(_t(locale, "wizard.need_server_first"))
        return
    if status.has_traffic:
        st.success(_t(locale, "wizard.collect_done"))
    if st.button(_t(locale, "settings.collect_now"), type="primary", use_container_width=True):
        with st.spinner(_t(locale, "wizard.collect_running")):
            results = collect_once(cfg)
        for row in results:
            st.caption(f"**{row.server_name}**: fetched {row.fetched_lines}, inserted {row.inserted_rows}")
        st.cache_data.clear()
        if any(r.inserted_rows > 0 for r in results):
            st.success(_t(locale, "wizard.collect_success"))
        else:
            st.info(_t(locale, "wizard.collect_empty"))


def _render_scan_step(locale: str, cfg: AppConfig | None, status: SetupStatus) -> None:
    section_head(_t(locale, "wizard.scan_head"))
    st.caption(_t(locale, "wizard.scan_hint"))
    if not cfg:
        st.warning(_t(locale, "wizard.need_server_first"))
        return
    if status.has_scan:
        st.success(_t(locale, "wizard.scan_done"))
    if st.button(_t(locale, "security.scan_all"), type="primary", use_container_width=True):
        with st.spinner(_t(locale, "common.scanning")):
            results = scan_all_servers(cfg)
        for row in results:
            label = "✅" if row.ok else "❌"
            st.caption(f"{label} **{row.server_name}**: {row.error or _t(locale, 'wizard.scan_ok')}")
        st.cache_data.clear()
        if any(r.ok for r in results):
            st.success(_t(locale, "wizard.scan_success"))


def _render_done_step(locale: str, status: SetupStatus) -> None:
    section_head(_t(locale, "wizard.done_head"))
    st.balloons()
    st.markdown(_t(locale, "wizard.done_body"))
    c1, c2, c3 = st.columns(3)
    safe_container_page_link(c1, "dashboard.py", label=f"📈 {_t(locale, 'app.analytics')}", use_container_width=True)
    safe_container_page_link(c2, "pages/1_Security.py", label=f"🔒 {_t(locale, 'app.security')}", use_container_width=True)
    safe_container_page_link(c3, "pages/2_Settings.py", label=f"⚙️ {_t(locale, 'app.settings')}", use_container_width=True)
    if st.button(_t(locale, "wizard.finish"), type="primary", use_container_width=True):
        dismiss_wizard()
        st.success(_t(locale, "wizard.finish_ok"))
        st.rerun()
