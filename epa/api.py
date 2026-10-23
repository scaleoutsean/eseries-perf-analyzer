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