FROM python:3.10.13-alpine3.18
ARG TAG=3.3.0
LABEL VERSION=${TAG}

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
