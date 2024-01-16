FROM python:3.10.13-alpine3.18
ARG TAG=3.3.0

LABEL VERSION=${TAG}
LABEL org.opencontainers.image.authors="@scaleoutSean (Github)"
LABEL org.opencontainers.image.url="https://github.com/scaleoutsean/eseries-perf-analyzer/"
LABEL org.opencontainers.image.source="https://github.com/scaleoutsean/eseries-perf-analyzer/"
LABEL org.opencontainers.image.version=${TAG}
LABEL org.opencontainers.image.description="E-Series Performance Analyzer collector fetches performance metrics from NetApp E-Series storage arrays and sends them to InfluxDB."
LABEL org.opencontainers.image.title="E-Series Performance Analyzer collector"
LABEL org.opencontainers.image.vendor="@scaleoutSean (Github)"

RUN apk update && apk upgrade && rm -rf /var/cache/apk/*
ADD requirements.txt ./
RUN python -m pip install --upgrade pip
RUN pip --default-timeout=5 --retries 15 install --upgrade -r requirements.txt && rm -rf /root/.cache
ADD docker-entrypoint.sh *.py ./
RUN chmod +x *.sh *.py

ENV COLLECTION_INTERVAL=60
ENV RETENTION_PERIOD=26w
ARG API=localhost
ENV API=5.5.5.5
ENV DBADDRESS=7.7.7.7
ENV DBPORT=8086
ARG DBADDRESS=${DB_ADDRESS}:${DB_PORT} 
ARG SYSNAME
ARG SYSID
ENV SYSNAME=R26U25-EF600
ENV SYSID=600A098000F63714000000005E79C888

ENTRYPOINT ["./docker-entrypoint.sh"]
