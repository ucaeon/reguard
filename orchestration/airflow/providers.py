"""Provider budgets and successful-response caching."""

from datetime import datetime
import hashlib
import json
import time
import httpx
from pipelines.collectors.common import ApiClient, CollectionError
from .state import atomic_json, state_db
from .state import KST


def reserve_request(provider, service, incremental, now=None):
    now = now or datetime.now(KST)
    timestamp = now.timestamp()
    with state_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        hourly = connection.execute(
            "SELECT count(*) FROM requests WHERE provider=? AND service=? AND at>?",
            (provider, service, timestamp - 3600),
        ).fetchone()[0]
        if provider == "food":
            nonincremental = connection.execute(
                "SELECT count(*) FROM requests WHERE provider=? AND at>? AND incremental=0",
                (provider, timestamp - 3600),
            ).fetchone()[0]
            start = now.replace(hour=6, minute=0, second=0, microsecond=0).timestamp()
            daily = connection.execute(
                "SELECT count(*) FROM requests WHERE provider=? AND service=? AND at>=?",
                (provider, service, start),
            ).fetchone()[0]
            if (
                not incremental
                and nonincremental >= 90
                or 6 <= now.hour < 19
                and daily >= 280
            ):
                raise CollectionError("LOCAL_REQUEST_BUDGET")
        elif hourly >= 900:
            raise CollectionError("LOCAL_REQUEST_BUDGET")
        connection.execute(
            "INSERT INTO requests VALUES (?,?,?,?)",
            (provider, service, timestamp, int(incremental)),
        )
        connection.execute("DELETE FROM requests WHERE at<?", (timestamp - 8 * 86400,))


def reserve_snapshot_request(service):
    with state_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        used = connection.execute(
            "SELECT count(*) FROM requests WHERE provider='food-file' AND service=? AND at>?",
            (service, now - 86400),
        ).fetchone()[0]
        if used >= 9:
            raise CollectionError("SNAPSHOT_DAILY_BUDGET")
        connection.execute(
            "INSERT INTO requests VALUES ('food-file',?,?,0)", (service, now)
        )


class BudgetClient(httpx.Client):
    def __init__(self, source, incremental, **kwargs):
        super().__init__(timeout=30, follow_redirects=False, **kwargs)
        self.source = source
        self.incremental = incremental

    def get(self, url, **kwargs):
        reserve_request(
            "food" if self.source.startswith("food-") else "safety",
            self.source,
            self.incremental,
        )
        return super().get(url, **kwargs)


class CachedApi(ApiClient):
    def __init__(self, client, folder):
        super().__init__(client, max_requests=3000, interval=1.0)
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def get_fresh(self, url, **kwargs):
        return super().get(url, **kwargs)

    def get(self, url, **kwargs):
        identity = json.dumps([url, kwargs.get("params", {})], sort_keys=True)
        path = self.folder / (hashlib.sha256(identity.encode()).hexdigest() + ".json")
        if path.exists():
            return json.loads(path.read_text())
        data = super().get(url, **kwargs)
        code = str(data.get("resultCode", ""))
        food = data.get("RESULT", {})
        for value in data.values():
            if isinstance(value, dict) and "RESULT" in value:
                food = value["RESULT"]
        if code in {"2000", "2004"} or food.get("CODE") in {"INFO-000", "INFO-200"}:
            atomic_json(path, data)
        return data
