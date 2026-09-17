FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS dependencies
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHON_DOTENV_DISABLED=1
WORKDIR /app
COPY tourist_congestion_backend/requirements.lock ./requirements.lock
RUN pip install --prefix=/install --require-hashes -r requirements.lock

FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS test
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHON_DOTENV_DISABLED=1
COPY --from=dependencies /install /usr/local
WORKDIR /app
COPY tourist_congestion_backend/ ./
RUN DJANGO_DEBUG=true python manage.py collectstatic --noinput
RUN chmod -R a+rX /app /usr/local

FROM test AS runtime
LABEL org.opencontainers.image.source="https://github.com/hurdoo/ilion"
LABEL org.opencontainers.image.description="ILION recommendation algorithm MVP, under development"
ENV DJANGO_DEBUG=false DATA_WORKER_ENABLED=true
RUN find /app -type f \( -name 'test*.py' -o -name '*tests.py' \) ! -path '/app/config/test_dashboard.py' -delete
USER 65532:65532
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD ["python", "runtime_healthcheck.py"]
CMD ["python", "runtime.py"]
