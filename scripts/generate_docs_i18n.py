#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate docs i18n JSON packs from canonical English strings in app/docs/page.tsx."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent.parent / "web" / "frontend" / "language-packs" / "docs"

LOCALE_NAMES = {"en": "English", "ru": "Русский", "es": "Español"}
LOCALE_LABELS = {"en": "EN", "ru": "RU", "es": "ES"}

PIPELINE_STATES = [
    "IDEA_RECEIVED",
    "SPEC_WRITTEN",
    "MARKET_CONTENT_READY",
    "METHODOLOGY_REVIEWED",
    "ARCH_DESIGNED",
    "CODE_COMMITTED",
    "QA_TESTING",
    "SECURITY_SCANNED",
    "SALES_ACTIVE",
    "SANDBOX_RUNNING",
    "TELEMETRY_COLLECTING",
    "EVOLUTION_ANALYZING",
]

CRYPTO_CHAINS = [
    {"name": "Base", "tokens": "USDT, USDC"},
    {"name": "Solana", "tokens": "USDT, USDC"},
    {"name": "Arbitrum", "tokens": "USDT, USDC"},
]

TOP_LEVEL_KEYS = [
    "locale",
    "localeNames",
    "localeLabels",
    "nav",
    "hero",
    "footer",
    "ui",
    "sectionTitles",
    "overview",
    "userGuide",
    "ownerGuide",
    "architecture",
    "quickstart",
    "adminPanel",
    "apiReference",
    "cli",
    "agents",
    "pipeline",
    "crypto",
    "security",
    "director",
    "configuration",
]


def _t(locale: str, en: str, ru: str, es: str) -> str:
    return {"en": en, "ru": ru, "es": es}[locale]


def _nav(locale: str) -> dict[str, str]:
    return {
        "home": _t(locale, "Home", "Главная", "Inicio"),
        "docs": _t(locale, "Docs", "Документация", "Documentación"),
        "admin": _t(locale, "Admin", "Админ", "Admin"),
        "toggle": _t(locale, "Toggle menu", "Меню", "Menú"),
    }


def _hero(locale: str) -> dict[str, str]:
    return {
        "backToHome": _t(locale, "Back to Home", "На главную", "Volver al inicio"),
        "title": _t(locale, "Documentation", "Документация", "Documentación"),
        "subtitle": _t(
            locale,
            "Architecture, quick start, owner playbook with visuals, API reference, CLI truth table, and links to the Markdown handbooks in docs/.",
            "Архитектура, быстрый старт, плейбук владельца с визуалами, справочник API, таблица истинности CLI и ссылки на Markdown-справочники в docs/.",
            "Arquitectura, inicio rápido, manual del operador con visuales, referencia API, tabla de verdad CLI y enlaces a los manuales Markdown en docs/.",
        ),
    }


def _footer(locale: str) -> dict[str, str]:
    return {
        "tagline": _t(locale, "AI-Factory v2.1 — Documentation", "AI-Factory v2.1 — Документация", "AI-Factory v2.1 — Documentación"),
        "home": _t(locale, "Home", "Главная", "Inicio"),
        "admin": _t(locale, "Admin", "Админ", "Admin"),
        "apiDocs": _t(locale, "API Docs", "API Docs", "API Docs"),
        "github": _t(locale, "GitHub", "GitHub", "GitHub"),
    }


def _ui(locale: str) -> dict[str, str]:
    return {
        "copyCode": _t(locale, "Copy code", "Копировать код", "Copiar código"),
        "screenshotNotBundled": _t(locale, "Screenshot not bundled", "Скриншот не включён", "Captura no incluida"),
        "screenshotHintPrefix": _t(locale, "From", "Из", "Desde"),
        "screenshotHintRun": _t(locale, "run", "выполните", "ejecute"),
        "screenshotHintMiddle": _t(
            locale,
            " with the app reachable (",
            " при доступном приложении (",
            " con la app accesible (",
        ),
        "screenshotHintEnv": "DOCS_SCREENSHOT_BASE_URL",
        "screenshotHintAnd": _t(locale, ", ", ", ", ", "),
        "screenshotHintPassword": "ADMIN_PASSWORD",
    }


def _section_titles(locale: str) -> dict[str, str]:
    return {
        "overview": _t(locale, "Overview", "Обзор", "Resumen"),
        "userGuide": _t(locale, "User guide", "Руководство пользователя", "Guía de usuario"),
        "ownerGuide": _t(locale, "Owner playbook", "Плейбук владельца", "Manual del operador"),
        "architecture": _t(locale, "Architecture", "Архитектура", "Arquitectura"),
        "quickstart": _t(locale, "Quick Start", "Быстрый старт", "Inicio rápido"),
        "adminPanel": _t(locale, "Admin Panel", "Админ-панель", "Panel de administración"),
        "apiReference": _t(locale, "API Reference", "Справочник API", "Referencia API"),
        "cli": _t(locale, "CLI Commands", "Команды CLI", "Comandos CLI"),
        "agents": _t(locale, "AI Agents", "ИИ-агенты", "Agentes de IA"),
        "pipeline": _t(locale, "Pipeline Flow", "Конвейер", "Flujo del pipeline"),
        "crypto": _t(locale, "Crypto Payments", "Криптоплатежи", "Pagos cripto"),
        "security": _t(locale, "Security", "Безопасность", "Seguridad"),
        "director": _t(locale, "Director AI", "Director AI", "Director AI"),
        "configuration": _t(locale, "Configuration", "Конфигурация", "Configuración"),
    }


def _overview(locale: str) -> dict[str, Any]:
    return {
        "title": "AI-Factory v2.1",
        "badge": _t(locale, "AI Company Platform · Single Docker Stack", "Платформа AI Company · один Docker-стек", "Plataforma AI Company · un solo stack Docker"),
        "intro": _t(
            locale,
            "Production-grade stack in one container (FastAPI + Next.js).",
            "Промышленный стек в одном контейнере (FastAPI + Next.js).",
            "Stack de producción en un contenedor (FastAPI + Next.js).",
        ),
        "introPipeline": _t(locale, "One multi-agent pipeline", "Один мультиагентный конвейер", "Un pipeline multiagente"),
        "introPipelineSuffix": _t(locale, " for everything:", " для всего:", " para todo:"),
        "introAutonomous": _t(locale, "autonomous", "автономный", "autónomo"),
        "introAutonomousSuffix": _t(
            locale,
            " mode feeds market research and generated ideas;",
            " режим питает исследование рынка и сгенерированные идеи;",
            " modo alimenta investigación de mercado e ideas generadas;",
        ),
        "introOnDemand": _t(locale, "on-demand", "по запросу", "bajo demanda"),
        "introOnDemandSuffix": _t(
            locale,
            " mode starts from the customer's phrase — same stages, same QA gates.",
            " режим стартует с формулировки заказчика — те же этапы и те же QA-ворота.",
            " modo arranca con la frase del cliente — mismas etapas y mismos controles QA.",
        ),
        "introMiddle": "",
        "introEnd": _t(
            locale,
            "Typical deliverables are share-ready landings; crypto checkout and sandbox preview ship with the bundle.",
            "Типичный результат — готовые к публикации лендинги; крипто-оплата и превью в песочнице входят в поставку.",
            "Las entregas típicas son landings listos para compartir; checkout cripto y vista previa en sandbox van incluidos.",
        ),
        "coreCapabilities": _t(locale, "Core Capabilities", "Ключевые возможности", "Capacidades principales"),
        "capabilities": [
            _t(
                locale,
                "Specialized pipeline roles in the admin roster: Analyst, PM, Methodologist, Architect, Designer (UX), Developer, QA, Security, DevOps, Marketing, Sales, Evolution Analyst — plus Director as a meta-agent. `agents/` in the repo is the source of truth; `ui_experience` in architecture is the binding UX brief for the Developer.",
                "Специализированные роли конвейера в админ-ростере: Analyst, PM, Methodologist, Architect, Designer (UX), Developer, QA, Security, DevOps, Marketing, Sales, Evolution Analyst — плюс Director как мета-агент. `agents/` в репозитории — источник истины; `ui_experience` в архитектуре — обязательный UX-бриф для Developer.",
                "Roles especializados del pipeline en el roster admin: Analyst, PM, Methodologist, Architect, Designer (UX), Developer, QA, Security, DevOps, Marketing, Sales, Evolution Analyst — más Director como metaagente. `agents/` en el repo es la fuente de verdad; `ui_experience` en arquitectura es el brief UX vinculante para Developer.",
            ),
            _t(locale, "Multi-LLM routing with failover — local Ollama, DeepSeek, Together, Groq", "Маршрутизация нескольких LLM с failover — локальный Ollama, DeepSeek, Together, Groq", "Enrutamiento multi-LLM con failover — Ollama local, DeepSeek, Together, Groq"),
            _t(locale, "Director AI — scheduled analysis, decisions queue, reports", "Director AI — плановый анализ, очередь решений, отчёты", "Director AI — análisis programado, cola de decisiones, informes"),
            _t(locale, "Crypto storefront — USDT/USDC (Base, Arbitrum, Ethereum, Solana); default list ~$4.99 USDT when sales artifacts omit price", "Крипто-витрина — USDT/USDC (Base, Arbitrum, Ethereum, Solana); цена по умолчанию ~$4.99 USDT, если артефакты sales не задают цену", "Tienda cripto — USDT/USDC (Base, Arbitrum, Ethereum, Solana); listado por defecto ~$4.99 USDT si los artefactos de ventas omiten precio"),
            _t(locale, "Glass storefront & admin — animations, responsive layout", "Стеклянная витрина и админка — анимации, адаптивная вёрстка", "Tienda y admin tipo glass — animaciones, diseño responsive"),
            _t(locale, "Enterprise-minded ops — secrets paths, audit hooks, sandbox isolation", "Операции enterprise-уровня — пути секретов, аудит, изоляция песочниц", "Operaciones enterprise — rutas de secretos, auditoría, aislamiento de sandbox"),
            _t(locale, "CLI companion for operators (`ai-company` where installed)", "CLI-компаньон для операторов (`ai-company` при установке)", "CLI para operadores (`ai-company` donde esté instalado)"),
            _t(locale, "Evolution loop — telemetry-driven improvements", "Цикл эволюции — улучшения на основе телеметрии", "Bucle de evolución — mejoras basadas en telemetría"),
        ],
        "atAGlance": _t(locale, "At a glance", "Кратко", "De un vistazo"),
        "stats": [
            {"label": _t(locale, "Deploy model", "Модель деплоя", "Modelo de despliegue"), "value": "Compose"},
            {"label": _t(locale, "Quality gates", "QA-ворота", "Controles de calidad"), "value": "Demo + QA"},
            {"label": _t(locale, "Pricing default", "Цена по умолчанию", "Precio por defecto"), "value": "~$5"},
            {"label": _t(locale, "Stack depth", "Глубина стека", "Profundidad del stack"), "value": "Full"},
        ],
        "singleContainerTitle": _t(locale, "Single Container", "Один контейнер", "Un solo contenedor"),
        "singleContainerBody": _t(
            locale,
            "Everything runs in one Docker container (Ubuntu 24.04, Python 3.12, Node.js 20). No external dependencies required.",
            "Всё работает в одном Docker-контейнере (Ubuntu 24.04, Python 3.12, Node.js 20). Внешние зависимости не требуются.",
            "Todo corre en un contenedor Docker (Ubuntu 24.04, Python 3.12, Node.js 20). No requiere dependencias externas.",
        ),
        "handbookTitle": _t(locale, "Canonical handbook (Markdown)", "Канонический справочник (Markdown)", "Manual canónico (Markdown)"),
        "handbookBodyPrefix": _t(
            locale,
            "For printable diagrams (Mermaid), full scenario tables, and pitfalls see ",
            "Печатные диаграммы (Mermaid), полные таблицы сценариев и подводные камни — в ",
            "Diagramas imprimibles (Mermaid), tablas de escenarios y trampas — véase ",
        ),
        "handbookBodyPath": "docs/owner-guide.md",
        "handbookBodySuffix": _t(
            locale,
            " in the repository — kept in sync with this tab.",
            " в репозитории — синхронизирован с этой вкладкой.",
            " en el repositorio — sincronizado con esta pestaña.",
        ),
        "userGuideBoxTitle": _t(locale, "Illustrated User Guide", "Иллюстрированное руководство", "Guía ilustrada"),
        "userGuideBoxPrefix": _t(
            locale,
            "Step-by-step “for dummies” usage with screenshots: ",
            "Пошаговое использование «для чайников» со скриншотами: ",
            "Uso paso a paso «para principiantes» con capturas: ",
        ),
        "userGuideBoxPath": "docs/USER_GUIDE.md",
        "userGuideBoxTab": _t(locale, "User guide", "Руководство пользователя", "Guía de usuario"),
        "userGuideBoxSuffix": _t(locale, " tab here on ", " здесь на ", " aquí en "),
        "userGuideBoxDocsPath": "/docs",
    }


def _user_guide(locale: str) -> dict[str, Any]:
    return {
        "titlePrefix": _t(locale, "Illustrated ", "Иллюстрированное ", "Guía ilustrada "),
        "titleGradient": _t(locale, "User Guide", "руководство пользователя", "de usuario"),
        "badge": _t(
            locale,
            "For dummies · Storefront + Admin · Screenshots refreshed from your running stack",
            "Для начинающих · Витрина + Админ · Скриншоты с вашего работающего стека",
            "Para principiantes · Tienda + Admin · Capturas de su stack en ejecución",
        ),
        "intro": _t(
            locale,
            "The canonical Markdown lives in docs/USER_GUIDE.md inside the repository. It is written for operators who need a gentle path before diving into docs/admin-guide.md (every tab, every API touchpoint).",
            "Канонический Markdown — docs/USER_GUIDE.md в репозитории. Для операторов, которым нужен мягкий вход перед docs/admin-guide.md (каждая вкладка, каждый API touchpoint).",
            "El Markdown canónico está en docs/USER_GUIDE.md en el repositorio. Para operadores que necesitan un camino suave antes de docs/admin-guide.md (cada pestaña, cada API touchpoint).",
        ),
        "whatYouWillLearnTitle": _t(locale, "What you will learn", "Чему вы научитесь", "Qué aprenderá"),
        "whatYouWillLearnItems": [
            _t(locale, "How the storefront, `/docs`, and `/admin` relate.", "Как связаны витрина, `/docs` и `/admin`.", "Cómo se relacionan la tienda, `/docs` y `/admin`."),
            _t(locale, "First-day checklist: login → New product wizard → Pipeline.", "Чеклист первого дня: вход → мастер New product → Pipeline.", "Lista del primer día: login → asistente New product → Pipeline."),
            _t(locale, "New Product: progress bar, quick-start templates, local vs cloud templates, AI prefill consent, actionable errors.", "New Product: progress bar, quick-start templates, local vs cloud templates, AI prefill consent, actionable errors.", "New Product: barra de progreso, plantillas quick-start, local vs cloud, consentimiento AI prefill, errores accionables."),
            _t(locale, "Workshop: board, spec/architecture diff, iteration canvas, multi-device lab, pattern library, Web Push.", "Workshop: board, spec/architecture diff, iteration canvas, multi-device lab, pattern library, Web Push.", "Workshop: board, diff spec/arquitectura, iteration canvas, multi-device lab, pattern library, Web Push."),
            _t(locale, "Where to click when LLM or network errors appear (links are embedded in red panels in the live UI).", "Куда нажимать при ошибках LLM или сети (ссылки в красных панелях live UI).", "Dónde hacer clic cuando aparecen errores LLM o de red (enlaces en paneles rojos del UI en vivo)."),
        ],
        "screenshotsTitle": _t(locale, "Screenshots (latest capture)", "Скриншоты (последний захват)", "Capturas (última grabación)"),
        "screenshotsRegenerate": _t(
            locale,
            "Regenerate anytime: cd web/frontend && npm run capture-docs-screenshots",
            "Пересоздать: cd web/frontend && npm run capture-docs-screenshots",
            "Regenerar: cd web/frontend && npm run capture-docs-screenshots",
        ),
        "captions": {
            "publicHome": _t(locale, "Storefront home — public entry.", "Главная витрины — публичный вход.", "Inicio de la tienda — entrada pública."),
            "publicDocs": _t(locale, "In-app documentation — this site.", "Встроенная документация — этот сайт.", "Documentación in-app — este sitio."),
            "adminNewProduct": _t(locale, "New product — guided wizard + templates.", "New product — мастер + шаблоны.", "New product — asistente guiado + plantillas."),
            "adminWorkshop": _t(locale, "Workshop — board, diffs, canvas, patterns, push.", "Workshop — board, diffs, canvas, patterns, push.", "Workshop — board, diffs, canvas, patterns, push."),
            "adminPipeline": _t(locale, "Pipeline — operational truth for every prod-… id.", "Pipeline — операционная правда для каждого prod-… id.", "Pipeline — verdad operativa para cada prod-… id."),
        },
        "offlineTitle": _t(locale, "Offline / PDF", "Офлайн / PDF", "Offline / PDF"),
        "offlineBodyPrefix": _t(locale, "Open ", "Откройте ", "Abra "),
        "offlineBodyPath1": "docs/USER_GUIDE.md",
        "offlineBodyMiddle": _t(
            locale,
            " in your editor or GitHub and print to PDF if leadership wants a paper packet. Mermaid-heavy owner content stays in ",
            " в редакторе или GitHub и экспортируйте в PDF. Контент владельца с Mermaid — в ",
            " en su editor o GitHub e imprima a PDF si el liderazgo quiere un paquete en papel. El contenido del operador con Mermaid permanece en ",
        ),
        "offlineBodyPath2": "docs/owner-guide.md",
    }


def _owner_guide(locale: str) -> dict[str, Any]:
    return {
        "titlePrefix": _t(locale, "Platform ", "Платформенный ", "Plataforma "),
        "titleGradient": _t(locale, "owner playbook", "плейбук владельца", "manual del operador"),
        "badge": _t(
            locale,
            "Operator scenarios · Storefront policy · Support vs pipeline",
            "Сценарии оператора · Политика витрины · Support vs pipeline",
            "Escenarios del operador · Política de tienda · Support vs pipeline",
        ),
        "intro": _t(
            locale,
            "This section is for the person running a deployed instance: provisioning LLMs, watching the pipeline, curating the marketplace, and helping buyers. Deep tab reference lives in docs/admin-guide.md; REST patterns in docs/api-integration-guide.md.",
            "Для того, кто эксплуатирует инстанс: LLM, pipeline, маркетплейс, поддержка покупателей. Подробности вкладок — docs/admin-guide.md; REST — docs/api-integration-guide.md.",
            "Para quien opera una instancia desplegada: aprovisionar LLM, vigilar el pipeline, curar el marketplace y ayudar a compradores. Referencia de pestañas en docs/admin-guide.md; REST en docs/api-integration-guide.md.",
        ),
        "visualMapTitle": _t(locale, "Visual map", "Визуальная карта", "Mapa visual"),
        "operatorControlPlane": _t(locale, "Operator control plane", "Плоскость управления оператора", "Plano de control del operador"),
        "firstDayTitle": _t(locale, "Step-by-step — first day", "Пошагово — первый день", "Paso a paso — primer día"),
        "firstDayItems": [
            _t(locale, "Confirm a host bind mount for /app/data (see root README — avoid anonymous Docker volumes).", "Подтвердите bind mount /app/data на хосте (см. README — без anonymous Docker volumes).", "Confirme bind mount de /app/data en el host (véase README — evite volúmenes Docker anónimos)."),
            _t(locale, "Sign in at /admin/login and rotate the admin password; enable TOTP if desired.", "Войдите на /admin/login и смените пароль admin; включите TOTP при необходимости.", "Inicie sesión en /admin/login y rote la contraseña admin; habilite TOTP si desea."),
            _t(locale, "Open LLM Providers — wire at least one model backend and verify routing rules.", "Откройте LLM Providers — подключите backend и проверьте routing rules.", "Abra LLM Providers — conecte al menos un backend y verifique routing rules."),
            _t(locale, "Submit an idea from New Product or run CLI discover / create-idea inside the container.", "Отправьте идею из New Product или CLI discover / create-idea в контейнере.", "Envíe una idea desde New Product o ejecute CLI discover / create-idea en el contenedor."),
            _t(locale, "Watch Pipeline — expand a card, click stage tiles for task payloads and errors.", "Следите за Pipeline — раскройте карточку, кликайте этапы для payload и ошибок.", "Observe Pipeline — expanda una tarjeta, haga clic en etapas para payloads y errores."),
            _t(locale, "Optional: run README full_pipeline_smoke.py against a completed product ID.", "Опционально: README full_pipeline_smoke.py для завершённого product ID.", "Opcional: README full_pipeline_smoke.py contra un product ID completado."),
        ],
        "marketplaceTitle": _t(locale, "Step-by-step — marketplace curation", "Пошагово — курация маркетплейса", "Paso a paso — curación del marketplace"),
        "marketplaceItems": [
            _t(locale, "Locate a COMPLETED row → Storefront panel.", "Найдите строку COMPLETED → панель Storefront.", "Localice fila COMPLETED → panel Storefront."),
            _t(locale, "Edit Marketplace copy to tune card/detail text (persisted to marketing_content.json).", "Редактируйте Marketplace copy (сохраняется в marketing_content.json).", "Edite Marketplace copy para ajustar texto de tarjeta/detalle (persistido en marketing_content.json)."),
            _t(locale, "If automatic quality gates block listing but you accept the risk: Force public storefront + justification.", "Если quality gates блокируют листинг, но риск приемлем: Force public storefront + justification.", "Si quality gates bloquean el listado pero acepta el riesgo: Force public storefront + justification."),
            _t(locale, "To pull a SKU offline: Not pursuing (with reason) or Hide from public storefront — shoppers lose listing + detail 404.", "Снять SKU: Not pursuing (с причиной) или Hide from public storefront — покупатели теряют listing + detail 404.", "Retirar SKU: Not pursuing (con razón) o Hide from public storefront — compradores pierden listing + detail 404."),
            _t(locale, "Remember: Dashboard “Completed” counts lifecycle; storefront visibility adds code + quality + hide rules.", "Помните: Dashboard «Completed» — lifecycle; видимость витрины добавляет code + quality + hide rules.", "Recuerde: Dashboard «Completed» cuenta lifecycle; visibilidad en tienda añade code + quality + hide rules."),
        ],
        "useCaseCards": [
            {
                "title": _t(locale, "Burst intake", "Burst intake", "Burst intake"),
                "body": _t(locale, "CLI create-ideas-batch or POST /api/admin/products/create-batch after validating LLM quota.", "CLI create-ideas-batch или POST /api/admin/products/create-batch после проверки LLM quota.", "CLI create-ideas-batch o POST /api/admin/products/create-batch tras validar cuota LLM."),
            },
            {
                "title": _t(locale, "Stuck stage", "Stuck stage", "Stuck stage"),
                "body": _t(locale, "Pipeline modal → inspect failing agent → LLM Logs + provider routing → optional human rework.", "Pipeline modal → failing agent → LLM Logs + provider routing → optional human rework.", "Pipeline modal → inspeccionar agente fallido → LLM Logs + provider routing → rework humano opcional."),
            },
            {
                "title": _t(locale, "Buyer confusion", "Buyer confusion", "Buyer confusion"),
                "body": _t(locale, "Lumen (/api/support) handles chat; tune RAG baseline markdown under backend services if branding changes.", "Lumen (/api/support) — чат; настройте RAG baseline markdown в backend services при смене брендинга.", "Lumen (/api/support) maneja chat; ajuste RAG baseline markdown en backend services si cambia el branding."),
            },
            {
                "title": _t(locale, "Discovery backlog", "Discovery backlog", "Discovery backlog"),
                "body": _t(locale, "Director discovery ranking → enqueue winners — documented in README + pipeline-operations.md.", "Director discovery ranking → enqueue winners — в README + pipeline-operations.md.", "Director discovery ranking → enqueue winners — documentado en README + pipeline-operations.md."),
            },
        ],
        "listingFlowTitle": _t(locale, "Listing decision flow", "Поток решения о листинге", "Flujo de decisión de listado"),
        "listingShippedQuestion": _t(locale, "Shipped + code on disk?", "Shipped + code on disk?", "¿Shipped + code on disk?"),
        "listingShippedNo": _t(locale, "No → never listed", "No → never listed", "No → never listed"),
        "listingHiddenQuestion": _t(locale, "Hidden / Not pursuing?", "Hidden / Not pursuing?", "¿Hidden / Not pursuing?"),
        "listingHiddenYes": _t(locale, "Yes → 404 on public catalog + detail", "Yes → 404 on public catalog + detail", "Sí → 404 en catálogo público + detail"),
        "listingQualityQuestion": _t(locale, "Passes marketplace quality OR admin force-list?", "Passes marketplace quality OR admin force-list?", "¿Pasa marketplace quality OR admin force-list?"),
        "listingQualityYes": _t(locale, "Yes → visible on storefront", "Yes → visible on storefront", "Sí → visible on storefront"),
        "screenshotsTitle": _t(locale, "Screenshots", "Скриншоты", "Capturas"),
        "screenshotsIntro": _t(
            locale,
            "Captured into the repo and mirrored to /docs-screenshots/ for this page.",
            "Сохранены в репозитории и зеркалированы в /docs-screenshots/ для этой страницы.",
            "Capturadas en el repo y reflejadas en /docs-screenshots/ para esta página.",
        ),
        "captions": {
            "adminLogin": _t(locale, "Admin login — rotate credentials on day one.", "Admin login — смените учётные данные в первый день.", "Admin login — rote credenciales el primer día."),
            "adminDashboard": _t(locale, "Dashboard snapshot — differs from storefront-visible counts.", "Dashboard — отличается от счётчиков видимых на витрине.", "Dashboard — difiere de conteos visibles en tienda."),
            "adminPipeline": _t(locale, "Pipeline monitor — storefront controls live inside expanded completed cards.", "Pipeline — управление витриной внутри раскрытых completed cards.", "Pipeline — controles de tienda dentro de tarjetas completed expandidas."),
            "adminNewProduct": _t(locale, "New product — guided wizard, quick-start chips, cloud templates.", "New product — мастер, quick-start chips, cloud templates.", "New product — asistente, chips quick-start, plantillas cloud."),
            "adminWorkshop": _t(locale, "Workshop — material diff, iteration canvas, pattern library, Web Push.", "Workshop — material diff, iteration canvas, pattern library, Web Push.", "Workshop — material diff, iteration canvas, pattern library, Web Push."),
            "adminProviders": _t(locale, "LLM Providers — keys, routing, health probes.", "LLM Providers — keys, routing, health probes.", "LLM Providers — keys, routing, health probes."),
            "adminSettings": _t(locale, "Settings — factory-wide configuration surface.", "Settings — конфигурация всей фабрики.", "Settings — superficie de configuración de la fábrica."),
        },
        "mermaidTitle": _t(locale, "Mermaid diagrams & printable PDF", "Диаграммы Mermaid и PDF", "Diagramas Mermaid y PDF imprimible"),
        "mermaidBodyPrefix": _t(locale, "GitHub renders the flowcharts in ", "GitHub рендерит блок-схемы в ", "GitHub renderiza los diagramas en "),
        "mermaidBodyPath": "docs/owner-guide.md",
        "mermaidBodySuffix": _t(
            locale,
            ". Copy that file into Notion, Confluence, or print-to-PDF for investor/operator packets.",
            ". Скопируйте в Notion, Confluence или print-to-PDF для инвесторов/операторов.",
            ". Cópielo a Notion, Confluence o imprima a PDF para paquetes de inversores/operadores.",
        ),
    }


def _architecture(locale: str) -> dict[str, Any]:
    return {
        "titleGradient": _t(locale, "Architecture", "архитектура", "arquitectura"),
        "intro": _t(
            locale,
            "AI-Factory follows a modular architecture with clear separation of concerns. All components run inside a single Docker container, communicating via internal HTTP and the filesystem.",
            "AI-Factory — модульная архитектура с чётким разделением ответственности. Все компоненты в одном Docker-контейнере, связь через internal HTTP и filesystem.",
            "AI-Factory sigue una arquitectura modular con separación clara de responsabilidades. Todos los componentes corren en un contenedor Docker, comunicándose vía HTTP interno y filesystem.",
        ),
        "componentDiagramTitle": _t(locale, "Component Diagram", "Диаграмма компонентов", "Diagrama de componentes"),
        "requestFlow": _t(locale, "Request Flow", "Поток запросов", "Flujo de solicitudes"),
        "requestFlowBody": _t(
            locale,
            "User requests go to Next.js on port 8080. API calls to /api/* are proxied by Next.js rewrites to the FastAPI backend on port 8081. The admin panel is served by Next.js as well.",
            "Запросы пользователей идут в Next.js на порту 8080. Вызовы /api/* проксируются Next.js rewrites на FastAPI backend на 8081. Admin panel тоже обслуживает Next.js.",
            "Las solicitudes van a Next.js en el puerto 8080. Las llamadas a /api/* se proxyan vía Next.js rewrites al backend FastAPI en 8081. El panel admin también lo sirve Next.js.",
        ),
    }


def _quickstart(locale: str) -> dict[str, Any]:
    return {
        "titleGradient": _t(locale, "Start", "старт", "inicio"),
        "intro": _t(
            locale,
            "Deploy and run the AI-Factory platform with a single Docker command.",
            "Разверните и запустите AI-Factory одной Docker-командой.",
            "Despliegue y ejecute AI-Factory con un solo comando Docker.",
        ),
        "step1": _t(locale, "1. Build the Image", "1. Сборка образа", "1. Construir la imagen"),
        "step2": _t(locale, "2. Run the Container", "2. Запуск контейнера", "2. Ejecutar el contenedor"),
        "step3": _t(locale, "3. Access the Platform", "3. Доступ к платформе", "3. Acceder a la plataforma"),
        "accessLinks": [
            {"label": _t(locale, "Storefront", "Витрина", "Tienda"), "url": "http://localhost:8080", "note": ""},
            {"label": _t(locale, "Admin Panel", "Админ-панель", "Panel admin"), "url": "http://localhost:8080/admin", "note": ""},
            {"label": _t(locale, "API Docs", "API Docs", "API Docs"), "url": "http://localhost:8080/api/docs", "note": "(FastAPI Swagger)"},
        ],
        "step4": _t(locale, "4. Login to Admin", "4. Вход в Admin", "4. Iniciar sesión en Admin"),
        "loginIntro": _t(
            locale,
            "There is no default admin123 password. On first startup with an empty data volume, the entrypoint asks for a password in the console when stdin is a TTY; otherwise it writes a one-time password to data/secrets/bootstrap_admin.txt. See docs/security.md in the repository.",
            "Нет пароля admin123 по умолчанию. При первом старте с пустым data volume entrypoint запрашивает пароль в консоли при TTY; иначе пишет one-time password в data/secrets/bootstrap_admin.txt. См. docs/security.md.",
            "No hay contraseña admin123 por defecto. En el primer arranque con volumen data vacío, el entrypoint pide contraseña en consola con TTY; si no, escribe one-time password en data/secrets/bootstrap_admin.txt. Véase docs/security.md.",
        ),
        "loginItems": [
            _t(locale, "Username: admin", "Username: admin", "Username: admin"),
            _t(locale, "Password: set at first bootstrap (console prompt or bootstrap file)", "Password: задаётся при первом bootstrap (консоль или bootstrap file)", "Password: se define en el primer bootstrap (consola o bootstrap file)"),
            _t(locale, "Navigate to /admin/login and sign in", "Перейдите на /admin/login и войдите", "Vaya a /admin/login e inicie sesión"),
            _t(locale, "Dev only: AIFACTORY_DEV_BOOTSTRAP_PASSWORD in .env", "Dev only: AIFACTORY_DEV_BOOTSTRAP_PASSWORD в .env", "Dev only: AIFACTORY_DEV_BOOTSTRAP_PASSWORD en .env"),
        ],
        "step5": _t(locale, "5. Create Your First Product", "5. Создайте первый продукт", "5. Cree su primer producto"),
        "dockerSandboxTitle": _t(locale, "Docker sandbox", "Docker sandbox", "Docker sandbox"),
        "dockerSandboxBody": _t(
            locale,
            "The factory image can run isolated preview containers (network none, dropped capabilities). Host-gateway to reach Ollama on the host is opt-in via docker-compose.host-gateway.yml — not enabled by default.",
            "Образ фабрики может запускать изолированные preview containers (network none, dropped capabilities). Host-gateway для Ollama на хосте — opt-in через docker-compose.host-gateway.yml — не включено по умолчанию.",
            "La imagen puede ejecutar preview containers aislados (network none, dropped capabilities). Host-gateway para Ollama en el host es opt-in vía docker-compose.host-gateway.yml — no habilitado por defecto.",
        ),
    }


def _admin_panel(locale: str) -> dict[str, Any]:
    return {
        "titleGradient": _t(locale, "Panel", "панель", "panel"),
        "intro": _t(
            locale,
            "The admin panel at /admin provides complete control over the AI-Factory platform. It is protected by JWT-based authentication with optional 2FA (TOTP).",
            "Admin panel на /admin — полный контроль над AI-Factory. Защита JWT-аутентификацией с опциональной 2FA (TOTP).",
            "El panel admin en /admin controla AI-Factory. Protegido con autenticación JWT y 2FA opcional (TOTP).",
        ),
        "authTitle": _t(locale, "Authentication", "Аутентификация", "Autenticación"),
        "authIntro": "",
        "authItems": [
            _t(locale, "JWT tokens with HTTP-only cookies", "JWT tokens с HTTP-only cookies", "JWT tokens con cookies HTTP-only"),
            _t(locale, "30-minute inactivity auto-logout", "Auto-logout через 30 минут неактивности", "Auto-logout tras 30 minutos de inactividad"),
            _t(locale, "Brute-force protection: max 5 failed attempts per 15 minutes", "Защита brute-force: макс. 5 неудачных попыток за 15 минут", "Protección brute-force: máx. 5 intentos fallidos por 15 minutos"),
            _t(locale, "Optional 2FA via Google Authenticator (TOTP)", "Опциональная 2FA через Google Authenticator (TOTP)", "2FA opcional vía Google Authenticator (TOTP)"),
        ],
        "dashboardTitle": _t(locale, "Dashboard Tab", "Вкладка Dashboard", "Pestaña Dashboard"),
        "dashboardIntro": _t(locale, "Real-time metrics overview including:", "Обзор метрик в реальном времени:", "Resumen de métricas en tiempo real:"),
        "dashboardItems": [
            _t(locale, "Pipeline metrics — total/active/completed/failed products, pending/running/timed-out tasks", "Pipeline metrics — total/active/completed/failed products, pending/running/timed-out tasks", "Pipeline metrics — total/active/completed/failed products, pending/running/timed-out tasks"),
            _t(locale, "Resource usage — CPU, memory, disk utilization", "Resource usage — CPU, memory, disk utilization", "Resource usage — CPU, memory, disk utilization"),
            _t(locale, "Revenue — earnings over last 24h, 7d, 30d", "Revenue — earnings over last 24h, 7d, 30d", "Revenue — earnings over last 24h, 7d, 30d"),
            _t(locale, "Security status — system health indicator, recent failed logins", "Security status — system health indicator, recent failed logins", "Security status — system health indicator, recent failed logins"),
        ],
        "providersTitle": _t(locale, "Model Providers Tab", "Вкладка Model Providers", "Pestaña Model Providers"),
        "providersIntro": _t(locale, "Configure and manage LLM providers:", "Настройка и управление LLM providers:", "Configure y gestione LLM providers:"),
        "providersItems": [
            _t(locale, "View all configured providers with status (online/offline/degraded)", "Все providers со статусом (online/offline/degraded)", "Ver providers con estado (online/offline/degraded)"),
            _t(locale, "Toggle providers enabled/disabled", "Включение/отключение providers", "Activar/desactivar providers"),
            _t(locale, "Monitor latency and model availability", "Мониторинг latency и доступности моделей", "Monitorear latency y disponibilidad de modelos"),
            _t(locale, "Configure routing rules per task type", "Routing rules по типу задачи", "Configurar routing rules por task type"),
        ],
        "agentsTitle": _t(locale, "Agents Tab", "Вкладка Agents", "Pestaña Agents"),
        "agentsIntro": _t(locale, "Monitor and configure AI agents:", "Мониторинг и настройка AI agents:", "Monitorear y configurar AI agents:"),
        "agentsItems": [
            _t(locale, "View status of all 11 pipeline roles (including Designer)", "Статус всех 11 pipeline roles (включая Designer)", "Estado de los 11 pipeline roles (incl. Designer)"),
            _t(locale, "Configure timeouts, retry limits, and priorities", "Timeouts, retry limits и priorities", "Configurar timeouts, retry limits y priorities"),
            _t(locale, "View agent logs with filtering", "Логи agents с фильтрацией", "Ver logs de agents con filtros"),
            _t(locale, "Restart individual agents if needed", "Перезапуск отдельных agents при необходимости", "Reiniciar agents individuales si hace falta"),
        ],
        "securityTitle": _t(locale, "Security Tab", "Вкладка Security", "Pestaña Security"),
        "securityIntro": _t(locale, "Security monitoring and configuration:", "Мониторинг и настройка безопасности:", "Monitoreo y configuración de seguridad:"),
        "securityItems": [
            _t(locale, "View audit logs with date/action/user filters", "Audit logs с фильтрами date/action/user", "Audit logs con filtros date/action/user"),
            _t(locale, "Export logs in JSON format", "Экспорт logs в JSON", "Exportar logs en JSON"),
            _t(locale, "Change admin password", "Смена пароля admin", "Cambiar contraseña admin"),
            _t(locale, "Configure 2FA", "Настройка 2FA", "Configurar 2FA"),
        ],
        "directorTitle": _t(locale, "Director Tab", "Вкладка Director", "Pestaña Director"),
        "directorIntro": _t(locale, "Director AI management:", "Управление Director AI:", "Gestión de Director AI:"),
        "directorItems": [
            _t(locale, "View latest Director reports with metrics and recommendations", "Последние отчёты Director с метриками и рекомендациями", "Últimos informes Director con métricas y recomendaciones"),
            _t(locale, "Configure analysis frequency (1/2/4/12 hours)", "Частота анализа (1/2/4/12 hours)", "Frecuencia de análisis (1/2/4/12 hours)"),
            _t(locale, "Toggle automatic actions on/off", "Включение/отключение automatic actions", "Activar/desactivar automatic actions"),
            _t(locale, "Trigger manual analysis for testing", "Ручной запуск анализа для тестов", "Disparar análisis manual para pruebas"),
        ],
        "settingsTitle": _t(locale, "Settings Tab", "Вкладка Settings", "Pestaña Settings"),
        "settingsIntro": _t(locale, "Storefront theme customization:", "Настройка темы витрины:", "Personalización de tema de tienda:"),
        "settingsItems": [
            _t(locale, "Choose from 5 themes: Cyberpunk, Minimal, Glass, Neon, Corporate", "5 тем: Cyberpunk, Minimal, Glass, Neon, Corporate", "5 temas: Cyberpunk, Minimal, Glass, Neon, Corporate"),
            _t(locale, "Theme applies dynamically without page reload", "Тема применяется без перезагрузки страницы", "El tema se aplica sin recargar la página"),
        ],
    }


def _api_endpoint(
    locale: str,
    method: str,
    path: str,
    desc_en: str,
    desc_ru: str,
    desc_es: str,
    code: str | None = None,
    code_lang: str | None = None,
) -> dict[str, Any]:
    ep: dict[str, Any] = {
        "method": method,
        "path": path,
        "description": _t(locale, desc_en, desc_ru, desc_es),
    }
    if code is not None:
        ep["code"] = code
    if code_lang is not None:
        ep["codeLanguage"] = code_lang
    return ep


def _api_reference(locale: str) -> dict[str, Any]:
    health_code = 'Response:\n{\n  "status": "ok",\n  "version": "2.1.0",\n  "service": "ai-factory-backend"\n}'
    login_code = (
        'Request:\n{\n  "username": "admin",\n  "password": "your_password",\n'
        '  "totp_code": "123456"  // optional, if 2FA enabled\n}\n\nResponse:\n{\n'
        '  "access_token": "eyJhbG...",\n  "token_type": "bearer",\n  "requires_2fa": false\n}'
    )
    create_code = 'Request:\n{\n  "idea": "Description of your product idea",\n  "target_audience": "developers"  // optional\n}'
    return {
        "titleGradient": _t(locale, "Reference", "справочник", "referencia"),
        "intro": _t(
            locale,
            "The FastAPI backend exposes a comprehensive REST API. All endpoints are accessible via /api/* through the Next.js proxy. Interactive documentation is available at /api/docs (Swagger UI). Raw schema: backend /openapi.json.",
            "FastAPI backend предоставляет REST API. Все endpoints доступны через /api/* прокси Next.js. Интерактивная документация: /api/docs (Swagger UI). Схема: backend /openapi.json.",
            "El backend FastAPI expone una API REST completa. Todos los endpoints vía /api/* proxy Next.js. Documentación interactiva en /api/docs (Swagger UI). Esquema: backend /openapi.json.",
        ),
        "introSwagger": "/api/docs",
        "handbookTitle": _t(locale, "Integration handbook", "Справочник интеграции", "Manual de integración"),
        "handbookBodyPrefix": _t(
            locale,
            "For authentication flows (cookie + Bearer), a grouped router map, curl snippets, and support-chat headers see ",
            "Authentication flows (cookie + Bearer), router map, curl snippets, support-chat headers — см. ",
            "Para authentication flows (cookie + Bearer), mapa de routers, curl snippets y headers support-chat véase ",
        ),
        "handbookBodyPath": "docs/api-integration-guide.md",
        "handbookBodySuffix": _t(
            locale,
            ". Swagger stays authoritative after upgrades.",
            ". Swagger остаётся авторитетным после обновлений.",
            ". Swagger sigue siendo autoritativo tras upgrades.",
        ),
        "publicEndpoints": _t(locale, "Public Endpoints", "Публичные endpoints", "Endpoints públicos"),
        "adminEndpoints": _t(locale, "Admin Endpoints (JWT Required)", "Admin endpoints (JWT Required)", "Admin endpoints (JWT Required)"),
        "endpoints": {
            "health": _api_endpoint(locale, "GET", "/api/health", "System health check. Returns status, version, and service name.", "Проверка здоровья системы. Возвращает status, version и service name.", "Health check del sistema. Devuelve status, version y service name.", health_code, "json"),
            "products": _api_endpoint(locale, "GET", "/api/products", "Storefront listing for shipped builds — filters incomplete sandboxes, marketplace quality, admin hide / not pursuing.", "Листинг витрины для shipped builds — фильтрует incomplete sandboxes, marketplace quality, admin hide / not pursuing.", "Listado de tienda para shipped builds — filtra incomplete sandboxes, marketplace quality, admin hide / not pursuing."),
            "productById": _api_endpoint(locale, "GET", "/api/products/{id}", "Product detail for public storefront — hidden SKUs return 404.", "Детали продукта для публичной витрины — hidden SKUs возвращают 404.", "Detalle de producto para tienda pública — hidden SKUs devuelven 404."),
            "support": _api_endpoint(locale, "MIXED", "/api/support/*", "Lumen support sessions & messages — often requires X-AIF-Support-Token once issued (see env AIFACTORY_SUPPORT_REQUIRE_TOKEN).", "Lumen support sessions & messages — часто требует X-AIF-Support-Token после выдачи (см. env AIFACTORY_SUPPORT_REQUIRE_TOKEN).", "Lumen support sessions & messages — a menudo requiere X-AIF-Support-Token tras emisión (véase env AIFACTORY_SUPPORT_REQUIRE_TOKEN)."),
            "sandboxRouter": _api_endpoint(locale, "ROUTER", "/api/sandbox · /api/payment · /api/customer …", "Sandbox previews, payments, feedback, marketing helpers — inspect Swagger for verbs.", "Sandbox previews, payments, feedback, marketing helpers — смотрите Swagger для verbs.", "Sandbox previews, payments, feedback, marketing helpers — inspeccione Swagger para verbs."),
            "aiMarket": _api_endpoint(locale, "PROTOCOL", "/.well-known/ai-market.json · /ai-market/*", "AI Market Protocol v1 — MCP manifest, HTTP 402 payments, channels, pipelines. Not under /api. Reference: cli/ai_market_agent.py, docs ai-market-protocol-v1.md.", "AI Market Protocol v1 — MCP manifest, HTTP 402 payments, channels, pipelines. Не под /api. Reference: cli/ai_market_agent.py, docs ai-market-protocol-v1.md.", "AI Market Protocol v1 — MCP manifest, HTTP 402 payments, channels, pipelines. No bajo /api. Reference: cli/ai_market_agent.py, docs ai-market-protocol-v1.md."),
            "theme": _api_endpoint(locale, "GET", "/api/config/theme", "Get current storefront theme configuration.", "Текущая конфигурация темы витрины.", "Obtener configuración de tema de tienda actual."),
            "adminLogin": _api_endpoint(
                locale,
                "POST",
                "/api/admin/auth/login",
                "Admin login. Sets HTTP-only cookie access_token; scripts may also send Authorization: Bearer ….",
                "Admin login. Устанавливает HTTP-only cookie access_token; скрипты могут отправлять Authorization: Bearer ….",
                "Admin login. Establece cookie HTTP-only access_token; scripts pueden enviar Authorization: Bearer ….",
                login_code,
                "json",
            ),
            "adminDashboard": _api_endpoint(locale, "GET", "/api/admin/dashboard", "Dashboard metrics: pipeline stats, resources, revenue, security.", "Метрики Dashboard: pipeline stats, resources, revenue, security.", "Métricas Dashboard: pipeline stats, resources, revenue, security."),
            "adminProviders": _api_endpoint(locale, "GET", "/api/admin/providers", "List LLM providers with status, latency, and model info.", "Список LLM providers со status, latency и model info.", "Listar LLM providers con status, latency y model info."),
            "adminAgents": _api_endpoint(locale, "GET", "/api/admin/agents", "List AI agents with status, tasks, and uptime.", "Список AI agents со status, tasks и uptime.", "Listar AI agents con status, tasks y uptime."),
            "adminSecurityLogs": _api_endpoint(locale, "GET", "/api/admin/security/logs?limit=100", "Get audit logs with optional limit parameter.", "Audit logs с опциональным limit.", "Obtener audit logs con parámetro limit opcional."),
            "adminDirectorReports": _api_endpoint(locale, "GET", "/api/admin/director/reports", "List Director AI generated reports.", "Список отчётов Director AI.", "Listar informes generados por Director AI."),
            "adminProductsCreate": _api_endpoint(locale, "POST", "/api/admin/products/create", "Create a new product from an idea.", "Создать новый продукт из идеи.", "Crear un nuevo producto desde una idea.", create_code, "json"),
            "adminMarketplaceCopy": _api_endpoint(locale, "PATCH", "/api/admin/pipeline/products/{id}/marketplace-copy", "Merge storefront-facing marketing strings for a shipped product.", "Объединить marketing strings витрины для shipped product.", "Fusionar marketing strings de tienda para un shipped product."),
            "adminStorefrontAdmin": _api_endpoint(locale, "PATCH", "/api/admin/pipeline/products/{id}/storefront-admin", "Human score, force-list override, admin hide-from-storefront flags.", "Human score, force-list override, admin hide-from-storefront flags.", "Human score, force-list override, admin hide-from-storefront flags."),
        },
    }


def _cli(locale: str) -> dict[str, Any]:
    return {
        "titleGradient": _t(locale, "Commands", "команды", "comandos"),
        "intro": _t(
            locale,
            "Commands ship with the repo in cli/ai_company_cli.py. Many README snippets use ai-company — prefer an explicit interpreter path unless your image aliases it.",
            "Команды в cli/ai_company_cli.py. В README часто ai-company — предпочитайте явный путь интерпретатора, если образ не создаёт alias.",
            "Los comandos están en cli/ai_company_cli.py. Muchos README usan ai-company — prefiera ruta explícita del intérprete salvo alias en la imagen.",
        ),
        "truthTableTitle": _t(locale, "Truth table", "Таблица истинности", "Tabla de verdad"),
        "truthTableBodyPrefix": _t(
            locale,
            "Some commands are demonstrations (wallet withdraw flow, parts of security scan). Read ",
            "Некоторые команды — демонстрации (wallet withdraw flow, части security scan). Читайте ",
            "Algunos comandos son demostraciones (wallet withdraw flow, partes de security scan). Lea ",
        ),
        "truthTableBodyPath": "docs/cli-reference.md",
        "invocationTitle": _t(locale, "Invocation", "Вызов", "Invocación"),
        "highValueTitle": _t(locale, "High-value operators", "Ключевые операции", "Operadores de alto valor"),
        "notImplementedTitle": _t(locale, "What is not implemented", "Что не реализовано", "Qué no está implementado"),
        "notImplementedItems": [
            _t(locale, "`director report --last` — open Admin Director tab or read /app/data/reports/director/*.md", "`director report --last` — Admin Director tab или /app/data/reports/director/*.md", "`director report --last` — pestaña Admin Director o /app/data/reports/director/*.md"),
            _t(locale, "`storefront preview` — use deployed Next.js or npm run dev inside web/frontend", "`storefront preview` — deployed Next.js или npm run dev в web/frontend", "`storefront preview` — Next.js desplegado o npm run dev en web/frontend"),
            _t(locale, "`restart web|orchestrator|director` — stub only; restart via Compose/systemd", "`restart web|orchestrator|director` — stub only; restart via Compose/systemd", "`restart web|orchestrator|director` — stub only; restart via Compose/systemd"),
        ],
        "preferAdminTitle": _t(locale, "Prefer Admin UI when…", "Предпочитайте Admin UI когда…", "Prefiera Admin UI cuando…"),
        "preferAdminBody": _t(
            locale,
            "Editing LLM providers with hot reload, storefront hide/marketing panels, and Live Monitor are safer via /admin than hand-editing YAML unless you know the reload semantics.",
            "Редактирование LLM providers с hot reload, storefront hide/marketing panels и Live Monitor безопаснее через /admin, чем правка YAML без знания reload semantics.",
            "Editar LLM providers con hot reload, paneles storefront hide/marketing y Live Monitor es más seguro vía /admin que editar YAML sin conocer reload semantics.",
        ),
    }


def _agents(locale: str) -> dict[str, Any]:
    cards = [
        ("Analyst", "Market research, opportunity analysis, research briefs", "Исследование рынка, анализ возможностей, research briefs", "Investigación de mercado, análisis de oportunidades, research briefs"),
        ("PM (Product Manager)", "Idea validation, market research, spec generation", "Валидация идей, исследование рынка, spec generation", "Validación de ideas, investigación de mercado, spec generation"),
        ("Methodologist", "Domain process gate — verifies that the spec and the generated code follow the accepted methodology for the product domain (CRM, helpdesk, e-commerce, …) using pluggable domain packs and a learning store of operator lessons", "Domain process gate — проверяет, что spec и код следуют методологии домена (CRM, helpdesk, e-commerce, …) через domain packs и learning store уроков операторов", "Domain process gate — verifica que spec y código sigan la metodología del dominio (CRM, helpdesk, e-commerce, …) con domain packs y learning store de lecciones"),
        ("Architect", "System design, technology stack decisions, architecture docs", "Проектирование системы, выбор стека, architecture docs", "Diseño de sistema, decisiones de stack, architecture docs"),
        ("Designer (UX layer)", "Not a separate queue task: structured ui_experience (mood, CSS variables, fonts, motion, signature moment) authored with architecture and implemented by Developer", "Не отдельная queue task: structured ui_experience (mood, CSS variables, fonts, motion, signature moment) вместе с architecture, реализует Developer", "No es queue task separada: ui_experience estructurado (mood, CSS variables, fonts, motion, signature moment) con architecture, implementado por Developer"),
        ("Developer", "Code implementation following architecture specs", "Реализация кода по architecture specs", "Implementación de código según architecture specs"),
        ("QA", "Automated testing, bug detection, code quality analysis", "Автотесты, обнаружение багов, анализ качества кода", "Testing automatizado, detección de bugs, análisis de calidad"),
        ("Security", "Vulnerability scanning, secret detection, dependency audit", "Сканирование уязвимостей, secret detection, dependency audit", "Escaneo de vulnerabilidades, secret detection, dependency audit"),
        ("DevOps", "Dockerization, deployment config, sandbox setup", "Dockerization, deployment config, sandbox setup", "Dockerization, deployment config, sandbox setup"),
        ("Marketing", "Product descriptions, landing pages, SEO content", "Описания продуктов, landing pages, SEO content", "Descripciones de producto, landing pages, SEO content"),
        ("Sales", "Pricing, payment integration, customer interaction", "Pricing, payment integration, customer interaction", "Pricing, payment integration, customer interaction"),
        ("Evolution Analyst", "Telemetry analysis, auto-improvements, A/B testing", "Анализ telemetry, auto-improvements, A/B testing", "Análisis de telemetry, auto-improvements, A/B testing"),
    ]
    return {
        "titleGradient": _t(locale, "Agents", "агенты", "agentes"),
        "intro": _t(
            locale,
            "The platform uses ten core agents plus a Methodologist gate and the Evolution Analyst meta-agent, each with a strict role. Director AI sits above the loop. Agents communicate through the filesystem — no agent can modify another agent's work. For web deliverables, the Architect also emits ui_experience (tokens, typography, motion) so the Developer ships intentional UI — shown as a dedicated ",
            "Платформа использует десять core agents плюс Methodologist gate и Evolution Analyst meta-agent, каждый со строгой ролью. Director AI над циклом. Агенты общаются через filesystem — агент не может менять работу другого. Для web deliverables Architect также создаёт ui_experience (tokens, typography, motion), Developer выпускает осмысленный UI — отдельный ",
            "La plataforma usa diez core agents más Methodologist gate y Evolution Analyst meta-agent, cada uno con rol estricto. Director AI está sobre el bucle. Los agentes se comunican vía filesystem — ningún agente modifica el trabajo de otro. Para web deliverables, Architect también emite ui_experience (tokens, typography, motion) para que Developer entregue UI intencional — un ",
        ),
        "introDesigner": _t(locale, "Designer", "Designer", "Designer"),
        "introSuffix": _t(
            locale,
            " step on the public pipeline diagram.",
            " шаг на публичной диаграмме pipeline.",
            " paso en el diagrama público del pipeline.",
        ),
        "cards": [{"name": c[0], "role": _t(locale, c[1], c[2], c[3])} for c in cards],
        "safety": _t(locale, "Agent Safety", "Безопасность агентов", "Seguridad de agentes"),
        "safetyItems": [
            _t(locale, "Strict role boundaries — no agent can perform another agent's tasks", "Строгие границы ролей — агент не выполняет задачи другого", "Límites estrictos de rol — ningún agente realiza tareas de otro"),
            _t(locale, "Timeout protection — agents have 30-second execution limit (configurable)", "Timeout protection — лимит выполнения 30 секунд (настраивается)", "Timeout protection — límite de ejecución 30 segundos (configurable)"),
            _t(locale, "Output validation — all agent outputs are validated against schemas", "Output validation — все выходы проверяются по schemas", "Output validation — todas las salidas se validan contra schemas"),
            _t(locale, "Escalation — if an agent fails repeatedly, the Director AI is notified", "Escalation — при повторных сбоях уведомляется Director AI", "Escalation — si un agente falla repetidamente, se notifica Director AI"),
            _t(locale, "Filesystem-based memory — no context hallucination, all state is on disk", "Filesystem-based memory — без context hallucination, состояние на диске", "Filesystem-based memory — sin context hallucination, todo el estado en disco"),
        ],
    }


def _pipeline(locale: str) -> dict[str, Any]:
    return {
        "titleGradient": _t(locale, "Flow", "конвейер", "pipeline"),
        "intro": _t(
            locale,
            "The product lifecycle follows a deterministic state machine with 13 states. Each state is handled by a specific agent, ensuring clear ownership and accountability.",
            "Жизненный цикл продукта следует детерминированному state machine из 13 состояний. Каждое состояние обрабатывает конкретный агент — чёткая ответственность.",
            "El ciclo de vida sigue una máquina de estados determinista con 13 estados. Cada estado lo maneja un agente específico — responsabilidad clara.",
        ),
        "introOnDemand": _t(
            locale,
            "Autonomous products still consume analyst/marketing idea flows; on-demand products anchor every downstream agent on the customer brief — not a separate lightweight conveyor for orders.",
            "Автономные продукты всё ещё используют analyst/marketing idea flows; on-demand продукты привязывают все downstream-агенты к brief заказчика — not a separate lightweight conveyor for orders.",
            "Los productos autónomos siguen consumiendo flujos analyst/marketing; los on-demand anclan cada agente downstream al brief del cliente — not a separate lightweight conveyor for orders.",
        ),
        "standardPipeline": _t(locale, "Standard Pipeline", "Стандартный pipeline", "Pipeline estándar"),
        "featuresTitle": _t(locale, "Pipeline Features", "Возможности pipeline", "Características del pipeline"),
        "featuresItems": [
            _t(locale, "Deterministic FSM — each product follows the same state machine", "Детерминированный FSM — каждый продукт следует той же state machine", "FSM determinista — cada producto sigue la misma máquina de estados"),
            _t(locale, "Error recovery — if QA finds bugs, product loops back to DEV_FIXING", "Восстановление после ошибок — если QA находит баги, продукт возвращается в DEV_FIXING", "Recuperación de errores — si QA encuentra bugs, el producto vuelve a DEV_FIXING"),
            _t(locale, "Timeout management — each step has a configurable timeout (default 30s)", "Управление таймаутами — каждый шаг с настраиваемым timeout (по умолчанию 30s)", "Gestión de timeouts — cada paso con timeout configurable (default 30s)"),
            _t(locale, "Parallel execution — multiple products can be in different pipeline stages", "Параллельное выполнение — несколько продуктов на разных этапах pipeline", "Ejecución paralela — varios productos en distintas etapas del pipeline"),
            _t(locale, "State persistence — JSON (default) or optional SQLite3 backend with CLI migration", "Сохранение состояния — JSON (по умолчанию) или опциональный SQLite3 backend с CLI migration", "Persistencia de estado — JSON (default) o backend SQLite3 opcional con migración CLI"),
            _t(locale, "Director override — Director AI can adjust timeouts and priorities", "Director override — Director AI может менять timeouts и приоритеты", "Director override — Director AI puede ajustar timeouts y prioridades"),
        ],
        "directorCycleTitle": _t(locale, "Director AI Cycle (Every 4 Hours)", "Цикл Director AI (каждые 4 часа)", "Ciclo Director AI (cada 4 horas)"),
        "directorCycleIntro": _t(
            locale,
            "In parallel with the product pipeline, the Director AI runs every 4 hours:",
            "Параллельно product pipeline Director AI запускается каждые 4 часа:",
            "En paralelo al product pipeline, Director AI corre cada 4 horas:",
        ),
        "directorCycleItems": [
            _t(locale, "1. Collect metrics from all sources (state files, telemetry, logs, database)", "1. Сбор метрик из всех источников (state files, telemetry, logs, database)", "1. Recolectar métricas de todas las fuentes (state files, telemetry, logs, database)"),
            _t(locale, "2. Analyze metrics against target values, identify anomalies and trends", "2. Анализ метрик относительно целей, аномалии и тренды", "2. Analizar métricas vs objetivos, identificar anomalías y tendencias"),
            _t(locale, "3. Generate decisions — auto-apply allowed actions, queue recommendations for admin", "3. Генерация решений — auto-apply разрешённых действий, рекомендации в очередь admin", "3. Generar decisiones — auto-apply acciones permitidas, encolar recomendaciones para admin"),
            _t(locale, "4. Generate markdown report saved to /data/reports/director/", "4. Markdown-отчёт в /data/reports/director/", "4. Informe markdown guardado en /data/reports/director/"),
            _t(locale, "5. Notify admin panel with ready report", "5. Уведомление admin panel о готовом отчёте", "5. Notificar panel admin con informe listo"),
        ],
        "pipelineStates": PIPELINE_STATES,
    }


def _crypto(locale: str) -> dict[str, Any]:
    return {
        "titleGradient": _t(locale, "Payments", "платежи", "pagos"),
        "intro": _t(
            locale,
            "AI-Factory supports multi-chain crypto payments for generated products. Customers can purchase products using USDT or USDC stablecoins.",
            "AI-Factory поддерживает мультичейн криптоплатежи за сгенерированные продукты. Покупатели могут платить USDT или USDC.",
            "AI-Factory admite pagos cripto multichain por productos generados. Los clientes pueden comprar con stablecoins USDT o USDC.",
        ),
        "economicsTitle": _t(locale, "Economics", "Экономика", "Economía"),
        "economicsBody": _t(
            locale,
            "Storefront and checkout default to about $4.99 USDT when marketing/sales files do not specify another price — tuned for impulse landing purchases while operators override per SKU.",
            "Витрина и checkout по умолчанию ~$4.99 USDT, если marketing/sales не задают другую цену — для импульсных покупок лендингов, операторы переопределяют per SKU.",
            "Tienda y checkout por defecto ~$4.99 USDT si marketing/sales no especifican otro precio — para compras impulsivas de landings; operadores override por SKU.",
        ),
        "supportedNetworks": _t(locale, "Supported Networks", "Поддерживаемые сети", "Redes soportadas"),
        "paymentFlowTitle": _t(locale, "Payment Flow", "Поток оплаты", "Flujo de pago"),
        "paymentFlowItems": [
            _t(locale, "Customer selects product and chooses a network (Base/Solana/Arbitrum)", "Покупатель выбирает продукт и сеть (Base/Solana/Arbitrum)", "El cliente elige producto y red (Base/Solana/Arbitrum)"),
            _t(locale, "System generates a unique payment address and amount", "Система генерирует уникальный адрес и сумму", "El sistema genera dirección y monto únicos"),
            _t(locale, "Customer sends USDT/USDC to the provided address", "Покупатель отправляет USDT/USDC на указанный адрес", "El cliente envía USDT/USDC a la dirección indicada"),
            _t(locale, "System monitors blockchain confirmations (polling every 15s)", "Система отслеживает подтверждения блокчейна (опрос каждые 15s)", "El sistema monitorea confirmaciones blockchain (polling cada 15s)"),
            _t(locale, "On sufficient confirmations — product license is activated", "При достаточных подтверждениях — активируется лицензия продукта", "Con confirmaciones suficientes — se activa la licencia del producto"),
            _t(locale, "Customer gains access to sandbox demo and full product", "Покупатель получает доступ к sandbox demo и полному продукту", "El cliente accede al demo sandbox y producto completo"),
        ],
        "walletTitle": _t(locale, "Wallet Management", "Управление кошельками", "Gestión de wallets"),
        "walletBody": _t(
            locale,
            "Platform wallets are configured via the CLI. Wallet addresses are displayed in the admin panel under Crypto Settings. Withdrawals require multi-signature approval.",
            "Кошельки платформы настраиваются через CLI. Адреса отображаются в admin panel в Crypto Settings. Вывод требует multi-signature approval.",
            "Los wallets de plataforma se configuran vía CLI. Las direcciones se muestran en admin panel bajo Crypto Settings. Retiros requieren multi-signature approval.",
        ),
        "chains": CRYPTO_CHAINS,
    }


def _security(locale: str) -> dict[str, Any]:
    return {
        "titleGradient": _t(locale, "Security", "безопасность", "seguridad"),
        "intro": _t(
            locale,
            "AI-Factory implements enterprise-grade security measures across all layers.",
            "AI-Factory реализует меры безопасности enterprise-уровня на всех слоях.",
            "AI-Factory implementa medidas de seguridad enterprise en todas las capas.",
        ),
        "authTitle": _t(locale, "Authentication & Authorization", "Аутентификация и авторизация", "Autenticación y autorización"),
        "authItems": [
            _t(locale, "JWT-based authentication with HTTP-only cookies", "JWT-аутентификация с HTTP-only cookies", "Autenticación JWT con cookies HTTP-only"),
            _t(locale, "Password hashing with SHA-256 + salt (fallback)", "Хеширование паролей SHA-256 + salt (fallback)", "Hash de contraseñas SHA-256 + salt (fallback)"),
            _t(locale, "2FA support via Google Authenticator (TOTP)", "2FA через Google Authenticator (TOTP)", "2FA vía Google Authenticator (TOTP)"),
            _t(locale, "Brute-force protection: 5 failed attempts max per 15 minutes", "Защита brute-force: макс. 5 неудачных попыток за 15 минут", "Protección brute-force: máx. 5 intentos fallidos por 15 minutos"),
            _t(locale, "30-minute session inactivity timeout", "Таймаут сессии 30 минут неактивности", "Timeout de sesión 30 minutos de inactividad"),
            _t(locale, "All admin actions logged to tamper-evident audit log", "Все действия admin в tamper-evident audit log", "Todas las acciones admin en audit log a prueba de manipulación"),
        ],
        "sandboxTitle": _t(locale, "Sandbox Isolation", "Изоляция sandbox", "Aislamiento de sandbox"),
        "sandboxItems": [
            _t(locale, "Docker-in-Docker for product sandboxes", "Docker-in-Docker для product sandboxes", "Docker-in-Docker para product sandboxes"),
            _t(locale, "No network access from sandboxes (default)", "Нет сетевого доступа из sandboxes (по умолчанию)", "Sin acceso de red desde sandboxes (default)"),
            _t(locale, "Resource limits (CPU/memory) per sandbox", "Лимиты ресурсов (CPU/memory) на sandbox", "Límites de recursos (CPU/memory) por sandbox"),
            _t(locale, "Filesystem isolation — no access to host files", "Изоляция filesystem — нет доступа к файлам хоста", "Aislamiento filesystem — sin acceso a archivos del host"),
            _t(locale, "Automatic sandbox cleanup on timeout", "Автоочистка sandbox по timeout", "Limpieza automática de sandbox al timeout"),
        ],
        "dataProtectionTitle": _t(locale, "Data Protection", "Защита данных", "Protección de datos"),
        "dataProtectionItems": [
            _t(locale, "Secrets encrypted at rest using Fernet (symmetric encryption)", "Секреты шифруются at rest через Fernet (symmetric encryption)", "Secretos cifrados at rest con Fernet (symmetric encryption)"),
            _t(locale, "Audit logs are append-only with tamper detection", "Audit logs append-only с обнаружением подмены", "Audit logs append-only con detección de manipulación"),
            _t(locale, "Rate limiting on all API endpoints", "Rate limiting на всех API endpoints", "Rate limiting en todos los API endpoints"),
            _t(locale, "No sensitive data returned in API responses", "Чувствительные данные не возвращаются в API responses", "Sin datos sensibles en API responses"),
            _t(locale, "Firewall rules within container (nftables)", "Правила firewall в контейнере (nftables)", "Reglas firewall dentro del contenedor (nftables)"),
        ],
        "monitoringTitle": _t(locale, "Security Monitoring", "Мониторинг безопасности", "Monitoreo de seguridad"),
        "monitoringItems": [
            _t(locale, "Real-time security dashboard in admin panel", "Dashboard безопасности в реальном времени в admin panel", "Dashboard de seguridad en tiempo real en admin panel"),
            _t(locale, "Failed login attempt tracking with IP logging", "Отслеживание неудачных входов с IP logging", "Seguimiento de logins fallidos con IP logging"),
            _t(locale, "Audit log export in JSON format", "Экспорт audit log в JSON", "Exportación de audit log en JSON"),
            _t(locale, "Automatic alerts on suspicious activity", "Автооповещения о подозрительной активности", "Alertas automáticas por actividad sospechosa"),
        ],
        "firstPasswordTitle": _t(locale, "First admin password", "Первый пароль admin", "Primera contraseña admin"),
        "firstPasswordBodyPrefix": _t(
            locale,
            "No fixed default password. Use the console prompt on first TTY start, read ",
            "Нет фиксированного пароля по умолчанию. Используйте консольный prompt при первом TTY start, читайте ",
            "Sin contraseña fija por defecto. Use el prompt de consola en el primer TTY start, lea ",
        ),
        "firstPasswordPath": "data/secrets/bootstrap_admin.txt",
        "firstPasswordBodySuffix": _t(
            locale,
            " for detached Compose, or rotate via Admin → Users. CSRF protection applies to cookie-based admin sessions (X-CSRF-Token header).",
            " для detached Compose или смените через Admin → Users. CSRF protection для cookie-based admin sessions (заголовок X-CSRF-Token).",
            " para Compose detached, o rote vía Admin → Users. CSRF protection aplica a sesiones admin cookie-based (header X-CSRF-Token).",
        ),
    }


def _director(locale: str) -> dict[str, Any]:
    metric_cards = [
        {
            "title": _t(locale, "Pipeline Efficiency", "Эффективность pipeline", "Eficiencia del pipeline"),
            "items": [
                _t(locale, "Idea → MVP time (target: <4h)", "Idea → MVP time (цель: <4h)", "Idea → MVP time (objetivo: <4h)"),
                _t(locale, "Auto-completion rate (target: >95%)", "Auto-completion rate (цель: >95%)", "Auto-completion rate (objetivo: >95%)"),
                _t(locale, "Agent timeout/error rates", "Agent timeout/error rates", "Agent timeout/error rates"),
                _t(locale, "Auto-fix success rate (target: >85%)", "Auto-fix success rate (цель: >85%)", "Auto-fix success rate (objetivo: >85%)"),
            ],
        },
        {
            "title": _t(locale, "Business Metrics", "Бизнес-метрики", "Métricas de negocio"),
            "items": [
                _t(locale, "Sandbox → purchase conversion (target: >12%)", "Sandbox → purchase conversion (цель: >12%)", "Sandbox → purchase conversion (objetivo: >12%)"),
                _t(locale, "Average order value in crypto", "Средний чек в крипто", "Valor medio de pedido en cripto"),
                _t(locale, "Top/bottom products by revenue", "Top/bottom products by revenue", "Top/bottom products by revenue"),
                _t(locale, "Marketing content effectiveness", "Эффективность marketing content", "Efectividad del marketing content"),
            ],
        },
        {
            "title": _t(locale, "Technical Health", "Техническое здоровье", "Salud técnica"),
            "items": [
                _t(locale, "CPU/RAM/disk usage alerts", "Алерты CPU/RAM/disk usage", "Alertas CPU/RAM/disk usage"),
                _t(locale, "LLM provider availability", "Доступность LLM provider", "Disponibilidad LLM provider"),
                _t(locale, "Security incident count", "Количество security incident", "Recuento de security incident"),
                _t(locale, "Model inference latency (P95)", "Model inference latency (P95)", "Model inference latency (P95)"),
            ],
        },
        {
            "title": _t(locale, "Product Quality", "Качество продукта", "Calidad del producto"),
            "items": [
                _t(locale, "Average product rating (from reviews)", "Средний рейтинг продукта (из reviews)", "Rating medio del producto (de reviews)"),
                _t(locale, "Bugs per 1000 lines of code", "Bugs на 1000 строк кода", "Bugs por 1000 líneas de código"),
                _t(locale, "Critical bug response time (P0)", "Critical bug response time (P0)", "Critical bug response time (P0)"),
                _t(locale, "Evolution improvements applied", "Применённые evolution improvements", "Evolution improvements aplicadas"),
            ],
        },
    ]
    return {
        "titleGradient": _t(locale, "AI", "AI", "AI"),
        "intro": _t(
            locale,
            "The Director AI is a meta-agent that oversees the entire platform. It does not participate in product development but evaluates system performance and makes optimization decisions.",
            "Director AI — мета-агент, надзирающий за всей платформой. Не участвует в разработке продуктов, но оценивает производительность системы и принимает решения по оптимизации.",
            "Director AI es un metaagente que supervisa toda la plataforma. No participa en el desarrollo de productos pero evalúa el rendimiento del sistema y toma decisiones de optimización.",
        ),
        "analysisCycleTitle": _t(locale, "Analysis Cycle (Every 4 Hours)", "Цикл анализа (каждые 4 часа)", "Ciclo de análisis (cada 4 horas)"),
        "cycleItems": [
            _t(locale, "1. Metrics Collection — gathers data from pipeline state, telemetry, logs, and financial records", "1. Metrics Collection — данные из pipeline state, telemetry, logs и financial records", "1. Metrics Collection — datos de pipeline state, telemetry, logs y financial records"),
            _t(locale, "2. Analysis — compares metrics against targets, identifies anomalies and trends", "2. Analysis — сравнение метрик с целями, аномалии и тренды", "2. Analysis — compara métricas vs objetivos, anomalías y tendencias"),
            _t(locale, "3. Decision Making — generates automatic actions (if enabled) and recommendations", "3. Decision Making — автоматические действия (если включены) и рекомендации", "3. Decision Making — acciones automáticas (si habilitadas) y recomendaciones"),
            _t(locale, "4. Report Generation — creates detailed markdown report", "4. Report Generation — подробный markdown-отчёт", "4. Report Generation — informe markdown detallado"),
            _t(locale, "5. Notification — updates admin panel with new report", "5. Notification — обновление admin panel новым отчётом", "5. Notification — actualiza admin panel con nuevo informe"),
        ],
        "metricsTitle": _t(locale, "Metrics Tracked", "Отслеживаемые метрики", "Métricas rastreadas"),
        "metricCards": metric_cards,
        "autoActionsTitle": _t(locale, "Automatic Actions", "Автоматические действия", "Acciones automáticas"),
        "autoActionsIntro": _t(locale, "When enabled, the Director AI can automatically:", "Если включено, Director AI может автоматически:", "Cuando está habilitado, Director AI puede automáticamente:"),
        "autoActionsItems": [
            _t(locale, "Increase agent timeouts if timeout rate exceeds 15%", "Увеличить agent timeouts, если timeout rate >15%", "Aumentar agent timeouts si timeout rate supera 15%"),
            _t(locale, "Trigger marketing reviews if conversion drops below 8%", "Запустить marketing reviews, если conversion <8%", "Disparar marketing reviews si conversion cae bajo 8%"),
            _t(locale, "Recommend switching to local models if GPU is underutilized", "Рекомендовать local models при недогрузке GPU", "Recomendar local models si GPU está subutilizada"),
            _t(locale, "Adjust resource limits based on usage patterns", "Корректировать resource limits по паттернам использования", "Ajustar resource limits según patrones de uso"),
        ],
        "reportFormatTitle": _t(locale, "Report Format", "Формат отчёта", "Formato del informe"),
        "reportFormatIntro": _t(
            locale,
            "Director reports are saved as Markdown files in /data/reports/director/ and displayed in the admin panel. Each report includes:",
            "Отчёты Director сохраняются как Markdown в /data/reports/director/ и отображаются в admin panel. Каждый отчёт включает:",
            "Los informes Director se guardan como Markdown en /data/reports/director/ y se muestran en admin panel. Cada informe incluye:",
        ),
        "reportFormatItems": [
            _t(locale, "Key metrics comparison (actual vs target)", "Сравнение ключевых метрик (actual vs target)", "Comparación de métricas clave (actual vs target)"),
            _t(locale, "Automatic actions applied", "Применённые автоматические действия", "Acciones automáticas aplicadas"),
            _t(locale, "Recommendations requiring admin approval", "Рекомендации, требующие одобрения admin", "Recomendaciones que requieren aprobación admin"),
            _t(locale, "24-hour forecast with risk assessment", "Прогноз на 24 часа с оценкой рисков", "Pronóstico 24 horas con evaluación de riesgos"),
        ],
    }


def _configuration(locale: str) -> dict[str, Any]:
    return {
        "titleGradient": _t(locale, "Configuration", "конфигурация", "configuración"),
        "intro": _t(
            locale,
            "The platform is configured through YAML and JSON files in /data/config/. Changes can be made via the admin panel or directly by editing these files.",
            "Платформа настраивается через YAML и JSON в /data/config/. Изменения через admin panel или прямое редактирование файлов.",
            "La plataforma se configura con YAML y JSON en /data/config/. Cambios vía admin panel o editando estos archivos.",
        ),
        "modelProvidersTitle": "Model Providers (model_providers.yaml)",
        "routingRulesTitle": _t(locale, "Routing Rules", "Правила маршрутизации", "Reglas de enrutamiento"),
        "globalConfigTitle": "Global Config (config.yaml)",
        "themesTitle": _t(locale, "Themes", "Темы", "Temas"),
        "themesIntro": _t(locale, "Five pre-installed themes are available:", "Доступны пять предустановленных тем:", "Hay cinco temas preinstalados:"),
        "themeItems": [
            _t(locale, "Cyberpunk — neon cyan, purple accents, dark gradient background", "Cyberpunk — neon cyan, фиолетовые акценты, тёмный gradient background", "Cyberpunk — neon cyan, acentos púrpura, fondo gradient oscuro"),
            _t(locale, "Minimal — clean white/gray with subtle shadows", "Minimal — чистый white/gray с лёгкими тенями", "Minimal — white/gray limpio con sombras sutiles"),
            _t(locale, "Glass — transparent panels with heavy blur effects", "Glass — прозрачные панели с сильным blur", "Glass — paneles transparentes con blur intenso"),
            _t(locale, "Neon — bright neon colors on dark background", "Neon — яркие neon colors на тёмном фоне", "Neon — colores neon brillantes sobre fondo oscuro"),
            _t(locale, "Corporate — professional blue/white color scheme", "Corporate — профессиональная blue/white схема", "Corporate — esquema blue/white profesional"),
        ],
    }


def build_pack(locale: str) -> dict[str, Any]:
    pack = {
        "locale": locale,
        "localeNames": LOCALE_NAMES,
        "localeLabels": LOCALE_LABELS,
        "nav": _nav(locale),
        "hero": _hero(locale),
        "footer": _footer(locale),
        "ui": _ui(locale),
        "sectionTitles": _section_titles(locale),
        "overview": _overview(locale),
        "userGuide": _user_guide(locale),
        "ownerGuide": _owner_guide(locale),
        "architecture": _architecture(locale),
        "quickstart": _quickstart(locale),
        "adminPanel": _admin_panel(locale),
        "apiReference": _api_reference(locale),
        "cli": _cli(locale),
        "agents": _agents(locale),
        "pipeline": _pipeline(locale),
        "crypto": _crypto(locale),
        "security": _security(locale),
        "director": _director(locale),
        "configuration": _configuration(locale),
    }
    assert list(pack.keys()) == TOP_LEVEL_KEYS
    return pack


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for locale in ("en", "ru", "es"):
        path = OUT_DIR / f"{locale}.json"
        data = build_pack(locale)
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        print(f"{path}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
