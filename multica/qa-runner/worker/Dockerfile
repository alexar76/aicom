# Deployment must supply the reviewed official-image digest as NODE_IMAGE.
ARG NODE_IMAGE=node:22.23.4-bookworm-slim@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d
FROM ${NODE_IMAGE}
WORKDIR /opt/qa
COPY --chown=0:0 package.json http.mjs smoke.mjs idle.mjs /opt/qa/
RUN chmod 0555 /opt/qa && chmod 0444 /opt/qa/package.json /opt/qa/*.mjs
USER 10001:10001
ENTRYPOINT ["node", "/opt/qa/idle.mjs"]
