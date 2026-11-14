FROM argus-checkout-browser:playwright-1.64.1
COPY --chmod=0444 server.mjs /app/server.mjs
COPY --chmod=0555 entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
