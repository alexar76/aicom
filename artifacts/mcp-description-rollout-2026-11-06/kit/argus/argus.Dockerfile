# syntax=docker/dockerfile:1
# ARGUS (aicom 624e03e43: MCP server state on /health and /status, owner note) on top of the hc-live image (keeps the 2026-10-31 OS fixes): only /app and the node binary change.
ARG BASE
FROM node:22.23.4-trixie-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY vendor ./vendor
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM node:22.23.4-trixie-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
COPY vendor ./vendor
RUN npm install --omit=dev --omit=optional && test ! -e node_modules/@aimarket/agent

FROM ${BASE}
USER root
COPY --from=deps /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
RUN rm -rf /app/dist /app/node_modules /app/web /app/vendor /app/package.json /app/package-lock.json /app/argus.config.example.json
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package.json /app/package-lock.json ./
COPY vendor ./vendor
COPY --from=build /app/dist ./dist
COPY web ./web
COPY argus.config.example.json ./
USER node
RUN node --version && node --check dist/index.js
