#!/usr/bin/env python3

###############################################################################
# Synopsis:                                                                   #
# Creates CA and TLS certificates for various services in EPA 4               #
#                                                                             #
# Author: @scaleoutSean (Github)                                              #
# Repository: https://github.com/scaleoutsean/sfc                             #
# License: the Apache License Version 2.0                                     #
###############################################################################

import os
import pathlib
import subprocess
import logging
import re
import ssl
import sys
import ipaddress
import tempfile
import fnmatch
from typing import Tuple

from tomlkit import value

USE_SUDO = False
FORCE_REGENERATE = False


def _ensure_dir(path: pathlib.Path):
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        if not USE_SUDO:
            raise
        subprocess.run(["sudo", "mkdir", "-p", str(path)], check=True)


def _write_bytes_file(path: pathlib.Path, data: bytes, mode: int = None):
    try:
        _ensure_dir(path.parent)
        path.write_bytes(data)
        if mode is not None:
            os.chmod(str(path), mode)
        return
    except PermissionError:
        if not USE_SUDO:
            raise

    _ensure_dir(path.parent)
    subprocess.run(["sudo", "tee", str(path)], input=data, stdout=subprocess.DEVNULL, check=True)
    if mode is not None:
        subprocess.run(["sudo", "chmod", format(mode, "o"), str(path)], check=True)


def _write_text_file(path: pathlib.Path, text: str, mode: int = None):
    _write_bytes_file(path, text.encode("utf-8"), mode=mode)


def _extract_cn_from_subj(subj: str, fallback: str = "localhost") -> str:
    marker = "/CN="
    if marker not in subj:
        return fallback
    return subj.split(marker, 1)[1].strip() or fallback


def _build_server_ext_config(common_name: str, dns_names: list, ip_names: list) -> str:
    lines = [
        "[req]",
        "distinguished_name = req_distinguished_name",
        "x509_extensions = v3_req",
        "prompt = no",
        "",
        "[req_distinguished_name]",
        f"CN = {common_name}",
        "",
        "[v3_req]",
        "basicConstraints = critical,CA:FALSE",
        "keyUsage = critical,digitalSignature,keyEncipherment",
        "extendedKeyUsage = serverAuth",
        "subjectAltName = @alt_names",
        "",
        "[alt_names]",
    ]

    n = 1
    for dns in dns_names:
        lines.append(f"DNS.{n} = {dns}")
        n += 1

    n = 1
    for ip in ip_names:
        lines.append(f"IP.{n} = {ip}")
        n += 1

    return "\n".join(lines) + "\n"

def create_certificates():
    # Create CA certificates under ./certs/_master/
    dest = pathlib.Path("./certs/_master")
    _ensure_dir(dest)

    key_path = dest / "ca.key"
    crt_path = dest / "ca.crt"

    # If they already exist, leave them alone unless forced.
    if key_path.exists() and crt_path.exists() and not FORCE_REGENERATE:
        logging.info("CA key and certificate already exist at %s. Skipping generation.", dest)
        return (key_path, crt_path)

    days = "3650"
    ca_config = dest / "ca_ext.cnf"

    try:
        # Generate private key
        logging.info("Generating CA private key: %s", key_path)
        subprocess.run(["openssl", "genrsa", "-out", str(key_path), "4096"], check=True)

        # OpenSSL 3 expects CA certs to carry proper CA/key usage constraints.
        _write_text_file(ca_config, """
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_ca
prompt = no

[req_distinguished_name]
CN = SFC-CA

[v3_ca]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical,CA:true
keyUsage = critical,keyCertSign,cRLSign
""")

        # Generate self-signed cert
        logging.info("Generating self-signed CA certificate: %s", crt_path)
        subprocess.run([
            "openssl",
            "req",
            "-x509",
            "-new",
            "-nodes",
            "-key",
            str(key_path),
            "-sha256",
            "-days",
            days,
            "-out",
            str(crt_path),
            "-config",
            str(ca_config),
        ], check=True)

        # Reset serial file when CA is regenerated.
        ca_srl = dest / "ca.srl"
        if ca_srl.exists():
            try:
                ca_srl.unlink()
            except OSError:
                pass

        # Restrict permissions on private key
        try:
            os.chmod(str(key_path), 0o600)
        except OSError:
            logging.debug("Failed to chmod private key; continuing.")

        logging.info("Created CA key and certificate at %s", dest)
        return (key_path, crt_path)
    except subprocess.CalledProcessError as e:
        logging.error("OpenSSL command failed: %s", e)
        raise


def gen_sign_csr(dest: pathlib.Path, base_name: str, subj: str, days: str = "3650") -> Tuple[pathlib.Path, pathlib.Path]:
    """Generate a private key, CSR and sign it with the master CA.

    Returns (key_path, cert_path).
    If both key and cert already exist, the function will skip generation and return them.
    """
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    # Ensure CA exists
    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    _ensure_dir(dest)

    key_path = dest / f"{base_name}.key"
    csr_path = dest / f"{base_name}.csr"
    cert_path = dest / f"{base_name}.crt"

    # If already present, skip unless forced.
    if key_path.exists() and cert_path.exists() and not FORCE_REGENERATE:
        logging.info("%s TLS key and certificate already exist. Skipping generation.", base_name)
        return (key_path, cert_path)

    # Generate key and CSR, then sign with CA    
    logging.info("Generating %s private key...", base_name)
    subprocess.run(["openssl", "genrsa", "-out", str(key_path), "4096"], check=True)

    common_name = _extract_cn_from_subj(subj, fallback=base_name)
    dns_names = [common_name]
    ip_names = []

    if base_name in ("influxdb", "s3", "grafana", "explorer", "vm"):
        dns_names = [base_name, "localhost"]
        ip_names = ["127.0.0.1"]

    san_config = dest / f"{base_name}_san.cnf"
    _write_text_file(san_config, _build_server_ext_config(common_name, dns_names, ip_names))

    logging.info("Generating %s CSR with SAN extensions...", base_name)
    subprocess.run([
        "openssl", "req", "-new", "-key", str(key_path), "-out", str(csr_path), "-config", str(san_config)
    ], check=True)

    logging.info("Signing %s certificate with CA and SAN extensions...", base_name)
    subprocess.run([
        "openssl", "x509", "-req", "-in", str(csr_path), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(cert_path), "-days", days, "-sha256", "-extensions", "v3_req", "-extfile", str(san_config)
    ], check=True)

    try:
        san_config.unlink()
    except Exception:
        pass

    # Restrict permissions on private key
    try:
        os.chmod(str(key_path), 0o600)
    except OSError:
        logging.debug("Failed to chmod %s private key; continuing.", base_name)

    # Copy CA public cert (binary-safe)
    _write_bytes_file(dest / "ca.crt", ca_crt.read_bytes())

    # Clean up CSR
    try:
        csr_path.unlink()
    except OSError:
        pass

    return (key_path, cert_path)

def create_vm_config():
    # Create Victoria Metrics CSR, sign it with CA key, copy to ./certs/vm
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    # Ensure CA exists
    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    dest = pathlib.Path("./certs/vm")
    key_path, cert_path = gen_sign_csr(dest, "vm", "/CN=vm")

    # Write a tiny example TLS config file for convenience
    conf_path = dest / "vm_tls.conf"
    conf_text = (
        "# Minimal Victoria Metrics TLS configuration (example)\n"
        "tls_enabled = true\n"
        f"tls_cert_file = {str(cert_path)}\n"
        f"tls_key_file = {str(key_path)}\n"
        f"tls_ca_file = {str(dest / 'ca.crt')}\n"
    )
    _write_text_file(conf_path, conf_text)

    logging.info("Victoria Metrics TLS material created at %s", str(dest))
    return (key_path, cert_path)

def create_s3_config():
    # Create S3 Gateway CSR, sign it with CA key, copy to ./certs/s3
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    dest = pathlib.Path("./certs/s3")
    key_path, cert_path = gen_sign_csr(dest, "s3", "/CN=s3")

    conf_path = dest / "s3_tls.conf"
    conf_text = (
        "# Minimal S3 TLS configuration (example)\n"
        f"tls_cert = {str(cert_path)}\n"
        f"tls_key = {str(key_path)}\n"
        f"tls_ca = {str(dest / 'ca.crt')}\n"
    )
    _write_text_file(conf_path, conf_text)

    logging.info("S3 TLS material created at %s", str(dest))
    return (key_path, cert_path)

def create_grafana_config():
    # Create Grafana CSR, sign it with CA key, copy to ./certs/grafana
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    dest = pathlib.Path("./certs/grafana")
    key_path, cert_path = gen_sign_csr(dest, "grafana", "/CN=grafana")

    conf_path = dest / "grafana_tls.conf"
    conf_text = (
        "# Minimal Grafana TLS configuration (example)\n"
        f"cert_file = {str(cert_path)}\n"
        f"cert_key = {str(key_path)}\n"
        f"ca_file = {str(dest / 'ca.crt')}\n"
    )
    _write_text_file(conf_path, conf_text)

    try:
        os.chown(str(key_path), 472, 472)
        os.chown(str(cert_path), 472, 472)
        os.chown(str(conf_path), 472, 472)
    except PermissionError:
        if USE_SUDO:
            subprocess.run(["sudo", "chown", "472:472", str(key_path), str(cert_path), str(conf_path)], check=True)
        else:
            logging.warning("Could not set 472:472 ownership on Grafana certs (requires sudo).")
            logging.warning("Grafana may fail to load certs. Run manually: sudo chown 472:472 ./certs/grafana/grafana*")

    logging.info("Grafana TLS material created at %s", str(dest))
    return (key_path, cert_path)


def copy_ca_to_all():
    # Copies CA public key to all services
    src = pathlib.Path("./certs/_master/ca.crt")
    for service in ["s3", "vm", "grafana", "sfc", "utils"]:
        dst = pathlib.Path(f"./certs/{service}/ca.crt")
        _ensure_dir(dst.parent)
        _write_bytes_file(dst, src.read_bytes())
    return


def _parse_eseries_controller_and_port(user_input: list) -> Tuple[str, int]:
    # Input may be single host or comma-separated list of two hosts; regardless, create a list of of one or two items.
    values = [v.strip() for v in user_input if v.strip()]
    if not values:
        raise ValueError("E-Series controller input is empty after parsing")

    # loop over items and return the first valid host:port pair we can parse; if multiple are provided, log a warning.
    
    for value in values:
        # Accept inputs like:
        # - 192.168.1.34,192.168.1.35
        # - c1.example.local, c1.example.local:8443
        # - 192.168.1.34:8443,192.168.1.35:8444
        # - https://ca.example.local:8443,https://cb.example.local:8444
        
        if "://" in value:
            from urllib.parse import urlparse
            parsed = urlparse(value)
            if not parsed.hostname:
                raise ValueError(f"Could not parse host from input: {user_input}")
            host = parsed.hostname
            port = parsed.port or 8443
            return host, port

        if value.count(":") == 1 and not value.startswith("["):
            host_part, port_part = value.split(":", 1)
            if host_part and port_part.isdigit():
                host = host_part.strip()
                port = int(port_part.strip())
                return host, port
        # accept bare hostnames or IPs without port; default to 8443
        

    return value, 8443


def _safe_cert_filename(host: str) -> str:
    # Keep cert filenames portable and predictable.
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", host.strip())
    return safe or "eseries"


def _extract_san_entries_from_pem(pem_data: str) -> Tuple[list, list]:
    """Return (dns_names, ip_names) parsed from certificate SAN."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".crt", delete=False, encoding="utf-8") as tmp:
        tmp.write(pem_data)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["openssl", "x509", "-in", tmp_path, "-noout", "-ext", "subjectAltName"],
            check=True,
            capture_output=True,
            text=True,
        )
        output = result.stdout
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    dns_names = []
    ip_names = []
    # Example line: DNS:influxdb, DNS:localhost, IP Address:127.0.0.1
    for line in output.splitlines():
        parts = [p.strip() for p in line.split(",")]
        for part in parts:
            if part.startswith("DNS:"):
                dns_names.append(part[len("DNS:"):].strip())
            elif part.startswith("IP Address:"):
                ip_names.append(part[len("IP Address:"):].strip())

    return dns_names, ip_names


def _host_matches_san(host: str, dns_names: list, ip_names: list) -> bool:
    host = host.strip()
    if not host:
        return False

    try:
        host_ip = ipaddress.ip_address(host)
        normalized_ips = set()
        for ip in ip_names:
            try:
                normalized_ips.add(str(ipaddress.ip_address(ip)))
            except ValueError:
                continue
        return str(host_ip) in normalized_ips
    except ValueError:
        pass

    host_l = host.lower()
    for dns in dns_names:
        dns_l = dns.lower()
        if dns_l == host_l:
            return True
        if "*" in dns_l and fnmatch.fnmatch(host_l, dns_l):
            return True
    return False


def maybe_download_eseries_certificate(download_mode: str = "auto", eseries_controller: str = ""):
    """Optionally download E-Series endpoint certificate and store it for Collector trust use.

    Stores cert(s) in:
    - ./certs/eseries/<fqdn-or-ip>.crt (reference archive)
    - ./eseries/certs/<fqdn-or-ip>.crt (picked up during collector image build)
    - ./eseries/certs/eseries_ca.crt (stable E-Series filename)
    - ./certs/eseries/eseries_ca.crt (runtime volume-mount path used by compose)
    """
    mode = (download_mode or "auto").strip().lower()

    if mode not in ("auto", "yes", "no"):
        logging.warning("Invalid --download-eseries-cert value '%s'. Using 'auto'.", download_mode)
        mode = "auto"

    if mode == "no":
        logging.info("Skipped E-Series certificate download (--download-eseries-cert=no).")
        return

    # endpoint may be a comma-separated list of two controllers; if two are provided loop over both and save certs to different files with hostnames in the name; if one is provided, use it for all.   
    # create endpoint_list from single item or comma-separated two items; strip whitespace and ignore empty items.
    endpoint_list = []
    if eseries_controller:
        for item in str(eseries_controller).split(","):
            item = item.strip()
            if item:
                endpoint_list.append(item)

    if not endpoint_list:
        if mode == "yes":
            if not sys.stdin.isatty():
                logging.warning("--download-eseries-cert=yes set without --eseries-controllers in non-interactive mode; skipping download.")
                return
            user_input = input("E-Series host or URL (example: 192.168.1.34 or https://sf.example.local:443): ").strip()
        else:
            if not sys.stdin.isatty():
                logging.info("Non-interactive session detected. Skipping optional E-Series cert download.")
                return
            answer = input("Do you want to download certificate from E-Series (n/Y): ").strip().lower()
            if answer in ("n", "no"):
                logging.info("Skipped E-Series certificate download by user choice.")
                return
            user_input = input("E-Series host or URL (example: 192.168.1.34 or https://sf.example.local:443): ").strip()

        for item in user_input.split(","):
            item = item.strip()
            if item:
                endpoint_list.append(item)

    if not endpoint_list:
        logging.warning("No E-Series host provided. Skipping E-Series certificate download.")
        return

    # loop over endpoint_list and process each; if empty, prompt user if in interactive mode, otherwise skip.
    for endpoint in endpoint_list:
        try:
            host, port = _parse_eseries_controller_and_port([endpoint])
            pem_data = ssl.get_server_certificate((host, port))
        except Exception as exc:
            logging.error("Failed to download E-Series certificate from %s: %s", endpoint, exc)
            continue

        try:
            dns_names, ip_names = _extract_san_entries_from_pem(pem_data)
            if not _host_matches_san(host, dns_names, ip_names):
                logging.warning(
                    "Downloaded E-Series certificate SAN does not include requested host '%s'. "
                    "TLS hostname verification will fail unless you use a matching DNS name or disable verification.",
                    host,
                )
                if dns_names or ip_names:
                    logging.warning("Certificate SAN entries: DNS=%s IP=%s", dns_names, ip_names)
        except Exception as exc:
            logging.warning("Could not inspect SAN entries in downloaded E-Series certificate: %s", exc)

        cert_name = _safe_cert_filename(host) + ".crt"

        certs_eseries_dir = pathlib.Path("./certs/eseries")
        _ensure_dir(certs_eseries_dir)
        eseries_cert_path = certs_eseries_dir / cert_name
        _write_text_file(eseries_cert_path, pem_data)

        # Keep E-Series build context trust files in sync.
        build_certs_dir = pathlib.Path("./eseries/certs")
        _ensure_dir(build_certs_dir)
        _write_text_file(build_certs_dir / cert_name, pem_data)
        _write_text_file(build_certs_dir / "eseries_ca.crt", pem_data)

        # Keep compose runtime mount path in sync.
        runtime_certs_dir = pathlib.Path("./certs/eseries")
        _ensure_dir(runtime_certs_dir)
        _write_text_file(runtime_certs_dir / "eseries_ca.crt", pem_data)

        logging.info("Saved E-Series certificate(s) to %s", eseries_cert_path)
        logging.info("Synced E-Series trust cert to ./certs/eseries_ca.crt and ./eseries/certs/eseries_ca.crt")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate CA and per-service TLS certificates.")
    parser.add_argument("--service", choices=["all", "grafana", "eseries", "ca", "vm", "s3"], default="all", help="Which certs to generate")
    parser.add_argument(
        "--download-eseries-cert",
        choices=["auto", "yes", "no"],
        default="auto",
        help="Download E-Series endpoint cert: auto=interactive prompt, yes=force download, no=skip.")
    parser.add_argument(
        "--eseries-controllers",
        default="",
        help="E-Series controller(s) or management URLs for certificate download (e.g. s194,s195 or https://controller.example.local:9443). Comma-separated if two.")
    parser.add_argument(
        "--use-sudo",
        action="store_true",
        help="Use sudo fallback for file writes when permission errors occur.")
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Regenerate certificates even if they already exist (recommended after CA extension changes).")
    args = parser.parse_args()

    USE_SUDO = args.use_sudo
    FORCE_REGENERATE = args.force_regenerate

    if args.service == "ca":
        create_certificates()
    elif args.service == "eseries":
        # E-Series trust cert bootstrap only; avoids touching other service directories.
        pass
    elif args.service == "vm":
        create_vm_config()
        copy_ca_to_all()
    elif args.service == "grafana":
        create_grafana_config()
        copy_ca_to_all()
    elif args.service == "s3":
        create_s3_config()
        copy_ca_to_all()        
    else:
        create_certificates()
        create_grafana_config()
        create_vm_config()
        create_s3_config()
        copy_ca_to_all()

    # Optional E-Series trust certificate bootstrap for SFC.
    maybe_download_eseries_certificate(args.download_eseries_cert, args.eseries_controllers)
