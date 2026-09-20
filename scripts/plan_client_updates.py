#!/usr/bin/env python3
"""Prepare per-client Compose overrides; never contact or mutate deployments."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.branding import load_brand_profile  # noqa: E402
from scripts.release_preflight import SERVICE_ROLES, load_manifest  # noqa: E402


def plan_updates(manifest_path: Path, fleet_path: Path, output: Path) -> dict:
    manifest = load_manifest(manifest_path)
    fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
    if set(fleet) != {"schema_version", "clients"} or fleet["schema_version"] != 1 or not fleet["clients"]:
        raise ValueError("Fleet requires schema_version 1 and at least one client")
    prepared = {}
    clients = []
    for client in fleet["clients"]:
        if set(client) != {"id", "profile", "assets", "services"}:
            raise ValueError("Client requires id, profile, assets and services")
        name = client["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name) or name in prepared:
            raise ValueError("Client IDs must be unique lowercase slugs")
        profile_path = (fleet_path.parent / client["profile"]).resolve()
        assets = (fleet_path.parent / client["assets"]).resolve()
        profile = load_brand_profile(str(profile_path))
        if not assets.is_dir():
            raise ValueError("Client asset directory is missing")
        for url in (profile.logo_url, profile.favicon_url, profile.social_image_url):
            if url.startswith("/branding/"):
                asset = (assets / url.removeprefix("/branding/")).resolve()
                if not asset.is_relative_to(assets) or not asset.is_file():
                    raise ValueError("Client brand asset is missing or outside the asset directory")
        selected = client["services"]
        if not isinstance(selected, list) or not {"api", "frontend", "migrations"}.issubset(selected):
            raise ValueError("Client services must include api, frontend and migrations")
        if len(set(selected)) != len(selected) or set(selected) - set(SERVICE_ROLES):
            raise ValueError("Client services contain unknown or duplicate services")
        services = {}
        for service in selected:
            role = SERVICE_ROLES[service]
            entry: dict = {"image": manifest["images"][role]}
            if role in {"api", "ingest-cuda", "ml-cuda"}:
                entry["environment"] = {"SITE_PROFILE_PATH": "/etc/transcript-archive/brand.json"}
                entry["volumes"] = [
                    {
                        "type": "bind",
                        "source": str(profile_path),
                        "target": "/etc/transcript-archive/brand.json",
                        "read_only": True,
                        "bind": {"create_host_path": False},
                    }
                ]
            elif role == "frontend":
                entry["volumes"] = [
                    {
                        "type": "bind",
                        "source": str(assets),
                        "target": "/usr/share/nginx/html/branding",
                        "read_only": True,
                        "bind": {"create_host_path": False},
                    }
                ]
            services[service] = entry
        prepared[name] = {"services": services}
        clients.append(
            {
                "id": name,
                "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                "compose": f"{name}.compose.json",
                "services": selected,
            }
        )
    result = {
        "schema_version": 1,
        "source_commit": manifest["source_commit"],
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "clients": clients,
    }
    # Validate the entire fleet first. Never overwrite an earlier plan or client configuration.
    output.mkdir(parents=True, exist_ok=False)
    for name, compose in prepared.items():
        (output / f"{name}.compose.json").write_text(json.dumps(compose, indent=2) + "\n", encoding="utf-8")
    (output / "plan.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--fleet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    plan = plan_updates(args.manifest, args.fleet, args.output)
    print(f"Prepared {len(plan['clients'])} client updates at {plan['source_commit']}; no deployments changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
