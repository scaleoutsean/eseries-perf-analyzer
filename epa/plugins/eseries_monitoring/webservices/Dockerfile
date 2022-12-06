ARG CONTAINER_WEBSERVICES_TAG=5.40
FROM netapp/eseries-webservices:${CONTAINER_WEBSERVICES_TAG} 
ARG TAG=latest
ARG PROJ_NAME=ntap-grafana
WORKDIR /opt/netapp/webservices_proxy
ADD wsconfig.xml ./wsconfig.xml
WORKDIR /opt/netapp/webservices_proxy
COPY users.properties ./data/config/
CMD ["./webserver.sh"]
