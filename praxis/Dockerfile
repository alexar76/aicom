# PRAXIS — practice target for the self-healing loop.
# Build from the MONOREPO ROOT:  docker build -f praxis/Dockerfile -t praxis:latest .
FROM python:3.11-slim AS base
WORKDIR /app

COPY oracles/core /app/core
COPY praxis /app/praxis

# `aimarket-oracle-core` is installed so the repair can IMPORT the canonical form instead of
# writing a second copy of it. The library has to be here before a fix can use it — what the
# image contains is an operator's decision, and the loop may not add a dependency of its own.
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" "cryptography>=42" \
 && pip install --no-cache-dir -e "/app/core[pqc]"

# The stage the deploy hand builds to run PRAXIS's own tests against a candidate image before
# anything is promoted. Not the default target, so pytest never ships to the runtime image.
FROM base AS test
RUN pip install --no-cache-dir pytest
CMD ["python", "-m", "pytest", "/app/praxis/tests", "-q"]

FROM base AS runtime
EXPOSE 9460
CMD ["python", "-m", "praxis.praxis"]
