ARG TAG=3.4
ARG PROJ_NAME=ntap-grafana
FROM ${PROJ_NAME}/python-base:${TAG}

# Install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# Copy dashboards directly into container
COPY dashboards /dashboards

# Copy the initialization script
COPY grafana_init.py /grafana_init.py

# Make script executable and set as entrypoint
WORKDIR /
CMD ["python", "/grafana_init.py"]
