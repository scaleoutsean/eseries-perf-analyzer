FROM docker.io/library/python:3.14.9-alpine3.24

# Install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# Copy dashboards directly into container
COPY dashboards /dashboards

# Copy the initialization script
COPY grafana_init.py /grafana_init.py

ENV GRAFANA_URL="https://grafana:3000"

# Make script executable and set as entrypoint
WORKDIR /
CMD ["python", "/grafana_init.py"]
