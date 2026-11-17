# HISTOR prod host, 2026-11-15: the running production image histor-histor:warden-0.27.0b-prod
# (sha256:8dcade5371f4…, MOMUS-evaluated WARDEN 0.27.0 build 403842d7) plus two changes from main, applied to the
# image's own files (each image file equalled main before the change):
#  * landing: the read cadence card, "every six hours (every 30 minutes for a week once its tools have changed
#    twice)" in en/es/fr/ru/zh (main bdad2a0ab; only those five lines);
#  * scanner.py / digest_xcheck.py: split JSON lines on "\n", not str.splitlines() (main 8f9e78965), and a line that is not JSON is a ScannerError (main 4f72b71e6). Remote polling
#    failed on every batch with a raw U+2028 in WARDEN 0.27.0's quoted clause since 2026-11-15 08:27Z.
# WARDEN is untouched.
FROM histor-histor:warden-0.27.0b-prod
USER 0:0
COPY --chown=0:0 --chmod=644 ctx/landing/index.html /app/docs/landing/index.html
COPY --chown=0:0 --chmod=644 ctx/landing/assets/i18n/ /app/docs/landing/assets/i18n/
COPY --chown=0:0 --chmod=644 ctx/histor/scanner.py ctx/histor/digest_xcheck.py /app/histor/
LABEL aicom.histor.overlay="landing-scanner-20261115" \
      aicom.histor.overlay.commits="bdad2a0ab 8f9e78965"
USER 65532:65532
