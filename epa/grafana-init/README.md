# Grafana Initialization Container

This container replaces the complex Ansible workflow with a simple Python script that:

1. **Waits for Grafana to be ready** - polls Grafana API until it responds
2. **Creates InfluxDB datasource** - sets up the connection to InfluxDB automatically
3. **Imports dashboards** - loads all JSON files from `/dashboards` via Grafana API
4. **Exits cleanly** - runs once and stops (restart: "no")

## Environment Variables

- `GRAFANA_URL` - Grafana endpoint (default: `http://grafana:3000`)
- `GRAFANA_USER` - Grafana admin username (default: `admin`)
- `GRAFANA_PASSWORD` - Grafana admin password (default: `admin`)

## Volume Mounts

- **None** - Dashboards are built into the container at build time

## Build Process

- Dashboards are copied from `./grafana-init/dashboards/` into the container during build
- No runtime volume mounts needed - self-contained approach

## Usage

This container is automatically started by docker-compose after Grafana starts. It:

1. Replaces the entire `ansible/` directory and related scripts
2. Eliminates the need for the complex Makefile build process
3. Provides better error handling and logging
4. Is much faster and more reliable than the Ansible approach

## Dashboard Management

- **Built-in dashboards**: Stored in `./grafana/dashboards/` and imported by this container
- **User dashboards**: Created/modified through Grafana UI, stored in `grafana_dashboards` volume
- **Clean separation**: System dashboards vs user dashboards

## Update a dashboard

- Export dashboard for sharing as JSON file. If editing, overwrite the same dashboard in `./epa/grafana-init/dashboards/`
- To deploy later, rebuild grafana-init container (`docker compose build grafana-init`), delete existing dashboards, and run `up grafana-init` to re-deploy. Or, manually import the saved dashboard

## Add a dashboard

- New dashboards can be created in Grafana. To save it, in dashboard settings
  - Modify it to use EPA folder if it's not the case
  - Add `NetAppESeries` tag and save it
- Export to `./epa/grafana-init/dashboards/` using a new name

Next time you run `up grafana-init`, the new dashboard will be deployed to Grafana together with others.

## Troubleshooting

View logs with: `docker logs grafana-init`

Common issues:
- Grafana not ready: Container will retry up to 30 times
- Dashboard import failures: Check JSON syntax and Grafana version compatibility. Dashboards need the tag `NetAppESeries` to be automatically deployed
- Datasource creation: Verify InfluxDB is accessible at `http://influxdb:8086` or other configured endpoint ("EPA" data source)
