FROM ai-factory-frontend:motion-20261011
USER root
WORKDIR /app/web/frontend
COPY web/frontend/ /app/web/frontend/
COPY docs/ /app/docs/
ARG SITE_URL
ARG SITE_ROLE
ENV NEXT_PUBLIC_SITE_URL=$SITE_URL AICOM_SITE_ROLE=$SITE_ROLE AICOM_BACKEND_INTERNAL_URL=http://aicom-app-1:8081 INTERNAL_API_URL=http://aicom-app-1:8081 NEXT_TELEMETRY_DISABLED=1
RUN rm -rf .next && npm ci --include=dev --ignore-scripts --no-audit --no-fund && npm rebuild sharp && NODE_OPTIONS=--max-old-space-size=1536 npm run build && npm prune --omit=dev --ignore-scripts --no-audit --no-fund && chown -R 10001:10001 .next
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 CMD curl -fsS http://127.0.0.1:8080/ > /dev/null || exit 1
CMD ["node","node_modules/next/dist/bin/next","start","--hostname","0.0.0.0","--port","8080"]
