FROM modelmarket-hub:pre3170-c66fe5e88c43
USER root
COPY aimarket_hub-3.17.0-py3-none-any.whl /tmp/aimarket_hub-3.17.0-py3-none-any.whl
COPY activate_wheel.py /tmp/activate_wheel.py
RUN python -m pip install --no-index --no-deps --force-reinstall /tmp/aimarket_hub-3.17.0-py3-none-any.whl \
    && python /tmp/activate_wheel.py \
    && python -m pip check \
    && chown -R hub:hub /app/aimarket_hub \
    && rm /tmp/aimarket_hub-3.17.0-py3-none-any.whl /tmp/activate_wheel.py
LABEL org.opencontainers.image.version="3.17.0"
LABEL ai.market.release.wheel.sha256="832f91e61cf486534bcb04552048a8fc14e392fe2cf866c3f56b5a73cd62219f"
USER hub
