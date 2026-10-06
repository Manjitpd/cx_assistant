"""Exercise knowledge-base CRUD and brand isolation against a running API."""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8001"


def call(method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            body = json.loads(raw) if raw else None
            return response.status, body
    except urllib.error.HTTPError as error:
        raw = error.read()
        body = json.loads(raw) if raw else None
        return error.code, body


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    status, brands = call("GET", "/api/brands")
    expect(status == 200 and isinstance(brands, list) and len(brands) == 2, f"brands: {status} {brands}")
    by_name = {brand["name"]: brand for brand in brands}
    aqua = by_name["AquaPure"]
    glow = by_name["GlowNest"]

    status, aqua_entries = call("GET", f"/api/brands/{aqua['id']}/knowledge")
    status_b, glow_entries = call("GET", f"/api/brands/{glow['id']}/knowledge")
    expect(status == 200 and status_b == 200, "list failed")
    expect(len(aqua_entries) == 4 and len(glow_entries) == 4, "expected four policies per brand")
    expect(all(entry["brand_id"] == aqua["id"] for entry in aqua_entries), "AquaPure list leaked another brand")
    expect(all(entry["brand_id"] == glow["id"] for entry in glow_entries), "GlowNest list leaked another brand")
    expect(
        {entry["category"] for entry in aqua_entries} == {"RETURN", "REFUND", "SHIPPING", "CANCELLATION"},
        "categories missing",
    )
    aqua_return = next(entry for entry in aqua_entries if entry["category"] == "RETURN")
    glow_return = next(entry for entry in glow_entries if entry["category"] == "RETURN")
    expect("30 days" in aqua_return["content"] and "60 days" in glow_return["content"], "policy text mixed")

    status, missing = call("GET", "/api/brands/00000000-0000-4000-8000-000000000000/knowledge")
    expect(status == 404, f"unknown brand should be 404, got {status} {missing}")

    created_body = {
        "title": "Holiday shipping hold",
        "category": "SHIPPING",
        "content": "AquaPure pauses nonessential shipments on December 24 and 25.",
        "active": True,
        "brand_id": glow["id"],
    }
    status, rejected = call("POST", f"/api/brands/{aqua['id']}/knowledge", created_body)
    expect(status == 422, f"cross-brand create should be 422, got {status} {rejected}")

    created_body["brand_id"] = aqua["id"]
    status, created = call("POST", f"/api/brands/{aqua['id']}/knowledge", created_body)
    expect(status == 201 and created["brand_id"] == aqua["id"], f"create failed: {status} {created}")
    entry_id = created["id"]

    status, blocked = call("GET", f"/api/knowledge/{entry_id}")
    expect(status == 422, f"get without brand_id should be 422, got {status} {blocked}")

    query = urllib.parse.urlencode({"brand_id": aqua["id"]})
    status, fetched = call("GET", f"/api/knowledge/{entry_id}?{query}")
    expect(status == 200 and fetched["title"] == created_body["title"], f"get failed: {status} {fetched}")

    foreign_query = urllib.parse.urlencode({"brand_id": glow["id"]})
    status, blocked = call("GET", f"/api/knowledge/{entry_id}?{foreign_query}")
    expect(status == 404, f"cross-brand get should be 404, got {status} {blocked}")

    edited = {
        "title": "Holiday shipping hold (updated)",
        "category": "SHIPPING",
        "content": "AquaPure pauses nonessential shipments on December 24, 25, and 26.",
        "active": False,
    }
    status, updated = call("PUT", f"/api/knowledge/{entry_id}?{query}", edited)
    expect(
        status == 200 and updated["title"].endswith("(updated)") and updated["active"] is False,
        f"edit failed: {status} {updated}",
    )
    status, fetched = call("GET", f"/api/knowledge/{entry_id}?{query}")
    expect(fetched["content"].endswith("26."), f"edit did not persist: {fetched}")

    status, blocked = call(
        "PUT",
        f"/api/knowledge/{glow_return['id']}?{query}",
        {
            "title": "Taken over",
            "category": "RETURN",
            "content": "This should not replace GlowNest policy.",
            "active": False,
        },
    )
    expect(status == 404, f"cross-brand edit should be 404, got {status} {blocked}")
    glow_query = urllib.parse.urlencode({"brand_id": glow["id"]})
    status, still = call("GET", f"/api/knowledge/{glow_return['id']}?{glow_query}")
    expect(status == 200 and still["title"] == glow_return["title"] and still["active"] is True, "GlowNest policy changed")

    status, blocked = call("DELETE", f"/api/knowledge/{glow_return['id']}?{query}")
    expect(status == 404, f"cross-brand delete should be 404, got {status} {blocked}")
    status, still = call("GET", f"/api/knowledge/{glow_return['id']}?{glow_query}")
    expect(status == 200, "GlowNest policy was deleted")

    status, _ = call("DELETE", f"/api/knowledge/{entry_id}?{query}")
    expect(status == 204, f"delete failed: {status}")
    status, gone = call("GET", f"/api/knowledge/{entry_id}?{query}")
    expect(status == 404, f"deleted entry still readable: {status} {gone}")

    status, aqua_entries = call("GET", f"/api/brands/{aqua['id']}/knowledge")
    expect(len(aqua_entries) == 4, "AquaPure policy count changed")
    print("knowledge API checks passed")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as error:
        print(error, file=sys.stderr)
        raise
