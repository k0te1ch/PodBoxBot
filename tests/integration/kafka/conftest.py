import os

import pytest

KAFKA_BOOTSTRAP = os.getenv("KAFKA_E2E_BOOTSTRAP", "")
SCHEMA_REGISTRY_URL = os.getenv("KAFKA_E2E_SCHEMA_REGISTRY", "http://localhost:8081")


@pytest.fixture(scope="session")
def kafka_stack() -> tuple[str, str]:
    if not KAFKA_BOOTSTRAP:
        pytest.skip("KAFKA_E2E_BOOTSTRAP not set; start tests/integration/kafka/docker-compose.yml")
    return KAFKA_BOOTSTRAP, SCHEMA_REGISTRY_URL
