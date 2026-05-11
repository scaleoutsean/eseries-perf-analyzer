# About various helper scripts

## Makefile

`make vendor` copies SANtricity client library which EPA Collector uses to avoid duplicating queries and reports that SANtricity client library already has. In Docker build process, that client library is copied into EPA Collector container.

The same library is installed via `./epa/requirements.txt`, but on host (which can't be used in `docker build`).

## TLS Certificate and data directory scripts

If you don't have own CA and/or certificates, create a virtual environment and install `tomlkit`.

```sh
$ pip install tomlkit
$ ./scripts/gen_ca_tls_certs.py  -h
usage: gen_ca_tls_certs.py [-h] 
  [--service {all,grafana,eseries,ca,vm,s3}]
  [--download-eseries-cert {auto,yes,no}] 
  [--eseries-controllers ESERIES_CONTROLLERS]
  [--use-sudo] [--force-regenerate]
```

You can't use `--download-eseries-cert` if your E-Series certs are invalid (not mapped to a resolvable FQDN or hostname), so we'll skip that step. Assuming you've screwed up once already, `--force-generate` can be used to create "missing" or new self-signed certificates.

```sh
$ ./scripts/gen_ca_tls_certs.py --service all --force-regenerate
Certificate request self-signature ok
subject=CN = grafana
Certificate request self-signature ok
subject=CN = vm
Certificate request self-signature ok
subject=CN = proxy
Do you want to download certificate from E-Series (n/Y): n
```

Check the result and if okay, run the other script to generate data directories and setup permissions on them.

```sh
$ ll certs/
total 36
drwxr-xr-x  9 root root 4096 Apr 26 15:56 ./
drwxr-xr-x 13 root root 4096 Apr 26 15:56 ../
drwxr-xr-x  2 root root 4096 Apr 26 15:56 eseries/
drwxr-xr-x  2 root root 4096 Apr 26 15:58 grafana/
drwxr-xr-x  2 root root 4096 Apr 26 15:58 _master/
drwxr-xr-x  2 root root 4096 Apr 26 15:58 proxy/
drwxr-xr-x  2 root root 4096 Apr 26 15:58 vm/

$ ./scripts/setup-data-dirs.sh
Setting up EPA data directories...
Creating data directories...
Setting Grafana ownership (472:472)...

Verification:
total 16
drwxr-xr-x  4 root root 4096 Apr 26 15:58 .
drwxr-xr-x 14 root root 4096 Apr 26 15:58 ..
drwxr-xr-x  2  472  472 4096 Apr 26 15:58 grafana
drwxr-xr-x  2  472  472 4096 Apr 26 15:58 grafana-dashboards

Setup complete! You can now run:
  docker compose up -d

$ docker compose build
```

You can edit `.env` (that shouldn't be necessary, though) and `docker-compose.yml` (you need to, especially E-Series controller IP(s) and password for the monitor account), before you run `docker compose up -d`.
