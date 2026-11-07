FROM rust:1.96-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-dev pkg-config && rm -rf /var/lib/apt/lists/*
WORKDIR /work
