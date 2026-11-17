# ARGUS with WARDEN 0.27.0 (warden#14 fix, ruleset 20) on top of the live image; nothing else changes.
ARG ARGUS_BASE_IMAGE=aicom-security:argus-hudson-auto-receipt-20261114
FROM ${ARGUS_BASE_IMAGE}
USER root
RUN rm -rf /app/node_modules/@aimarket/warden
COPY warden/ /app/node_modules/@aimarket/warden/
RUN node -e "const p=require(\"/app/node_modules/@aimarket/warden/package.json\"); if (p.name!==\"@aimarket/warden\"||p.version!==\"0.27.0\") process.exit(1)"
USER node
LABEL aicom.argus.overlay="warden-0270-20261115" org.aimarket.warden.version="0.27.0" org.aimarket.warden.tarball-sha256="525622b730b3262d595aa2f3ad9ec059306a875fcf178b2ad1cd9cb15457829e"
