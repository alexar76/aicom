"""Derive scoped audit facts from saved responses without further network access."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def read(name):
    return json.loads((ROOT / name).read_text())


aer = read("aer.raw")
baseline = json.loads((REPO / "docs/evidence/external-use-pass6-2026-10-30/aer-free-snapshot.json").read_text())
fields = ["as_of", "tier", "tier_raw", "score", "uptime", "organic_paying_agents", "paying_wallets_raw", "settled_usd_14d", "centrality", "outlook_basis"]
agent402 = read("agent402-index.raw")
stats = read("hub-stats.raw")
peers = read("hub-peers.raw")
volume = read("x402-volume.raw")
november_rows = [row for row in volume["data"] if "2026-11-01" <= row["date"] <= "2026-11-09"]
summary = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "external_writes": False,
    "payments_or_invokes": False,
    "aer": {
        "source": "https://agenteconomy.report/s/modelmarket.dev.json",
        "baseline": {key: baseline.get(key) for key in fields},
        "current": {key: aer.get(key) for key in fields},
        "methodology_source": "https://agenteconomy.report/s/methodology",
        "current_methodology_version": "2026-11-08",
        "comparability_ru": "2 ноября изменился набор ресурсов для uptime, 8 ноября — фильтрация organic wallets. Рост рейтинга и uptime не является изолированной оценкой улучшения продукта на неизменной методике.",
        "top_organic_displayed": ["0x097e3f339d0b02…", "agent402.tools…", "0xa4f183a6799f03…", "0xb9148cd4157ad8…"],
        "attribution_ru": "Первый префикс совпадает с раскрытым тестовым кошельком владельца в docs/pay-on-verified-demo.md. Agent402 — посредник; известна собственная тестовая покупка через него 30 октября. Операторы двух остальных префиксов не установлены. Четыре organic не равны четырём независимым клиентам; очищенную сумму и число клиентов этот срез не вычисляет.",
    },
    "x402_list": {
        "source": "https://x402-list.com/api/v1/services/aimarket/volume",
        "attribution": "Data: x402-list.com (CC BY 4.0)",
        "window": "2026-11-01 through incomplete 2026-11-09 UTC, as returned at observation",
        "reported_rows": november_rows,
        "reported_settlements_in_rows": sum(row["tx_count"] for row in november_rows),
        "scope_ru": "Весь payout address у измеряемых facilitators; не уникальные клиенты, не delivery outcomes. Каждая дневная сумма округлена до $0.00; точная сумма из этих округлений не восстанавливается. Пропущенные дни отдельно не объявлены нулём.",
    },
    "agent402": {
        "source": "https://agent402.tools/api/index?seller=modelmarket.dev",
        "fetched_at_utc": datetime.fromtimestamp(agent402["fetchedAt"] / 1000, timezone.utc).isoformat(),
        "routes": agent402["toolCount"],
        "paid_routes": agent402["paidToolCount"],
        "router_dispatch_eligible": agent402["routerDispatchEligible"],
        "reason": agent402["routerDispatchReason"],
        "paid_route_callable_flags": [{"route": row["route"], "callable_now": row.get("executeViaCallableNow"), "reason": row.get("routerDispatchReason")} for row in agent402["tools"] if row.get("paid")],
        "interpretation_ru": "Текущее решение внешнего роутера блокирует dispatch по settlement_self_funded / below the settlement floor. Его расчёт происхождения средств здесь не воспроизведён; это не проверка прямого вызова нашего API и не диагноз его недоступности.",
    },
    "usetested": {
        "source": "https://usetested.com/v1/review?service=modelmarket.dev",
        "calls_tested": read("usetested.raw")["measured"]["calls_tested"],
        "receipts": read("usetested.raw")["receipts"],
        "interpretation_ru": "По-прежнему один исторический платный тест 27 октября. Обновление review 2 ноября не является новой покупкой.",
    },
    "agenstry": {
        "source": "https://agenstry.com/agents/modelmarket.dev",
        "score": 78,
        "grade": "B",
        "successful_direct_probes": 70,
        "direct_probes": 70,
        "displayed_invocations_last_7d": 0,
        "scope_ru": "Автоматическая протокольная проверка каталога; не доказательство adoption. Счёт 78/B уже существовал в октябре.",
    },
    "public_own_telemetry": {
        "source": "https://modelmarket.dev/ai-market/v2/stats/live",
        "total_invocations_since_counter_reset": stats["summary"]["total_invocations"],
        "classified_external_invocations": stats["summary"]["external_invocations"],
        "recent_page_rows": len(stats["events"]),
        "recent_classification_counts": [{"traffic_class": key[0], "traffic_basis": key[1], "rows": value} for key, value in Counter((row.get("traffic_class"), row.get("traffic_basis")) for row in stats["events"]).items()],
        "interpretation_ru": "В 50 последних строках 31 external/override относится к одному псевдониму account:18001a84cca4, 10 external имеют traffic_basis=null. Ни сводные 2808 external, ни 677 credit accounts не являются проверенным количеством независимых пользователей. Денежный volume ledger, выданные credits и внешние settlements не суммируются.",
    },
    "federation": {
        "source": "https://modelmarket.dev/ai-market/v2/federation/peers",
        "peers_count": peers["count"],
        "pending_count": peers["pending_count"],
        "agent_exec": next(row for row in peers["peers"] if row["url"] == "https://agent-exec.448c.org"),
        "industrial": next(row for row in peers["peers"] if "railway.app" in row["url"]),
        "offline_signature_result": "peer-signatures.json",
        "interpretation_ru": "agent-exec объявляет 19 tools, его подпись совместима с Hub, отрицательный контроль отвергнут. Это техническая совместимость снимка, не выполнение 19 tools и не новый покупатель. Industrial по-прежнему active/trusted, но liveness=silent, silent_days=9, discovery HTTP404. Количество peers включает собственные сервисы и не равно числу внешних операторов.",
    },
    "apis_attested": {
        "source": "https://apis.io/providers/attestedmemory-net/",
        "profile_created": "2026-11-02",
        "profile_source": "harvest:mcp-registry",
        "listed_api_contracts": 56,
        "listed_agent_skills": 8,
        "score_as_of": "2026-11-06",
        "rubric": "v0.27.0",
        "composite_score": 32.5,
        "interpretation_ru": "Новая машинная обнаружимость/профилирование. Автогенерированные contracts, skills и оценки не доказывают стороннее выполнение кода, ручной обзор или клиентов; отдельные отрицательные поля оценки не перепроверены против реализации.",
    },
    "limitations_ru": [
        "Срез публичных источников 9 ноября, не весь интернет и не закрытая аналитика.",
        "Даты первого обнаружения не приравниваются к датам события; собственные ответы, автоиндексы и исследования отделены от регулярного спроса.",
        "VibeLeaderboard ответил HTTP429; обход не выполнялся, поисковая карточка не принята за проверенный полный обзор.",
    ],
}
(ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"saved": "summary.json", "x402_list_reported_settlements": summary["x402_list"]["reported_settlements_in_rows"], "aer_tier": aer["tier"], "agent402_dispatch": agent402["routerDispatchEligible"]}, ensure_ascii=False))
