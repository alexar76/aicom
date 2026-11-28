# histor-histor for the daily peer checks: FROM the image the HISTOR app runs (other-revision-20261127,
# sha256:9414eb56…) with main's peers.py and the new fingerprint_xcheck.py. The app keeps running its image by ID.
ARG BASE
FROM ${BASE}
COPY --chmod=0644 files/peers.py files/fingerprint_xcheck.py /app/histor/
