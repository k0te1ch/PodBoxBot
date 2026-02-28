import json
import os
import time
from pathlib import Path

import requests

SCHEMA_DIR = Path("/app/shared/schemas")
REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
POLL_INTERVAL = 5  # секунд


def wait_for_registry(url, retries=10, delay=3):
    for _ in range(retries):
        try:
            r = requests.get(f"{url}/subjects")
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(delay)
    raise RuntimeError("Schema Registry not available")


def register_schema(file_path: Path):
    subject = f"{file_path.stem}-value"
    with open(file_path) as f:
        schema_str = json.dumps(json.load(f))

    r = requests.post(
        f"{REGISTRY_URL}/subjects/{subject}/versions",
        headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
        json={"schema": schema_str},
    )

    if r.status_code in (200, 201):
        print(f"✅ Registered schema: {subject}")
    elif "already exists" in r.text:
        print(f"ℹ Schema already exists: {subject}")
    else:
        print(f"❌ Failed to register {subject}: {r.status_code} {r.text}")


def main():
    wait_for_registry(REGISTRY_URL)
    seen = set()
    while True:
        for f in SCHEMA_DIR.glob("*.avsc"):
            if f not in seen:
                register_schema(f)
                seen.add(f)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
