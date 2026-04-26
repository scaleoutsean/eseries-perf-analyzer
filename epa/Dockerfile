FROM python:3.14.3-alpine3.23 AS builder

RUN apk update && apk upgrade && apk add --no-cache git
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python -m pip install --upgrade pip

ADD requirements.txt ./
RUN pip --default-timeout=5 --retries 15 install --upgrade -r requirements.txt

FROM python:3.14.3-alpine3.23
ARG TAG=latest

LABEL VERSION=${TAG}
LABEL org.opencontainers.image.authors="@scaleoutSean (Github)"
LABEL org.opencontainers.image.url="https://github.com/scaleoutsean/eseries-perf-analyzer/"
LABEL org.opencontainers.image.source="https://github.com/scaleoutsean/eseries-perf-analyzer/"
LABEL org.opencontainers.image.version=${TAG}
LABEL org.opencontainers.image.description="E-Series Performance Analyzer collector fetches NetApp E-Series storage arrays stats and config and exports for Prometheus scrapers."
LABEL org.opencontainers.image.title="E-Series Performance Analyzer collector and exporter for Prometheus"
LABEL org.opencontainers.image.vendor="@scaleoutSean (Github)"

# pyarrow runtime requires libstdc++ and potentially c-ares
RUN apk update && apk upgrade && apk add --no-cache libstdc++ c-ares && rm -rf /var/cache/apk/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
ADD docker-entrypoint.sh *.py ./
COPY santricity_client ./santricity_client
RUN chmod +x *.sh *.py

ENV COLLECTION_INTERVAL=60
ENV TLS_VERIFY=true
ENV API=5.5.5.5
ENV API_PORT=8443
ENV PROMETHEUS_PORT=8080

EXPOSE ${PROMETHEUS_PORT}

ENTRYPOINT ["./docker-entrypoint.sh"]
