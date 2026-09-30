"""Цели Prometheus указывают на сервисы, которые есть в docker compose.

Цель ``redis-exporter:9121`` не резолвилась: сервис называется
``redis_exporter``, и таргет Redis всегда был down.
"""

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
PROMETHEUS = REPO / "configs" / "metrics" / "prometheus.yml"
COMPOSE_FILES = ["docker-compose.yml", "docker-compose.tun2socks.yml"]


def _targets() -> list[tuple[str, str]]:
    config = yaml.safe_load(PROMETHEUS.read_text(encoding="utf-8"))
    return [
        (job["job_name"], target)
        for job in config["scrape_configs"]
        for static in job.get("static_configs", [])
        for target in static["targets"]
    ]


def _monitoring_hosts(compose_file: str) -> dict[str, set[str]]:
    """Имя в сети monitoring (сервис или container_name) -> открытые порты."""
    services = yaml.safe_load((REPO / compose_file).read_text(encoding="utf-8"))["services"]
    hosts: dict[str, set[str]] = {}
    for name, service in services.items():
        if "monitoring" not in (service.get("networks") or []):
            continue
        ports = {str(port) for port in service.get("expose") or []}
        for host in (name, service.get("container_name")):
            if host:
                hosts[host] = ports
    return hosts


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
@pytest.mark.parametrize(("job", "target"), _targets())
def test_target_is_a_service_on_the_monitoring_network(compose_file, job, target):
    host, port = target.rsplit(":", 1)
    if host == "localhost":
        return
    hosts = _monitoring_hosts(compose_file)

    assert host in hosts, f"{job}: {host} is not a service on the monitoring network in {compose_file}"
    # Бот слушает 8080 без expose: порт внутри сети доступен и так.
    if hosts[host]:
        assert port in hosts[host], f"{job}: {host} does not expose {port} in {compose_file}"
