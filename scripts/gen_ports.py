#!/usr/bin/env python3
"""Generate a .env file with random free host ports for docker-compose.

Writes keys:
DB_HOST_PORT, REDIS_HOST_PORT, API_HOST_PORT, PROMETHEUS_HOST_PORT,
GRAFANA_HOST_PORT, OPENSEARCH_HOST_PORT, DASHBOARDS_HOST_PORT
"""
import socket
from pathlib import Path

def free_port():
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", 0))
    p = s.getsockname()[1]
    s.close()
    return p

def main():
    keys = [
        'DB_HOST_PORT',
        'REDIS_HOST_PORT',
        'API_HOST_PORT',
        'PROMETHEUS_HOST_PORT',
        'GRAFANA_HOST_PORT',
        'OPENSEARCH_HOST_PORT',
        'DASHBOARDS_HOST_PORT',
    ]
    ports = {}
    used = set()
    for k in keys:
        p = free_port()
        while p in used:
            p = free_port()
        used.add(p)
        ports[k] = p

    out = Path('.env')

    # If .env exists, back it up and preserve non-port keys.
    if out.exists():
        stamp = __import__('datetime').datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        backup = out.with_name(f".env.bak.{stamp}")
        out.replace(backup)
        print(f"Existing .env backed up to {backup}")
        # read backed-up content to preserve other keys
        existing = {}
        try:
            for line in backup.read_text().splitlines():
                if not line or line.strip().startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                existing[k.strip()] = v.strip()
        except Exception:
            existing = {}
    else:
        existing = {}

    # Merge: keep existing values for our keys if present; otherwise use generated
    merged = {}
    used_values = set(existing.values())
    for k in keys:
        if k in existing and existing[k]:
            merged[k] = existing[k]
            used_values.add(int(existing[k]) if existing[k].isdigit() else existing[k])
        else:
            p = free_port()
            while p in used_values:
                p = free_port()
            merged[k] = str(p)
            used_values.add(p)

    # Write a new .env preserving other existing non-port lines
    with out.open('w') as f:
        f.write('# Generated .env - port assignments\n')
        # write back any existing non-port keys
        for k, v in existing.items():
            if k not in keys:
                f.write(f"{k}={v}\n")
        # now write merged port keys
        for k in keys:
            f.write(f"{k}={merged[k]}\n")

    # echo results
    for k, v in merged.items():
        print(f"{k}={v}")

if __name__ == '__main__':
    main()
