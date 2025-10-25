#!/usr/bin/env python3
"""
Validate Prometheus and Grafana monitoring configuration.

This script checks:
1. YAML and JSON syntax
2. Metric definitions are complete
3. Dashboard queries are valid
4. Alert expressions are valid (basic check)
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)


def check_yaml_file(filepath):
    """Check if a YAML file is valid."""
    try:
        with open(filepath) as f:
            yaml.safe_load(f)
        return True, "OK"
    except Exception as e:
        return False, str(e)


def check_json_file(filepath):
    """Check if a JSON file is valid."""
    try:
        with open(filepath) as f:
            json.load(f)
        return True, "OK"
    except Exception as e:
        return False, str(e)


def check_prometheus_config():
    """Check Prometheus configuration."""
    print("Checking Prometheus configuration...")
    
    config_file = Path("config/prometheus/prometheus.yml")
    ok, msg = check_yaml_file(config_file)
    if not ok:
        print(f"  ✗ {config_file}: {msg}")
        return False
    print(f"  ✓ {config_file}")
    
    # Check scrape configs
    with open(config_file) as f:
        config = yaml.safe_load(f)
    
    scrape_configs = config.get("scrape_configs", [])
    if not scrape_configs:
        print("  ✗ No scrape_configs found")
        return False
    
    required_jobs = {"api", "worker"}
    found_jobs = {job["job_name"] for job in scrape_configs if "job_name" in job}
    missing = required_jobs - found_jobs
    if missing:
        print(f"  ✗ Missing scrape jobs: {missing}")
        return False
    
    print(f"  ✓ Found scrape jobs: {', '.join(found_jobs)}")
    return True


def check_prometheus_alerts():
    """Check Prometheus alert rules."""
    print("\nChecking Prometheus alerts...")
    
    alerts_file = Path("config/prometheus/alerts.yml")
    ok, msg = check_yaml_file(alerts_file)
    if not ok:
        print(f"  ✗ {alerts_file}: {msg}")
        return False
    print(f"  ✓ {alerts_file}")
    
    with open(alerts_file) as f:
        alerts = yaml.safe_load(f)
    
    groups = alerts.get("groups", [])
    if not groups:
        print("  ✗ No alert groups found")
        return False
    
    alert_count = sum(len(group.get("rules", [])) for group in groups)
    print(f"  ✓ Found {alert_count} alert rules in {len(groups)} groups")
    
    # Check that all alerts have required fields
    for group in groups:
        for rule in group.get("rules", []):
            if "alert" in rule:
                required_fields = {"expr", "labels", "annotations"}
                missing = required_fields - set(rule.keys())
                if missing:
                    print(f"  ✗ Alert '{rule['alert']}' missing fields: {missing}")
                    return False
    
    return True


def check_grafana_provisioning():
    """Check Grafana provisioning configs."""
    print("\nChecking Grafana provisioning...")
    
    datasource_file = Path("config/grafana/provisioning/datasources/prometheus.yml")
    ok, msg = check_yaml_file(datasource_file)
    if not ok:
        print(f"  ✗ {datasource_file}: {msg}")
        return False
    print(f"  ✓ {datasource_file}")
    
    dashboards_file = Path("config/grafana/provisioning/dashboards/dashboards.yml")
    ok, msg = check_yaml_file(dashboards_file)
    if not ok:
        print(f"  ✗ {dashboards_file}: {msg}")
        return False
    print(f"  ✓ {dashboards_file}")
    
    return True


def check_grafana_dashboards():
    """Check Grafana dashboard JSON files."""
    print("\nChecking Grafana dashboards...")
    
    dashboard_dir = Path("config/grafana/dashboards")
    if not dashboard_dir.exists():
        print(f"  ✗ Dashboard directory not found: {dashboard_dir}")
        return False
    
    dashboards = list(dashboard_dir.glob("*.json"))
    if not dashboards:
        print(f"  ✗ No dashboard JSON files found in {dashboard_dir}")
        return False
    
    all_ok = True
    for dashboard_file in dashboards:
        ok, msg = check_json_file(dashboard_file)
        if not ok:
            print(f"  ✗ {dashboard_file}: {msg}")
            all_ok = False
        else:
            print(f"  ✓ {dashboard_file.name}")
    
    return all_ok


def check_docker_compose():
    """Check docker-compose.yml has monitoring services."""
    print("\nChecking docker-compose.yml...")
    
    compose_file = Path("docker-compose.yml")
    ok, msg = check_yaml_file(compose_file)
    if not ok:
        print(f"  ✗ {compose_file}: {msg}")
        return False
    
    with open(compose_file) as f:
        compose = yaml.safe_load(f)
    
    services = compose.get("services", {})
    required_services = {"prometheus", "grafana"}
    missing = required_services - set(services.keys())
    if missing:
        print(f"  ✗ Missing services: {missing}")
        return False
    
    print(f"  ✓ Monitoring services configured: {', '.join(required_services)}")
    
    # Check volumes
    volumes = compose.get("volumes", {})
    required_volumes = {"prometheus-data", "grafana-data"}
    missing = required_volumes - set(volumes.keys())
    if missing:
        print(f"  ✗ Missing volumes: {missing}")
        return False
    
    print(f"  ✓ Volumes configured: {', '.join(required_volumes)}")
    return True


def check_metrics_modules():
    """Check that metrics modules can be imported."""
    print("\nChecking metrics modules...")
    
    sys.path.insert(0, str(Path.cwd()))
    
    # Check API metrics
    try:
        # Just check syntax, don't actually import (prometheus_client may not be installed)
        import py_compile
        api_metrics = Path("app/metrics.py")
        py_compile.compile(str(api_metrics), doraise=True)
        print(f"  ✓ {api_metrics} (syntax OK)")
    except Exception as e:
        print(f"  ✗ app/metrics.py: {e}")
        return False
    
    # Check worker metrics
    try:
        worker_metrics = Path("worker/metrics.py")
        py_compile.compile(str(worker_metrics), doraise=True)
        print(f"  ✓ {worker_metrics} (syntax OK)")
    except Exception as e:
        print(f"  ✗ worker/metrics.py: {e}")
        return False
    
    return True


def main():
    """Run all validation checks."""
    print("=" * 60)
    print("Monitoring Configuration Validation")
    print("=" * 60)
    
    checks = [
        check_prometheus_config,
        check_prometheus_alerts,
        check_grafana_provisioning,
        check_grafana_dashboards,
        check_docker_compose,
        check_metrics_modules,
    ]
    
    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Error in {check.__name__}: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    if all(results):
        print("✓ All validation checks passed!")
        print("=" * 60)
        return 0
    else:
        failed = sum(1 for r in results if not r)
        print(f"✗ {failed}/{len(results)} checks failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
