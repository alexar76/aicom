# Fábrica, catálogo y ecosistema: tres direcciones

[EN](landing-separation.md) · [RU](landing-separation.ru.md) · [ES](landing-separation.es.md) · [FR](landing-separation.fr.md) · [中文](landing-separation.zh.md)

- `https://magic-ai-factory.com/`: fábrica operativa, generador, catálogo y administración.
- `https://modeldev.modelmarket.dev/`: nueva página promocional de la fábrica.
- `https://ecosystem.modelmarket.dev/`: atlas canónico de la economía de las máquinas.

El botón principal abre la fábrica operativa. Los productos enlazan a `/#products`; generador, agentes, documentación y condiciones también abren la aplicación real. El atlas presenta la fábrica mediante su página promocional y sus tarjetas abren los servicios. Los enlaces al ecosistema usan su propio dominio.

La fábrica original está restaurada. La compra de servicios permanece activa: este traslado no cambia backend, cuenta, registro ni presupuestos. Véase [la guía](factory-subcontracting.es.md).

`app/HomePage.tsx` conserva el catálogo operativo; `components/factory/FactoryLanding.tsx` contiene la promoción. Solo el frontend separado compilado y ejecutado con `AICOM_SITE_ROLE=factory-landing` muestra esa promoción. Usa `NEXT_PUBLIC_SITE_URL=https://modeldev.modelmarket.dev`, cinco rutas (`/`, `/ru/`, `/es/`, `/fr/`, `/zh/`), canonical y alternativas lingüísticas propias, sin PWA ni widget de mercado de la aplicación. La compilación normal mantiene la fábrica.

El atlas se genera desde `scripts/github-io/`; su dominio canónico, sitemap y metadatos son `ecosystem.modelmarket.dev`. `ATLAS_SITE_URL` permite una compilación con otro origen explícito. No se hace push a GitHub; su redirección publicada anterior permanece hasta una publicación autorizada por separado.

Los dos modelos completos giran y admiten arrastre con ratón/dedo y flechas, sin pausa. Se respeta movimiento reducido. Son ilustraciones conceptuales, no datos en vivo. Se conservan encyclopedia, school, guides, learn y oracles en modeldev.

Producción: app en 9080; frontend modeldev en 9088, contenedor `aicom-frontend-modeldev-20261011`, imagen `ai-factory-frontend:modeldev-final-20261011`. El atlas usa `/var/www/ecosystem.modelmarket.dev` → `/var/www/ecosystem-atlas-20261011`. Fuentes y copias: `/root/domain-split-20261011/`; `rollback-modeldev.sh` restaura el vhost anterior sin detener la fábrica ni la compra de servicios. Certbot usa la cuenta existente, validación webroot, renovación automática y recarga nginx; esperar propagación DNS antes de emitir el certificado.

Validar idiomas, canonical, navegación, WebGL, secciones conservadas y API. Ejecutar typecheck, build y `python3 scripts/github-io/validate.py`. [Resultados](evidence/domain-split-2026-10-11/README.md).
