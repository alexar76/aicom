# Node security baseline: 22.23.4 (2026-10-21 security release).
FROM node:22.23.4-alpine AS base
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY server.js ./
ENV PORT=3000
EXPOSE 3000
USER node
CMD ["node", "server.js"]
