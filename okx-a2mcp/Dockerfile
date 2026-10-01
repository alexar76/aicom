FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund && npm cache clean --force
COPY src ./src
USER node
ENV HOST=0.0.0.0 PORT=9480
EXPOSE 9480
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:9480/health >/dev/null || exit 1
CMD ["node", "src/server.js"]
