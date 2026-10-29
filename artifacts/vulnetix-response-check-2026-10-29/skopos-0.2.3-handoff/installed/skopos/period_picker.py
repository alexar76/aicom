"""Flexible analytics time-range picker — presets + optional custom range."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

from skopos.i18n import t

RELATIVE_UNITS = ("minutes", "hours", "days", "weeks", "months")
DEFAULT_RELATIVE_AMOUNT = 24
DEFAULT_RELATIVE_UNIT = "hours"
# Relative periods are cache keys for every analytics query. Using the exact
# current microsecond made every Streamlit rerun a guaranteed cache miss.
PERIOD_CACHE_BUCKET_SECONDS = 60

PRESET_ORDER: tuple[str, ...] = ("1d", "7d", "30d", "90d", "365d")
DEFAULT_PRESET = "1d"
PRESET_DAYS: dict[str, int] = {
    "1d": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "365d": 365,
}
PRESET_LABEL_KEYS: dict[str, str] = {
    "1d": "period.preset_day",
    "7d": "period.preset_week",
    "30d": "period.preset_month",
    "90d": "period.preset_quarter",
    "365d": "period.preset_year",
}

SESSION_PRESET_KEY = "analytics_period_preset"
SESSION_CUSTOM_KEY = "analytics_period_use_custom"
SESSION_CUSTOM_PREFIX_KEY = "analytics_period_custom_prefix"


@dataclass(frozen=True)
class PeriodRange:
    since: datetime
    until: datetime

    @property
    def duration(self) -> timedelta:
        return self.until - self.since

    def since_iso(self) -> str:
        return self.since.isoformat()

    def until_iso(self) -> str:
        return self.until.isoformat()


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _cache_aligned_now(dt: datetime) -> datetime:
    """Return a stable UTC boundary shared by reruns in the same minute."""
    utc = _as_utc(dt)
    epoch = int(utc.timestamp())
    aligned = epoch - (epoch % PERIOD_CACHE_BUCKET_SECONDS)
    return datetime.fromtimestamp(aligned, tz=timezone.utc)


def _combine_date_time(d: date, tm: time) -> datetime:
    return datetime.combine(d, tm, tzinfo=timezone.utc)


def _relative_delta(amount: int, unit: str) -> timedelta:
    if amount < 1:
        raise ValueError("amount must be >= 1")
    if unit == "minutes":
        return timedelta(minutes=amount)
    if unit == "hours":
        return timedelta(hours=amount)
    if unit == "days":
        return timedelta(days=amount)
    if unit == "weeks":
        return timedelta(weeks=amount)
    if unit == "months":
        return timedelta(days=amount * 30)
    raise ValueError(f"unknown unit: {unit}")


def resolve_relative_period(amount: int, unit: str, *, now: datetime | None = None) -> PeriodRange:
    end = _as_utc(now or _utc_now())
    start = end - _relative_delta(amount, unit)
    return PeriodRange(since=start, until=end)


def resolve_absolute_period(start: datetime, end: datetime) -> PeriodRange:
    since = _as_utc(start)
    until = _as_utc(end)
    if since > until:
        since, until = until, since
    return PeriodRange(since=since, until=until)


def resolve_preset(preset_id: str, *, now: datetime | None = None) -> PeriodRange:
    days = PRESET_DAYS.get(preset_id, PRESET_DAYS[DEFAULT_PRESET])
    return resolve_relative_period(days, "days", now=now)


def ensure_period_state() -> None:
    if SESSION_PRESET_KEY not in st.session_state:
        st.session_state[SESSION_PRESET_KEY] = DEFAULT_PRESET
    if SESSION_CUSTOM_KEY not in st.session_state:
        st.session_state[SESSION_CUSTOM_KEY] = False


def get_active_period(*, now: datetime | None = None) -> PeriodRange:
    """Resolve period from session without rendering widgets."""
    ensure_period_state()
    now = _cache_aligned_now(now or _utc_now())
    if st.session_state.get(SESSION_CUSTOM_KEY):
        return _resolve_custom_period(now=now)
    preset = str(st.session_state.get(SESSION_PRESET_KEY, DEFAULT_PRESET))
    if preset not in PRESET_DAYS:
        preset = DEFAULT_PRESET
    return resolve_preset(preset, now=now)


def _unit_label(locale: str, unit: str) -> str:
    return t(f"period.unit_{unit}", locale)


def _format_period_summary(period: PeriodRange, locale: str) -> str:
    fmt = "%Y-%m-%d %H:%M UTC"
    return t(
        "period.summary",
        locale,
        from_ts=period.since.strftime(fmt),
        to_ts=period.until.strftime(fmt),
        hours=f"{period.duration.total_seconds() / 3600:.1f}",
    )


def _render_custom_period(container, locale: str, *, key_prefix: str, now: datetime) -> PeriodRange:
    mode = container.radio(
        t("period.mode", locale),
        options=["relative", "absolute"],
        format_func=lambda m: t(f"period.mode_{m}", locale),
        horizontal=True,
        key=f"{key_prefix}_mode",
        label_visibility="collapsed",
    )

    if mode == "relative":
        c1, c2 = container.columns([2, 3])
        amount = int(
            c1.number_input(
                t("period.amount", locale),
                min_value=1,
                max_value=3650,
                value=DEFAULT_RELATIVE_AMOUNT,
                step=1,
                key=f"{key_prefix}_amount",
            )
        )
        unit = c2.selectbox(
            t("period.unit", locale),
            RELATIVE_UNITS,
            index=RELATIVE_UNITS.index(DEFAULT_RELATIVE_UNIT),
            format_func=lambda u: _unit_label(locale, u),
            key=f"{key_prefix}_unit",
        )
        return resolve_relative_period(amount, unit, now=now)

    default_start = now - timedelta(hours=DEFAULT_RELATIVE_AMOUNT)
    start_date = container.date_input(
        t("period.from_date", locale),
        value=default_start.date(),
        max_value=now.date(),
        key=f"{key_prefix}_from_date",
    )
    start_time = container.time_input(
        t("period.from_time", locale),
        value=default_start.time().replace(second=0, microsecond=0),
        key=f"{key_prefix}_from_time",
    )
    end_date = container.date_input(
        t("period.to_date", locale),
        value=now.date(),
        max_value=now.date(),
        key=f"{key_prefix}_to_date",
    )
    end_time = container.time_input(
        t("period.to_time", locale),
        value=now.time().replace(second=0, microsecond=0),
        key=f"{key_prefix}_to_time",
    )
    return resolve_absolute_period(
        _combine_date_time(start_date, start_time),
        _combine_date_time(end_date, end_time),
    )


def _resolve_custom_period(*, now: datetime | None = None) -> PeriodRange:
    """Best-effort custom period from widget keys (main or sidebar toolbar)."""
    now = now or _utc_now()
    prefix = str(st.session_state.get(SESSION_CUSTOM_PREFIX_KEY, "analytics_period_main"))
    mode = st.session_state.get(f"{prefix}_mode", "relative")
    if mode == "absolute":
        try:
            start_d = st.session_state[f"{prefix}_from_date"]
            start_t = st.session_state[f"{prefix}_from_time"]
            end_d = st.session_state[f"{prefix}_to_date"]
            end_t = st.session_state[f"{prefix}_to_time"]
            return resolve_absolute_period(
                _combine_date_time(start_d, start_t),
                _combine_date_time(end_d, end_t),
            )
        except KeyError:
            return resolve_preset(DEFAULT_PRESET, now=now)
    amount = int(st.session_state.get(f"{prefix}_amount", DEFAULT_RELATIVE_AMOUNT))
    unit = st.session_state.get(f"{prefix}_unit", DEFAULT_RELATIVE_UNIT)
    if unit not in RELATIVE_UNITS:
        unit = DEFAULT_RELATIVE_UNIT
    return resolve_relative_period(amount, unit, now=now)


def _activate_custom_period(*, key_suffix: str) -> None:
    st.session_state[SESSION_CUSTOM_KEY] = True
    st.session_state[SESSION_CUSTOM_PREFIX_KEY] = f"analytics_period{key_suffix}"
    st.rerun()


def _render_custom_section(
    container,
    locale: str,
    *,
    key_suffix: str,
    key_prefix: str,
    now: datetime,
    use_custom: bool,
) -> PeriodRange:
    """Custom range block — inline (no nested expander)."""
    period = get_active_period(now=now)
    container.markdown(f"**{t('period.custom_range', locale)}**")
    if use_custom:
        period = _render_custom_period(
            container,
            locale,
            key_prefix=key_prefix,
            now=now,
        )
    else:
        container.caption(t("period.custom_hint", locale))
    if container.button(
        t("period.apply_custom", locale),
        key=f"period_apply_custom{key_suffix}",
        use_container_width=True,
    ):
        _activate_custom_period(key_suffix=key_suffix)
    return period


def render_period_toolbar(
    container,
    locale: str,
    *,
    key_suffix: str,
    show_custom: bool = True,
    custom_as_expander: bool = True,
) -> PeriodRange:
    """Preset period buttons (day/week/month/quarter/year) + optional custom range."""
    ensure_period_state()
    now = _cache_aligned_now(_utc_now())
    use_custom = bool(st.session_state.get(SESSION_CUSTOM_KEY, False))
    active_preset = str(st.session_state.get(SESSION_PRESET_KEY, DEFAULT_PRESET))

    container.markdown(f"**{t('common.period', locale)}**")
    cols = container.columns(len(PRESET_ORDER))
    for col, preset_id in zip(cols, PRESET_ORDER):
        selected = (not use_custom) and preset_id == active_preset
        with col:
            if st.button(
                t(PRESET_LABEL_KEYS[preset_id], locale),
                key=f"period_preset_{preset_id}{key_suffix}",
                type="primary" if selected else "secondary",
                use_container_width=True,
            ):
                st.session_state[SESSION_PRESET_KEY] = preset_id
                st.session_state[SESSION_CUSTOM_KEY] = False
                st.rerun()

    period = get_active_period(now=now)

    if show_custom:
        if custom_as_expander:
            with container.expander(t("period.custom_range", locale), expanded=use_custom):
                if use_custom:
                    period = _render_custom_period(
                        container,
                        locale,
                        key_prefix=f"analytics_period{key_suffix}",
                        now=now,
                    )
                else:
                    container.caption(t("period.custom_hint", locale))
                if container.button(
                    t("period.apply_custom", locale),
                    key=f"period_apply_custom{key_suffix}",
                    use_container_width=True,
                ):
                    _activate_custom_period(key_suffix=key_suffix)
        else:
            period = _render_custom_section(
                container,
                locale,
                key_suffix=key_suffix,
                key_prefix=f"analytics_period{key_suffix}",
                now=now,
                use_custom=use_custom,
            )

    container.caption(_format_period_summary(period, locale))
    return period


def render_period_picker(locale: str, *, key_prefix: str = "analytics_period") -> PeriodRange:
    """Sidebar duplicate of the period toolbar."""
    return render_period_toolbar(
        st.sidebar,
        locale,
        key_suffix="_sb",
        show_custom=True,
    )
