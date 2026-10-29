FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PAGESPEED_CLOUD=1 \
    PAGESPEED_PUBLIC_REPORTS=1 \
    PAGESPEED_DATA_DIR=/data \
    PAGESPEED_HEADLESS=1 \
    PAGESPEED_COLLECTOR=api \
    PAGESPEED_ALLOW_BROWSER=0

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates gosu tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home pagespeed \
    && mkdir /data && chown pagespeed:pagespeed /data
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . ./
RUN chmod +x /app/docker-entrypoint.sh
EXPOSE 5055
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "server.py"]
