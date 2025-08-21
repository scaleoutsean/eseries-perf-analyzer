ARG CONTAINER_ALPINE_TAG=3.19
ARG TAG=latest
FROM alpine:${CONTAINER_ALPINE_TAG}
ARG TAG=latest
LABEL VERSION=${TAG}
ARG REPO_FILE=repositories
ADD $REPO_FILE /etc/apk/repositories
ONBUILD RUN apk update && apk upgrade && rm -rf /var/cache/apk/*
