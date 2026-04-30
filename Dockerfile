FROM ghcr.io/ministryofjustice/analytical-platform-airflow-python-base:1.28.0@sha256:a0989a2bea050374220b102a7b2c5643666f80e23a95b1d5033e2dfdb8b350c4

WORKDIR /opt/analyticalplatform

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
ADD . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

ENV PATH="/opt/analyticalplatform/.venv/bin:$PATH"

RUN pwd && ls -la && \
    find . -maxdepth 2 -type f -iname "main.py" -print

ENTRYPOINT ["python", "src/connector/main.py"]
