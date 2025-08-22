FROM python:3.10.16-alpine3.19

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
