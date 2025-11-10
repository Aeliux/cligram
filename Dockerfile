FROM python:3.13.9-alpine3.21 AS python-base
FROM mcr.microsoft.com/devcontainers/base:alpine-3.21

# Copy Python from the python-base stage
COPY --from=python-base /usr/local /usr/local

# Ensure Python is in PATH and libraries are linked
ENV PATH="/usr/local/bin:$PATH"
RUN ldconfig /usr/local/lib || true

# Install poetry
RUN pip install --no-cache-dir poetry black ruff mypy
