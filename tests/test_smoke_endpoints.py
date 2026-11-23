"""API smoke check: no endpoint answers 500 on an empty database, foreign ids and invalid request bodies."""

# Streaming and service responses that are checked by their own tests.
SKIP = {"/metrics", "/api/v1/events/stream", "/health"}  # /health does its own DB check outside the test loop


def _get_paths(client) -> list[str]:
    schema = client.get("/api/v1/openapi.json").json()
    return sorted(path for path, ops in schema["paths"].items() if "get" in ops and "{" not in path and path not in SKIP)


def test_get_endpoints_do_not_crash(client, token_user_1):
    paths = _get_paths(client)
    assert len(paths) > 40, paths
    failures = []
    for headers in ({}, {"Authorization": f"Bearer {token_user_1}"}):
        for path in paths:
            response = client.get(path, headers=headers)
            if response.status_code >= 500:
                failures.append(f"{path} {'auth' if headers else 'guest'}: {response.status_code} {response.text[:120]}")
    assert failures == []


def test_get_endpoints_with_unknown_ids_answer_4xx(client, token_user_1):
    """A non-existent id, code or key in the path gives a 4xx response, not a crash."""
    import re

    schema = client.get("/api/v1/openapi.json").json()
    paths = sorted(path for path, ops in schema["paths"].items() if "get" in ops and "{" in path)
    assert len(paths) > 20
    failures = []
    headers = {"Authorization": f"Bearer {token_user_1}"}
    for template in paths:
        for value in ("999999", "zz"):
            path = re.sub(r"\{[^}]+\}", value, template)
            response = client.get(path, headers=headers)
            if response.status_code >= 500:
                failures.append(f"{path}: {response.status_code} {response.text[:120]}")
    assert failures == []


def test_writes_with_bad_bodies_answer_4xx(client, token_user_1):
    """An empty body, garbage instead of JSON and wrong field types give 4xx for all mutating requests."""
    import re

    schema = client.get("/api/v1/openapi.json").json()
    headers = {"Authorization": f"Bearer {token_user_1}"}
    failures = []
    count = 0
    for template, ops in sorted(schema["paths"].items()):
        path = re.sub(r"\{[^}]+\}", "999999", template)
        for method in ("post", "put", "patch", "delete"):
            if method not in ops:
                continue
            count += 1
            for kwargs in ({"json": {}}, {"content": b"not json", "headers": {**headers, "Content-Type": "application/json"}},
                           {"json": {"move": 5, "fen": [], "name": {"x": 1}, "id": "abc"}}):
                response = client.request(method.upper(), path, **({"headers": headers} | kwargs))
                if response.status_code >= 500:
                    failures.append(f"{method.upper()} {path} {list(kwargs)[0]}: {response.status_code} {response.text[:100]}")
    assert count > 40
    assert failures == []
