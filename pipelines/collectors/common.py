import time

import httpx


class CollectionError(Exception):
    pass


class ApiClient:
    def __init__(self, client, max_requests=20, interval=1.0, sleep=time.sleep):
        self.client = client
        self.max_requests = max_requests
        self.interval = interval
        self.sleep = sleep
        self.requests = 0
        self.retries = 0
        self.transport_errors = {}

    def get(self, url, **kwargs):
        for attempt in range(3):
            if self.requests >= self.max_requests:
                raise CollectionError("REQUEST_BUDGET_EXCEEDED")
            if self.requests:
                self.sleep(self.interval)
            self.requests += 1
            try:
                response = self.client.get(url, **kwargs)
            except httpx.TransportError as error:
                # Exception messages may contain API keys; retain only fixed error categories.
                category = next(
                    (
                        name
                        for kind, name in (
                            (httpx.ConnectTimeout, "CONNECT_TIMEOUT"),
                            (httpx.ReadTimeout, "READ_TIMEOUT"),
                            (httpx.WriteTimeout, "WRITE_TIMEOUT"),
                            (httpx.PoolTimeout, "POOL_TIMEOUT"),
                            (httpx.ConnectError, "CONNECT_ERROR"),
                            (httpx.RemoteProtocolError, "REMOTE_PROTOCOL_ERROR"),
                            (httpx.ReadError, "READ_ERROR"),
                        )
                        if isinstance(error, kind)
                    ),
                    "TRANSPORT_ERROR",
                )
                self.transport_errors[category] = (
                    self.transport_errors.get(category, 0) + 1
                )
                if attempt == 2:
                    raise CollectionError("NETWORK_ERROR") from None
            else:
                if response.status_code not in (429, 500, 502, 503, 504):
                    if response.status_code != 200:
                        raise CollectionError(f"HTTP_{response.status_code}")
                    try:
                        data = response.json()
                    except ValueError:
                        raise CollectionError("INVALID_JSON") from None
                    if not isinstance(data, dict):
                        raise CollectionError("INVALID_RESPONSE_SHAPE")
                    return data
                if attempt == 2:
                    raise CollectionError(f"HTTP_{response.status_code}")
            self.retries += 1
            self.sleep(2**attempt)
        raise CollectionError("RETRY_EXHAUSTED")


def records(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise CollectionError("INVALID_ROWS")
    return value


def record_id(row, key):
    value = row.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or not str(value).strip()
    ):
        raise CollectionError("MISSING_SOURCE_ID")
    return str(value).strip()
