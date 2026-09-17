# Same base as .github/workflows/arc-linux-release.yml (ubuntu-latest = 24.04,
# glibc 2.39): a kernel built here needs no newer glibc than the official
# release, so the platform loads it and arc/pack_kernel.py accepts it.
# Built and run by arc/build-kernel-docker.sh; nothing here is task-specific.
FROM ubuntu:24.04
ARG RUST_TOOLCHAIN=1.98.0
ENV DEBIAN_FRONTEND=noninteractive \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake pkg-config curl ca-certificates git \
 && rm -rf /var/lib/apt/lists/*
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain "${RUST_TOOLCHAIN}" \
 && chmod -R a+rwX /usr/local/cargo /usr/local/rustup   # builds run as the host user, not root
WORKDIR /work
