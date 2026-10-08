#!/usr/bin/env python3
"""Telegram note about WARDEN's weekly ERC-8004 feedback run (deploy/erc-8004/warden_feedback_refresh.sh).

Runs hourly on not-my-vps next to the fleet alerter and reuses its bot: credentials from
/etc/aicom-alert.env (AICOM_ALERT_TELEGRAM_TOKEN / AICOM_ALERT_TELEGRAM_CHAT), never argv. It reads
the run's public summary — admin-vps never holds the bot token — and says something when:

* a new run finished (what was published, revoked, held for the owner, or why it failed);
* no run has finished for more than 8 days (once a day, until one does);
* the summary itself has been unreachable for FETCH_FAIL_RUNS hourly runs in a row (once a day).

The last two are different facts and say so. When the summary cannot be fetched, the age of the
last run comes from the last summary this script saw (state "notified"), not from nothing: on
2026-10-08 a 12-minute network outage at admin-vps made one fetch time out and the page claimed
the weekly run had not happened for 8 days, three days after it had.

Stdlib only. State in /var/lib/aicom-alert/warden-feedback.json.
"""
from __future__ import annotations

import calendar
import json
import os
import sys
import time
import urllib.parse
import urllib.request

SUMMARY_URL = os.environ.get(
    "WARDEN_FB_SUMMARY_URL", "https://histor.modelmarket.dev/.well-known/erc-8004/feedback/last-run.json")
STATE = os.environ.get("WARDEN_FB_NOTIFY_STATE", "/var/lib/aicom-alert/warden-feedback.json")
STALE_S = 8 * 86400
FETCH_FAIL_RUNS = 3  # hourly runs: one blip is not a page, three hours of silence is
LOW_ETH = float(os.environ.get("WARDEN_FB_LOW_ETH", "0.0001"))  # ~80 feedback transactions on Base


def load_env(path: str = "/etc/aicom-alert.env") -> None:
    try:
        for line in open(path):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def send(text: str) -> None:
    token = os.environ.get("AICOM_ALERT_TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("AICOM_ALERT_TELEGRAM_CHAT", "").strip()
    if not token or not chat:
        sys.exit("no Telegram credentials in /etc/aicom-alert.env")
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=15).read()


def message(run: dict) -> str:
    lines = ["WARDEN · отзывы ERC-8004: еженедельная перепроверка"]
    if run.get("status") != "ok":
        lines.append(f"❗ запуск не удался: {run.get('error') or 'см. journalctl -u warden-feedback на admin-vps'}")
    lines.append(f"за этот запуск — опубликовано: {run.get('given', 0)} · снято: {run.get('revoked', 0)}")
    if run.get("liveFeedback") is not None:
        lines.append(f"всего живых отзывов WARDEN: {run['liveFeedback']}")
    held = run.get("held") or []
    if held:
        names = ", ".join(f"{h.get('name')} (#{h.get('agentId')})" for h in held)
        lines.append(f"ждут твоего решения (блокирующая находка, отзыв не публикуется): {names}")
    if run.get("status") == "ok" and not run.get("given") and not run.get("revoked") and not held:
        lines.append("изменений нет")
    bal = run.get("balanceEth")
    if isinstance(bal, (int, float)):
        lines.append(f"баланс кошелька отзывов: {bal:.6f} ETH" + (" — пора пополнить (сеть Base)" if bal < LOW_ETH else ""))
    lines.append("вне расписания: deploy/erc-8004/warden-feedback")
    return "\n".join(lines)


def main() -> None:
    load_env()
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {}
    req = urllib.request.Request(SUMMARY_URL, headers={"user-agent": "aicom-alert/warden-feedback"})
    try:
        run = json.load(urllib.request.urlopen(req, timeout=20))
    except Exception as exc:  # the summary itself is gone: say so once a day
        run, fetch_error = {}, str(exc)[:200]
    else:
        fetch_error = ""
    now = time.time()
    ran = run.get("ranAt") or ""
    if ran and ran != state.get("notified"):
        send(message(run))
        state["notified"] = ran
    # The summary is the only witness; when it cannot be read, the last one seen still dates the run.
    last = ran or state.get("notified") or ""
    ran_ts = calendar.timegm(time.strptime(last, "%Y-%m-%dT%H:%M:%SZ")) if last else 0
    state["fetch_fail"] = state.get("fetch_fail", 0) + 1 if fetch_error else 0
    if now - ran_ts > STALE_S and now - state.get("stale_sent", 0) > 86400:
        unread = f"; сводка сейчас недоступна: {fetch_error}" if fetch_error else ""
        send(f"WARDEN · отзывы ERC-8004: перепроверка не запускалась больше 8 дней "
             f"(последний известный запуск {last or 'никогда'}{unread}). "
             "Проверь warden-feedback.timer на admin-vps или запусти deploy/erc-8004/warden-feedback.")
        state["stale_sent"] = now
    elif state["fetch_fail"] >= FETCH_FAIL_RUNS and now - state.get("unreachable_sent", 0) > 86400:
        send(f"WARDEN · отзывы ERC-8004: сводка {SUMMARY_URL} не читается {state['fetch_fail']} ч подряд "
             f"({fetch_error}). Последний известный запуск {last} — по расписанию всё в порядке, "
             "проблема в доступе к histor.modelmarket.dev (admin-vps: nginx, сеть).")
        state["unreachable_sent"] = now
    bal = run.get("balanceEth")
    if isinstance(bal, (int, float)) and bal < LOW_ETH and now - state.get("low_sent", 0) > 86400:
        send(f"WARDEN · отзывы ERC-8004: на кошельке {run.get('wallet')} осталось {bal:.6f} ETH "
             f"(меньше {LOW_ETH} ETH, около 80 транзакций). Пополни его в сети Base.")
        state["low_sent"] = now
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(state, open(STATE, "w"))


if __name__ == "__main__":
    main()
