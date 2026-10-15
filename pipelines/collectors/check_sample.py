import httpx


def main():
    url = "https://openapi.foodsafetykorea.go.kr/api/sample/I0490/json/1/5"
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("I0490", {})
        rows = result.get("row", [])
        if not rows:
            raise ValueError("Sample returned no rows")
        print(f"Sample API OK: {len(rows)} rows")
        print("Fields:", ", ".join(sorted(rows[0])))
    except (httpx.HTTPError, ValueError) as exc:
        raise SystemExit(
            f"Sample check failed: {type(exc).__name__}. Check provider availability; no key required."
        ) from None


if __name__ == "__main__":
    main()
