# The one environment every agent-habits confirmation run uses (both agents, every cell).
# Toolchains for the five study languages, the two pinned agent CLIs, a non-root user; no credentials.
FROM gitgalaxy-gnucobol:3

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      openjdk-17-jdk-headless python3 python3-venv gcc g++ make git curl ca-certificates nodejs npm procps \
    && rm -rf /var/lib/apt/lists/*

# D7: the checker's referee (python-chess) in its own venv, used only by /check/check.
RUN python3 -m venv /opt/checkvenv && /opt/checkvenv/bin/pip install --no-cache-dir chess==1.11.2

# Codex CLI, pinned (D2).
RUN npm install -g @openai/codex@0.166.0 && codex --version

# Claude Code, pinned (D2): the exact binary of the host install.
COPY claude-2.1.316 /usr/local/bin/claude
RUN chmod 755 /usr/local/bin/claude

RUN useradd -m -u 1000 -s /bin/bash agent
USER agent
ENV HOME=/home/agent PATH=/home/agent/.cargo/bin:$PATH

# Rust, pinned toolchain, minimal profile.
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain 1.82.0 \
    && cargo --version

RUN git config --global user.name "agent" && git config --global user.email "agent@localhost" \
    && git config --global init.defaultBranch main

WORKDIR /work
