# Node security baseline: 22.23.4 (2026-10-21 security release).
FROM node:22.23.4-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json ./
COPY vendor ./vendor
RUN npm ci --omit=dev --no-audit --no-fund && npm cache clean --force
COPY src ./src
# The sellers' review answers (src/web/review.js) live on a named volume mounted here; an empty volume
# takes this directory's owner, so the read-only container can still write its one file.
RUN mkdir -p /data/review && chown node:node /data/review
USER node
ENV HOST=0.0.0.0 PORT=9480
EXPOSE 9480
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:9480/health >/dev/null || exit 1
CMD ["node", "src/server.js"]
