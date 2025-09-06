FROM python:3.13-alpine

ENV EPA_VERSION=${COLLECTOR_VERSION}
ARG TAG=${EPA_VERSION}

LABEL VERSION=${TAG}
LABEL org.opencontainers.image.authors="@scaleoutSean (Github)"
LABEL org.opencontainers.image.url="https://github.com/scaleoutsean/eseries-perf-analyzer/"
LABEL org.opencontainers.image.source="https://github.com/scaleoutsean/eseries-perf-analyzer/"
LABEL org.opencontainers.image.version=${TAG}
LABEL org.opencontainers.image.description="E-Series Performance Analyzer collector fetches metrics and config from NetApp E-Series storage arrays and writes them to InfluxDB 3."
LABEL org.opencontainers.image.title="E-Series Performance Analyzer Collector"
LABEL org.opencontainers.image.vendor="@scaleoutSean (Github)"

RUN apk update && apk upgrade --no-cache
# Optionally we could add CA certificate to container OS but we recommend to use CLI args or .env/YAML
# RUN apk add --no-cache ca-certificates && update-ca-certificates
RUN python -m pip install --upgrade pip
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip --default-timeout=5 --retries 15 install --upgrade -r requirements.txt && rm -rf /root/.cache
COPY collector.py ./
COPY *.py /app/
# bring in entrypoint
COPY entrypoint.sh ./
RUN chmod +x *.sh

ENTRYPOINT ["./entrypoint.sh"]
