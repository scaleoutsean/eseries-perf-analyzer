## Change log

- 4.0.0 beta (August 15, 2025)
  - This beta version includes only EPA Collector (not the entire EPA stack, which remains in scope for release EPA 4)
  - NEW: Major database back-end upgrade to InfluxDB 3 Core. Data migration from EPA 3 (InfluxDB v1) is not supported  
  - NEW: controller information collected for each controller (for monitoring of load balancing across controllers in two-controller configurations)
  - NEW: physical drive information collected (for configuration, rather than performance, monitoring)
  - NEW: improvements in security-related aspects (defaults: HTTPS only, HTTPS everywhere, TLS v1.3 only, strict TLS certificate validation)
  - IMPROVED: temperature sensors, PSU (power supply unit) readings and flash disk wear level all collected and should handle multiple shelves
  - IMPROVED: many smaller improvements, updates of external Python modules
  - IMPROVED: significant code overhaul with most of v3 complexity gone (and some has been added to accommodate new high-value features)
  - REMOVED: ARM64 support (due to lack of interest/feedback). EPA Collector 4 likely works on ARM64, but no testing or bug fixes will be done

- 3.3.1 (June 1, 2024):
  - Dependency update (requests library)

- 3.3.0 (April 15, 2024):
  - collector now collects *controller shelf*'s total power consumption metric (sum of PSUs' consumption) and temperature sensors' values 
  - Security-related updates of various components

- 3.2.0 (Jan 30, 2023):
  - No new features vs. v3.1.0
  - No changes to Grafana container, Grafana charts, and InfluxDB container
  - collector and dbmanager are now completely independent of containers built by InfluxDB and Grafana Makefile 
  - New Kubernetes folder with Kubernetes-related instructions and sample YAML files
  - collector and dbmanager can work on both AMD64 and ARM64 systems

- 3.1.0 (Jan 12, 2023):
  - No changes to Grafana dashboards
  - Updated Grafana v8 (8.5.15), Python Alpine image (3.10-alpine3.17) and certifi (2022.12.7)
  - Remove SANtricity Web Services Proxy (WSP) and remove WSP-related code from collector 
  - Make InfluxDB listen on public (external) IP address, so that collectors from remote locations can send data in
  - Add the ability to alternate between two E-Series controllers to collector (in upstream v3.0.0 the now-removed WSP would do that)
  - Add collection of SSD wear level for flash media (panel(s) haven't been added, it's up to the user to add them if they need 'em)
  - Expand the number of required arguments in `collector.py` to avoid unintentional mistakes
  - Collector can run in Kubernetes and Nomad
  - Add dbmanager container for the purpose of uploading array configuration to InfluxDB (and potentially other DB-related tasks down the road)
  - Add simple Makefile for collector containers (collector itself, and dbmanager)
  - Old unit tests are no longer maintained
