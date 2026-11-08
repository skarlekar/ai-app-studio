FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GPTAPPS_PORT=8765
WORKDIR /app

# Only public source and examples enter the image.
COPY gptapps/ /app/gptapps/
COPY LICENSE /app/LICENSE
COPY scripts/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN python -c "import sys; assert sys.version_info >= (3, 11)" \
    && chmod -R a+rX /app \
    && mkdir -p /data /config \
    && chown -R 10001:10001 /data

USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=2s --timeout=3s --start-period=3s --retries=15 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('GPTAPPS_PORT', '8765') + '/api/config', timeout=2).close()"
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
