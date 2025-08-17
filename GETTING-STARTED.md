# Getting Started with E-Series Performance Analyzer

- [Getting Started with E-Series Performance Analyzer](#getting-started-with-e-series-performance-analyzer)
  - [CLI](#cli)
  - [Docker](#docker)
    - [Step 1: Clone the Repository and install Requirements](#step-1-clone-the-repository-and-install-requirements)
    - [Step 2: Generate or get TLS Certificates](#step-2-generate-or-get-tls-certificates)
    - [Step 3: Set Up Configuration Files](#step-3-set-up-configuration-files)
    - [Step 4: Build and Launch the Application](#step-4-build-and-launch-the-application)
    - [Step 5: Verify the Setup](#step-5-verify-the-setup)
    - [Step 6: Access Web interfaces (optional)](#step-6-access-web-interfaces-optional)
    - [Step 7: View metrics](#step-7-view-metrics)
    - [Troubleshooting](#troubleshooting)
  - [Kubernetes](#kubernetes)


This guide will walk you through setting up and using the E-Series Performance Analyzer.


## CLI

```sh
git clone https://github.com/scaleoutsean/eseries-perf-analyzer.git
cd eseries-perf-analyzer
pyhon3 -m venv .venv
source .venv/bin/activate # use "deactivate" to GTHO
```

Create a virtual environment and install the requirements (`app/requirements.txt`) with `pip`.

If you want to hard-code startup parameters, copy `.config.example` to `config.yaml`, edit this file and then try with with fewer arguments.

```sh
cp config.example config.yml
```

Edit `config.yml` to match your environment (optional):

```sh
vim config.yml
```

Get an InfluxDB 3 API token that you need to access InfluxDB API.

From the top directory, run Collector:

```sh
python3 ./app/collector.py -h 
```

Some of the arguments don't start anything, but instead run for a few seconds and quit. See the details here:


```sh
usage: collector.py [-h] [--config CONFIG] [--api API [API ...]] [--intervalTime INTERVALTIME] [--influxdbUrl INFLUXDBURL]
                    [--influxdbDatabase INFLUXDBDATABASE] [--influxdbToken INFLUXDBTOKEN] [--toJson TOJSON] [--fromJson FROMJSON] [--showReachability]
                    [--tlsCa TLSCA] [--threads THREADS] [--tlsValidation {strict,normal,none}] [--showSantricity] [--logfile LOGFILE]
                    [--loglevel {DEBUG,INFO,WARNING,ERROR}] [--maxIterations MAXITERATIONS] [--bootstrapInfluxDB]

Collect E-Series metrics

options:
  -h, --help            show this help message and exit
  --config CONFIG       Path to YAML or JSON config file. Overrides CLI and .env args if used.
  --api, -u, -p API [API ...]
                        List of E-Series API endpoints (IPv4 or IPv6 addresses or hostnames) to collect from. Use -u for username and -p for password
                        inline, e.g., --api 10.0.0.1 -u admin -p secret. Overrides config file.
  --intervalTime INTERVALTIME
                        Collection interval in seconds (minimum 60). Determines how often metrics are collected or replayed.
  --influxdbUrl INFLUXDBURL
                        InfluxDB server URL (overrides config file and .env if set). Example: https://db.example.com:8181
  --influxdbDatabase INFLUXDBDATABASE
                        InfluxDB database name (overrides config file and .env if set).
  --influxdbToken INFLUXDBTOKEN
                        InfluxDB authentication token (overrides config file and .env if set).
  --toJson TOJSON       Directory to write collected metrics as JSON files (for offline replay or debugging).
  --fromJson FROMJSON   Directory to replay previously collected JSON metrics instead of live collection.
  --showReachability    Test reachability of SANtricity API endpoints and InfluxDB before collecting metrics.
  --tlsCa TLSCA         Path to CA certificate for verifying API/InfluxDB TLS connections (if not in system trust store).
  --threads THREADS     Number of concurrent threads for metric collection. Default: 4. 4 or 8 is typical.
  --tlsValidation {strict,normal,none}
                        TLS validation mode for SANtricity API: strict (require valid CA and SKI/AKI), normal (default Python validation), none (disable
                        all TLS validation, INSECURE, for testing only). Default: strict.
  --showSantricity      Test SANtricity API endpoints independently of session creation and InfluxDB logic.
  --logfile LOGFILE     Path to log file. If not provided, logs to console only.
  --loglevel {DEBUG,INFO,WARNING,ERROR}
                        Log level for both console and file output. Default: INFO
  --maxIterations MAXITERATIONS
                        Maximum number of collection iterations to run before exiting. Default: 0 (run indefinitely). Set to a positive integer to exit
                        after that many iterations.
  --bootstrapInfluxDB   Bootstrap InfluxDB: create database if needed, create all measurement tables with proper schemas, validate, and report
                        structure. Exits after completion.
```

## Docker

The main difference between running CLI and Docker Compose is Docker Compose has most of the stack ready for you.  

Docker Compose ignores `--config` that the CLI has. Use `.env` or `docker-compose.yaml`  to configure Collector in Docker.

Note that you *can* run some Docker Compose services on one VM (or host) and others on another. For example, you could run Collector on one VM and InfluxDB on another. But in that case you would have to tell containers to use FQDN or external IP to connect to the remote service.


### Step 1: Clone the Repository and install Requirements

```sh
git clone https://github.com/scaleoutsean/eseries-perf-analyzer.git
cd eseries-perf-analyzer
```

### Step 2: Generate or get TLS Certificates

**NOTE:** If you have own Certificate Authority (CA) you should just use your own. Or, you could run this step to see what certificates are required and where to put them, create and clobber them with your own.

The certificate generation script should be executed with your E-Series SANtricity controller('s) IP addresses if you don't have valid certificates on those systems.

```sh
./utils/gen.py --controllers 10.0.0.1 10.0.0.2
```

This script will:
- Create a self-signed root CA
- Generate certificates for all services
- Update passwords in your `.env` file and possibly `./secrets/*.env` files
- Prepare the environment for secure communication

Note that you can ignore the generated TLS certificates for E-Series controller(s) and you should probably do that if your have the proper CA in your environment. But if you use low-quality snake-oil TLS certificates, EPA containers won't trust those certificates without additional work on your side.


### Step 3: Set Up Configuration Files

1. Create and edit the environment file (recommended) or docker-compose.yaml:

```sh
cp env.example .env
vim .env
```

If you used `./utils/gen.py` to create passwords, `./secrets/*.env` may have passwords in them.

Key settings to update:
- `API`: IP addresses of FQDNs of your E-Series controller(s)
- Other settings can be left as defaults for initial setup


### Step 4: Build and Launch the Application

Build and start the Docker containers:

```sh
docker compose build
docker compose up
# if it works OK, do a CTRL+C and then
# docker compose up -d
```

Note that Grafana won't stat by default because it is already exposed on Nginx to LAN and it uses the default Grafana credentials.
It is recommended to set up your own as EPA doesn't want to have Grafana in its stack, but you can start with it with `docker --profile monitoring [-d] up`.

### Step 5: Verify the Setup

Check that all services are running properly:

```bash
docker compose ps
```

All services that are up and proxied by Nginx should be reachable from LAN at this point.

```sh
docker compose logs <service>
# docker compose logs influxdb
```

**NOTE**: to run just Collector container, use `docker compose run --rm collector -h`. You may want to do this for one-off tasks or other reasons.

### Step 6: Access Web interfaces (optional)

These are not "managed" in the sense that they're only properly deployed and ready to be configured, but EPA doesn't attempt to manage these systems. Assuming your proxy's external host name is `epa-proxy`:

- **InfluxDB Explorer**: https://epa-proxy:18443
  - API token for InfluxDB 3 access
  - Add your InfluxDB (https://influxdb:8181 in a shared Docker Compose environment, if you haven't changed service name)
- **S3 console**: https://epa-proxy:9001
  - Username: Value of MINIO_ROOT_USER in your .env file
  - Password: Value of MINIO_ROOT_PASSWORD in your .env file
- **Grafana**: https://epa-proxy:3443
  - `admin`/`admin` as per Grafana defaults

The reason there isn't much done about "fine-tuning" these is: everyone should have these shared services elsewhere and not rely on a collector project for unrelated infrastructure services that should be actively managed for security and other reasons. 

These non-essential services in the EPA stack are meant for *production-ready* prototyping, testing, training, and evaluation, but the last 20% should be done by the folks who are supposed to manage them.

### Step 7: View metrics

Once the system has collected data for a few minutes, you can create dashboards in the InfluxDB Explorer UI to visualize your E-Series performance metrics.

From **InfluxDB Explorer**:
- add database (with InfluxDB running internally in Docker, http**s**://influxdb:8181, and if outside use the Nginx FQDN, such as https://nginx:8181)
- select `eserries` database from database drop-down list, and run the query `SELECT * FROM POWER`.

From **the CLI**:
- use InfluxDB CLI with environment variables or arguments to query InfluxDB and show tables with `SHOW MEASUREMENTS`
- locally within Docker Compose environment you may use the `utils` container for this - see [TIPS](TIPS.md).

From **Grafana**: 
- add InfluxDB Data Source: 
  - use `SQL` language dialect for InfluxDB 3
  - if both Grafana and InfluxDB run in same Docker Compose, use https://influxdb:8181, if not, use Nginx FQDN, such as https://nginx:8181
  - if Grafana cannot connect via HTTPS see [DOCUMENTATION](./DOCUMENTATION.md) for additional details about this
- you will need InfluxDB API token to access the DB. Paste the token near the bottom just below database name

### Troubleshooting

- Check container logs: `docker compose logs collector` (or other EPA service name from `docker ps`)
- Ensure certificates were generated correctly: `ls -la certs/`
- Verify controller connectivity: `collector.py --testReachability` or `collector.py --showSantricity`
- Check for error messages in the logs: `docker compose logs | grep ERROR` or `docker compospe logs influxdb`


## Kubernetes

TODO
