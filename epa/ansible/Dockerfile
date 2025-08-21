ARG TAG=latest
ARG PROJ_NAME=ntap-grafana
ARG IMAGE=${PROJ_NAME}/python-base:${TAG}
# Installing Ansible requires gcc and other dependencies to build packages from source. We'll do this in 2 stages so we don't
#   have to have all of the build-time dependencies in the final image.
FROM ${IMAGE} AS builder

# Signifies this is a temporary image that can be purged
LABEL autodelete="true"
# Update package index and install build dependencies
RUN apk update && apk add --no-cache gcc musl-dev libffi-dev make openssl-dev
# Upgrade pip - should work fine with Python 3.10.16-alpine3.19
RUN python -m pip install --upgrade pip
# Install packages with better error handling and compatibility
RUN pip --default-timeout=5 --retries 15 install --upgrade --prefix=/install -r requirements.txt

FROM ${IMAGE}
COPY --from=builder /install /usr/local
ADD *.yml *.json ./
ADD dashboards/ ./dashboards
ADD tasks/ ./tasks
RUN mkdir -p /etc/ansible && touch /etc/ansible/hosts && mkdir -p /home/dashboards/backup
ENTRYPOINT ["ansible-playbook", "-v"]
CMD ["main.yml"]
