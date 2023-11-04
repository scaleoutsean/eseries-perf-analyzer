FROM python:3.10.13-alpine3.18
ARG TAG=3.3.0
LABEL VERSION=${TAG}

ADD ../config.json ./
ADD dbmanager/requirements.txt ./
ADD dbmanager/db_manager.py ./
ADD dbmanager/docker-entrypoint.sh *.py ./
RUN chmod +x *.sh *.py

RUN apk update && apk upgrade && rm -rf /var/cache/apk/*
RUN python -m pip install --upgrade pip
RUN pip --default-timeout=5 --retries 15 install --upgrade -r requirements.txt && rm -rf /root/.cache

ENV COLLECTION_INTERVAL=300
ENV RETENTION_PERIOD=52w
ENV DBADDRESS=7.7.7.7
ENV DBPORT=8086
ARG DBADDRESS=${DB_ADDRESS}:${DB_PORT} 

ENTRYPOINT ["./docker-entrypoint.sh"]
