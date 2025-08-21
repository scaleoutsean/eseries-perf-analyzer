ARG BASE_IMAGE=influxdb:1.11.8-alpine
FROM ${BASE_IMAGE}

# Install common utilities on Alpine
USER root
RUN apk update && apk add --no-cache curl wget vim 

# Create a non-root user to run commands
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Copy entrypoint and README (assumed present in build context)
COPY entrypoint.sh /usr/local/bin/utils-entrypoint.sh
RUN chmod +x /usr/local/bin/utils-entrypoint.sh

WORKDIR /home/appuser
COPY README.txt /home/appuser/README.txt
RUN chown appuser:appgroup /home/appuser/README.txt

USER appuser

# By default, run the entrypoint which will prepare environment then exec the CMD
ENTRYPOINT ["/usr/local/bin/utils-entrypoint.sh"]

# Keep container running by default (can be overridden by compose command)
CMD ["tail", "-f", "/dev/null"]
