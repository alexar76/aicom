"""Documentation page chrome strings for all 20 SKOPOS doc locales."""

from __future__ import annotations

from typing import Any

UI_STRINGS: dict[str, dict[str, Any]] = {
    "en": {
        "title": "Documentation",
        "subtitle": "Deployment, configuration, usage, and HTTP logs (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Primary source: nginx access logs.** **Apache combined** is also supported "
            "(`apache.enabled: true` in servers.yaml). Caddy, Traefik, and raw app logs are not. "
            "Metis test stack: Apache :8088 and `/admin/` — see the **HTTP logs** tab."
        ),
        "doc_language": "Guide language",
        "image_missing": "Screenshot not found: {path}",
        "sections": {
            "overview": "Overview",
            "deployment": "Deployment",
            "configuration": "Configuration",
            "usage": "Usage",
            "nginx": "HTTP logs",
        },
    },
    "zh": {
        "title": "文档",
        "subtitle": "部署、配置、使用及 HTTP 日志（nginx + Apache）",
        "nginx_disclaimer": (
            "ℹ️ **主要数据源：nginx access 日志。** 也支持 **Apache combined**"
            "（在 servers.yaml 中设置 `apache.enabled: true`）。"
            "不支持 Caddy、Traefik 及原始应用日志。"
            "Metis 测试环境：Apache :8088 和 `/admin/` — 请参阅 **HTTP 日志** 选项卡。"
        ),
        "doc_language": "指南语言",
        "image_missing": "未找到截图：{path}",
        "sections": {
            "overview": "概览",
            "deployment": "部署",
            "configuration": "配置",
            "usage": "使用",
            "nginx": "HTTP 日志",
        },
    },
    "es": {
        "title": "Documentación",
        "subtitle": "Despliegue, configuración, uso y logs HTTP (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Fuente principal: logs de acceso nginx.** **Apache combined** también está soportado "
            "(`apache.enabled: true` en servers.yaml). Caddy, Traefik y logs de app — no. "
            "Prueba en metis: Apache :8088 y `/admin/` — pestaña «Logs HTTP»."
        ),
        "doc_language": "Idioma de la guía",
        "image_missing": "Captura no encontrada: {path}",
        "sections": {
            "overview": "Resumen",
            "deployment": "Despliegue",
            "configuration": "Configuración",
            "usage": "Uso",
            "nginx": "Logs HTTP",
        },
    },
    "hi": {
        "title": "दस्तावेज़ीकरण",
        "subtitle": "तैनाती, कॉन्फ़िगरेशन, उपयोग और HTTP लॉग (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **प्राथमिक स्रोत: nginx access logs.** **Apache combined** भी समर्थित है "
            "(`apache.enabled: true` servers.yaml में)। Caddy, Traefik और raw app logs — नहीं। "
            "Metis टेस्ट स्टैक: Apache :8088 और `/admin/` — **HTTP logs** टैब देखें।"
        ),
        "doc_language": "गाइड की भाषा",
        "image_missing": "स्क्रीनशॉट नहीं मिला: {path}",
        "sections": {
            "overview": "अवलोकन",
            "deployment": "तैनाती",
            "configuration": "कॉन्फ़िगरेशन",
            "usage": "उपयोग",
            "nginx": "HTTP logs",
        },
    },
    "ar": {
        "title": "التوثيق",
        "subtitle": "النشر والإعداد والاستخدام وسجلات HTTP (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **المصدر الأساسي: سجلات وصول nginx.** **Apache combined** مدعوم أيضًا "
            "(`apache.enabled: true` في servers.yaml). Caddy وTraefik وسجلات التطبيقات الخام — لا. "
            "مجموعة اختبار Metis: Apache :8088 و`/admin/` — راجع تبويب **سجلات HTTP**."
        ),
        "doc_language": "لغة الدليل",
        "image_missing": "لم يتم العثور على لقطة الشاشة: {path}",
        "sections": {
            "overview": "نظرة عامة",
            "deployment": "النشر",
            "configuration": "الإعداد",
            "usage": "الاستخدام",
            "nginx": "سجلات HTTP",
        },
    },
    "pt": {
        "title": "Documentação",
        "subtitle": "Implantação, configuração, uso e logs HTTP (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Fonte principal: logs de acesso nginx.** **Apache combined** também é suportado "
            "(`apache.enabled: true` em servers.yaml). Caddy, Traefik e logs brutos de app — não. "
            "Stack de teste Metis: Apache :8088 e `/admin/` — veja a aba **Logs HTTP**."
        ),
        "doc_language": "Idioma do guia",
        "image_missing": "Captura de tela não encontrada: {path}",
        "sections": {
            "overview": "Visão geral",
            "deployment": "Implantação",
            "configuration": "Configuração",
            "usage": "Uso",
            "nginx": "Logs HTTP",
        },
    },
    "ru": {
        "title": "Документация",
        "subtitle": "Развёртывание, настройка, использование и HTTP-логи (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Основной источник — access-логи nginx.** **Apache combined** тоже поддерживается "
            "(`apache.enabled: true` в servers.yaml). Caddy, Traefik и произвольные app-логи — нет. "
            "Тест на metis: Apache :8088 и `/admin/` — см. вкладку «HTTP-логи»."
        ),
        "doc_language": "Язык руководства",
        "image_missing": "Скриншот не найден: {path}",
        "sections": {
            "overview": "Обзор",
            "deployment": "Развёртывание",
            "configuration": "Настройка",
            "usage": "Использование",
            "nginx": "HTTP-логи",
        },
    },
    "ja": {
        "title": "ドキュメント",
        "subtitle": "デプロイ、設定、使用方法、HTTP ログ（nginx + Apache）",
        "nginx_disclaimer": (
            "ℹ️ **主なソース：nginx access ログ。** **Apache combined** もサポートしています "
            "（servers.yaml で `apache.enabled: true`）。Caddy、Traefik、生のアプリログには非対応です。"
            "Metis テスト環境：Apache :8088 と `/admin/` — **HTTP ログ** タブを参照してください。"
        ),
        "doc_language": "ガイドの言語",
        "image_missing": "スクリーンショットが見つかりません：{path}",
        "sections": {
            "overview": "概要",
            "deployment": "デプロイ",
            "configuration": "設定",
            "usage": "使用方法",
            "nginx": "HTTP ログ",
        },
    },
    "fr": {
        "title": "Documentation",
        "subtitle": "Déploiement, configuration, utilisation et journaux HTTP (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Source principale : journaux d'accès nginx.** **Apache combined** est également pris en charge "
            "(`apache.enabled: true` dans servers.yaml). Caddy, Traefik et les journaux bruts d'application — non. "
            "Stack de test Metis : Apache :8088 et `/admin/` — voir l'onglet **Journaux HTTP**."
        ),
        "doc_language": "Langue du guide",
        "image_missing": "Capture d'écran introuvable : {path}",
        "sections": {
            "overview": "Vue d'ensemble",
            "deployment": "Déploiement",
            "configuration": "Configuration",
            "usage": "Utilisation",
            "nginx": "Journaux HTTP",
        },
    },
    "de": {
        "title": "Dokumentation",
        "subtitle": "Bereitstellung, Konfiguration, Nutzung und HTTP-Logs (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Primärquelle: nginx Access-Logs.** **Apache combined** wird ebenfalls unterstützt "
            "(`apache.enabled: true` in servers.yaml). Caddy, Traefik und rohe App-Logs — nicht. "
            "Metis-Teststack: Apache :8088 und `/admin/` — siehe Tab **HTTP-Logs**."
        ),
        "doc_language": "Sprache des Leitfadens",
        "image_missing": "Screenshot nicht gefunden: {path}",
        "sections": {
            "overview": "Übersicht",
            "deployment": "Bereitstellung",
            "configuration": "Konfiguration",
            "usage": "Nutzung",
            "nginx": "HTTP-Logs",
        },
    },
    "ko": {
        "title": "문서",
        "subtitle": "배포, 구성, 사용법 및 HTTP 로그 (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **주요 소스: nginx access 로그.** **Apache combined**도 지원됩니다 "
            "(`apache.enabled: true` in servers.yaml). Caddy, Traefik 및 원시 앱 로그는 지원하지 않습니다. "
            "Metis 테스트 스택: Apache :8088 및 `/admin/` — **HTTP 로그** 탭을 참조하세요."
        ),
        "doc_language": "가이드 언어",
        "image_missing": "스크린샷을 찾을 수 없습니다: {path}",
        "sections": {
            "overview": "개요",
            "deployment": "배포",
            "configuration": "구성",
            "usage": "사용법",
            "nginx": "HTTP 로그",
        },
    },
    "it": {
        "title": "Documentazione",
        "subtitle": "Distribuzione, configurazione, utilizzo e log HTTP (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Fonte principale: access log nginx.** È supportato anche **Apache combined** "
            "(`apache.enabled: true` in servers.yaml). Caddy, Traefik e log grezzi dell'app — no. "
            "Stack di test Metis: Apache :8088 e `/admin/` — vedi la scheda **Log HTTP**."
        ),
        "doc_language": "Lingua della guida",
        "image_missing": "Screenshot non trovato: {path}",
        "sections": {
            "overview": "Panoramica",
            "deployment": "Distribuzione",
            "configuration": "Configurazione",
            "usage": "Utilizzo",
            "nginx": "Log HTTP",
        },
    },
    "tr": {
        "title": "Dokümantasyon",
        "subtitle": "Dağıtım, yapılandırma, kullanım ve HTTP günlükleri (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Birincil kaynak: nginx access log'ları.** **Apache combined** de desteklenir "
            "(`apache.enabled: true` in servers.yaml). Caddy, Traefik ve ham uygulama log'ları — hayır. "
            "Metis test yığını: Apache :8088 ve `/admin/` — **HTTP günlükleri** sekmesine bakın."
        ),
        "doc_language": "Kılavuz dili",
        "image_missing": "Ekran görüntüsü bulunamadı: {path}",
        "sections": {
            "overview": "Genel bakış",
            "deployment": "Dağıtım",
            "configuration": "Yapılandırma",
            "usage": "Kullanım",
            "nginx": "HTTP günlükleri",
        },
    },
    "id": {
        "title": "Dokumentasi",
        "subtitle": "Penyebaran, konfigurasi, penggunaan, dan log HTTP (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Sumber utama: access log nginx.** **Apache combined** juga didukung "
            "(`apache.enabled: true` di servers.yaml). Caddy, Traefik, dan log aplikasi mentah — tidak. "
            "Stack uji Metis: Apache :8088 dan `/admin/` — lihat tab **Log HTTP**."
        ),
        "doc_language": "Bahasa panduan",
        "image_missing": "Tangkapan layar tidak ditemukan: {path}",
        "sections": {
            "overview": "Ikhtisar",
            "deployment": "Penyebaran",
            "configuration": "Konfigurasi",
            "usage": "Penggunaan",
            "nginx": "Log HTTP",
        },
    },
    "vi": {
        "title": "Tài liệu",
        "subtitle": "Triển khai, cấu hình, sử dụng và nhật ký HTTP (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Nguồn chính: access log nginx.** **Apache combined** cũng được hỗ trợ "
            "(`apache.enabled: true` trong servers.yaml). Caddy, Traefik và log ứng dụng thô — không. "
            "Stack thử nghiệm Metis: Apache :8088 và `/admin/` — xem tab **Nhật ký HTTP**."
        ),
        "doc_language": "Ngôn ngữ hướng dẫn",
        "image_missing": "Không tìm thấy ảnh chụp màn hình: {path}",
        "sections": {
            "overview": "Tổng quan",
            "deployment": "Triển khai",
            "configuration": "Cấu hình",
            "usage": "Sử dụng",
            "nginx": "Nhật ký HTTP",
        },
    },
    "th": {
        "title": "เอกสาร",
        "subtitle": "การปรับใช้ การตั้งค่า การใช้งาน และ HTTP log (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **แหล่งข้อมูลหลัก: nginx access log** รองรับ **Apache combined** ด้วย "
            "(`apache.enabled: true` ใน servers.yaml) ไม่รองรับ Caddy, Traefik และ app log ดิบ "
            "Stack ทดสอบ Metis: Apache :8088 และ `/admin/` — ดูแท็บ **HTTP log**"
        ),
        "doc_language": "ภาษาคู่มือ",
        "image_missing": "ไม่พบภาพหน้าจอ: {path}",
        "sections": {
            "overview": "ภาพรวม",
            "deployment": "การปรับใช้",
            "configuration": "การตั้งค่า",
            "usage": "การใช้งาน",
            "nginx": "HTTP log",
        },
    },
    "hr": {
        "title": "Dokumentacija",
        "subtitle": "Implementacija, konfiguracija, korištenje i HTTP logovi (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Primarni izvor: nginx access logovi.** **Apache combined** također je podržan "
            "(`apache.enabled: true` u servers.yaml). Caddy, Traefik i sirovi app logovi — ne. "
            "Metis test stack: Apache :8088 i `/admin/` — pogledajte karticu **HTTP logovi**."
        ),
        "doc_language": "Jezik vodiča",
        "image_missing": "Snimka zaslona nije pronađena: {path}",
        "sections": {
            "overview": "Pregled",
            "deployment": "Implementacija",
            "configuration": "Konfiguracija",
            "usage": "Korištenje",
            "nginx": "HTTP logovi",
        },
    },
    "sk": {
        "title": "Dokumentácia",
        "subtitle": "Nasadenie, konfigurácia, používanie a HTTP logy (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Primárny zdroj: nginx access logy.** **Apache combined** je tiež podporovaný "
            "(`apache.enabled: true` v servers.yaml). Caddy, Traefik a surové app logy — nie. "
            "Metis test stack: Apache :8088 a `/admin/` — pozrite kartu **HTTP logy**."
        ),
        "doc_language": "Jazyk príručky",
        "image_missing": "Snímka obrazovky sa nenašla: {path}",
        "sections": {
            "overview": "Prehľad",
            "deployment": "Nasadenie",
            "configuration": "Konfigurácia",
            "usage": "Používanie",
            "nginx": "HTTP logy",
        },
    },
    "nl": {
        "title": "Documentatie",
        "subtitle": "Implementatie, configuratie, gebruik en HTTP-logs (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **Primaire bron: nginx access logs.** **Apache combined** wordt ook ondersteund "
            "(`apache.enabled: true` in servers.yaml). Caddy, Traefik en ruwe app-logs — niet. "
            "Metis-teststack: Apache :8088 en `/admin/` — zie het tabblad **HTTP-logs**."
        ),
        "doc_language": "Taal van de gids",
        "image_missing": "Schermafbeelding niet gevonden: {path}",
        "sections": {
            "overview": "Overzicht",
            "deployment": "Implementatie",
            "configuration": "Configuratie",
            "usage": "Gebruik",
            "nginx": "HTTP-logs",
        },
    },
    "fa": {
        "title": "مستندات",
        "subtitle": "استقرار، پیکربندی، استفاده و لاگ‌های HTTP (nginx + Apache)",
        "nginx_disclaimer": (
            "ℹ️ **منبع اصلی: access logهای nginx.** **Apache combined** نیز پشتیبانی می‌شود "
            "(`apache.enabled: true` در servers.yaml). Caddy، Traefik و لاگ‌های خام برنامه — خیر. "
            "پشته آزمایشی Metis: Apache :8088 و `/admin/` — زبانه **لاگ‌های HTTP** را ببینید."
        ),
        "doc_language": "زبان راهنما",
        "image_missing": "تصویر صفحه یافت نشد: {path}",
        "sections": {
            "overview": "نمای کلی",
            "deployment": "استقرار",
            "configuration": "پیکربندی",
            "usage": "استفاده",
            "nginx": "لاگ‌های HTTP",
        },
    },
}
