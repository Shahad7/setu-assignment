# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /app

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# this layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip install -r requirements.txt

# Use the minimal runtime image.
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user and group for security.
# Standard public images run as root by default, so this is required.
RUN addgroup --system appgroup && adduser --system --group appuser

WORKDIR /app

# Copy the built virtual environment from the builder stage and change ownership.
COPY --from=builder --chown=appuser:appgroup /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy the source code into the container and change ownership.
COPY --chown=appuser:appgroup . .

# Switch to the non-root user.
USER appuser

# Expose the port that the application listens on.
EXPOSE 8000

# Run the application.
CMD ["/venv/bin/python3", "-m", "uvicorn", "src.main:app", "--host=0.0.0.0", "--port=8000"]