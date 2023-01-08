ARG TAG=latest
ARG PROJ_NAME=ntap-grafana
FROM ${PROJ_NAME}-plugin/eseries_monitoring/python-base
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

RUN python -m pip install --upgrade pip
RUN pip --default-timeout=5 --retries 15 install --upgrade -r requirements.txt && rm -rf /root/.cache

ADD docker-entrypoint.sh *.py ./
RUN chmod +x *.sh *.py

ENTRYPOINT ["./docker-entrypoint.sh"]
