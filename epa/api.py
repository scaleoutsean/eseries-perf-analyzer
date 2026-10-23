import requests


def get_json(session, url, **kwargs):
    """Fetch JSON without disguising HTTP failures as empty payloads."""
    kwargs.setdefault("timeout", (6.10, 15))
    response = session.get(url, **kwargs)
    response.raise_for_status()
    if not 200 <= response.status_code < 300:
        raise requests.exceptions.HTTPError(
            f"Unexpected HTTP status {response.status_code} for {url}",
            response=response,
        )
    return response.json()


def get_drive_statistics(session, system_url, statistics_fetch_time=300):
    """Read every analyzed page, retaining the newest row per drive."""
    return get_analyzed_statistics(
        session, f"{system_url}/analyzed/drive-statistics", ("diskId",),
        statistics_fetch_time=statistics_fetch_time,
        legacy_url=f"{system_url}/analysed-drive-statistics",
    )


def get_analyzed_statistics(session, url, identity_keys, statistics_fetch_time=300, legacy_url=None):
    """Read newest-first history once per object, across all single-use pages."""
    params = {"statisticsFetchTime": statistics_fetch_time}
    newest = {}
    seen_tokens = set()
    for page_index in range(1000):
        try:
            payload = get_json(session, url, params=params)
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if legacy_url is None or page_index != 0 or status not in (404, 405):
                raise
            payload = get_json(session, legacy_url)
            if not isinstance(payload, list) or any(
                not isinstance(row, dict) or any(
                    not isinstance(row.get(key), str) or not row[key] for key in identity_keys
                ) for row in payload
            ):
                raise ValueError("Expected legacy statistics rows with object identities")
            return payload

        if not isinstance(payload, dict) or not isinstance(payload.get("statistics"), list):
            raise ValueError("Expected paged analyzed statistics with a statistics list")
        for row in payload["statistics"]:
            if not isinstance(row, dict) or any(
                not isinstance(row.get(key), str) or not row[key] for key in identity_keys
            ):
                raise ValueError("Expected analyzed statistics rows with object identities")
            newest.setdefault(tuple(row[key] for key in identity_keys), row)
        if "tokenId" not in payload:
            raise ValueError("Missing analyzed statistics pagination token")
        token = payload["tokenId"]
        if token is None:
            return list(newest.values())
        if not isinstance(token, str) or not token or token in seen_tokens:
            raise ValueError("Invalid or repeated analyzed statistics pagination token")
        seen_tokens.add(token)
        params = {"statisticsFetchTime": statistics_fetch_time, "token-id": token}
    raise ValueError("Analyzed statistics pagination exceeded 1000 pages")