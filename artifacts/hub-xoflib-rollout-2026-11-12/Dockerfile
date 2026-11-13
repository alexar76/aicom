ARG BASE
FROM ${BASE}
ARG RUN_USER
USER root
RUN --mount=type=bind,source=wheel,target=/wheel,ro \
    python -m pip install --no-index --no-deps --no-cache-dir /wheel/*.whl
USER ${RUN_USER}
