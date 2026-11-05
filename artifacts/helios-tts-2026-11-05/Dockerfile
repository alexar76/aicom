# HELIOS worker: the running security image plus edge-tts 7.3.1 (7.2.8 gets 403 from Edge read-aloud, 2026-11-05).
FROM aicom-security:helios-worker-hc-live-20261031
USER root
RUN pip freeze > /tmp/before.txt \
 && pip install --no-cache-dir "edge-tts==7.3.1" \
 && pip freeze > /tmp/after.txt \
 && echo "--- packages changed:" && (diff /tmp/before.txt /tmp/after.txt || true) \
 && python -c "import importlib.metadata as m; v = m.version('edge_tts'); assert v == '7.3.1', v" \
 && rm -f /tmp/before.txt /tmp/after.txt
USER helios
