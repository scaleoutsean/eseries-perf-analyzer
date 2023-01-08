ARG TAG=latest
ARG PROJ_NAME=ntap-grafana
FROM ${PROJ_NAME}-plugin/eseries_monitoring/python-base
ENV COLLECTION_INTERVAL=300
ENV RETENTION_PERIOD=52w
ENV DBADDRESS=7.7.7.7
ENV DBPORT=8086
ARG DBADDRESS=${DB_ADDRESS}:${DB_PORT} 

RUN python -m pip install --upgrade pip
RUN pip --default-timeout=5 --retries 15 install --upgrade -r requirements.txt && rm -rf /root/.cache

ADD config.json ./
ADD db_manager.py ./
ADD docker-entrypoint.sh *.py ./
RUN chmod +x *.sh *.py

ENTRYPOINT ["./docker-entrypoint.sh"]
