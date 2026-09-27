# syntax=docker/dockerfile:1

# Use the official uv image for the builder stage
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
ENV VIRTUAL_ENV="/venv"

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/uv to speed up subsequent builds.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    uv pip install -r requirements.txt

# Use the official uv image for the runtime stage
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN addgroup --system appgroup && \
    useradd --system --gid appgroup --create-home --home-dir /home/appuser appuser

# Set the HOME environment variable so uv knows where to look
ENV HOME=/home/appuser

WORKDIR /app

# Copy the built virtual environment from the builder stage and change ownership.
COPY --from=builder --chown=appuser:appgroup /venv /venv
ENV PATH="/venv/bin:$PATH"
ENV VIRTUAL_ENV="/venv"

# Copy the source code into the container and change ownership.
COPY --chown=appuser:appgroup . .

# Switch to the non-root user.
USER appuser

# Expose the port that the application listens on.
EXPOSE 8000

# Run the application using uv run (it automatically detects the VIRTUAL_ENV variable)
CMD ["uv", "run", "uvicorn", "src.main:app", "--host=0.0.0.0", "--port=8000"]