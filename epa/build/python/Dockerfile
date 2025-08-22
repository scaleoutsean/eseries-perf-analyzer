ARG TAG=3.4
ARG CONTAINER_PYTHON_TAG=3.10.16-alpine3.19

FROM epa/alpine-base:${TAG} AS builder
# Signifies this is a temporary image that can be purged
LABEL autodelete="true"

FROM python:${CONTAINER_PYTHON_TAG}
ARG TAG=3.4
ARG PIP_CONF=pip.conf
ADD $PIP_CONF /etc/pip.conf
COPY --from=builder /etc/apk/repositories /etc/apk/repositories
ONBUILD WORKDIR /home
ONBUILD COPY requirements.txt .
ONBUILD RUN apk update && apk upgrade && rm -rf /var/cache/apk/*
