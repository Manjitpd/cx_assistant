"""Brand-scoped knowledge retrieval."""

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8001"

AQUA_MESSAGE = "Can I return this defective pitcher and get a prepaid label?"
GLOW_MESSAGE = (
    "I want to return opened skincare because more than half remains. "
    "Please send a prepaid label."
)
UNRELATED_MESSAGE = "The xylophone metronome needs a rehearsal stand."
TOKEN = "zephyrwidget"


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


def knowledge_ids(brand_id: str) -> set[str]:
    status, rows = call("GET", f"/api/brands/{brand_id}/knowledge")
    expect(status == 200 and isinstance(rows, list), f"knowledge list failed: {status} {rows}")
    return {row["id"] for row in rows}


def assert_ranked(hits: object, allowed_ids: set[str], blocked_ids: set[str], label: str) -> None:
    expect(isinstance(hits, list) and len(hits) > 0, f"{label} returned nothing: {hits}")
    scores = []
    for hit in hits:
        for key in ("knowledge_entry_id", "title", "category", "content", "score"):
            expect(key in hit, f"{label} missing {key}: {hit}")
        expect(hit["knowledge_entry_id"] in allowed_ids, f"{label} returned another brand: {hit}")
        expect(hit["knowledge_entry_id"] not in blocked_ids, f"{label} leaked the other brand: {hit}")
        expect(hit["title"] and hit["content"], f"{label} empty text: {hit}")
        expect(isinstance(hit["score"], (int, float)) and hit["score"] > 0, f"{label} score: {hit}")
        scores.append(hit["score"])
    expect(scores == sorted(scores, reverse=True), f"{label} rank order: {scores}")


def main() -> None:
    status, brands = call("GET", "/api/brands")
    expect(status == 200 and isinstance(brands, list), f"brands: {status} {brands}")
    by_name = {brand["name"]: brand for brand in brands}
    aqua = by_name["AquaPure"]
    glow = by_name["GlowNest"]
    aqua_ids = knowledge_ids(aqua["id"])
    glow_ids = knowledge_ids(glow["id"])
    expect(aqua_ids.isdisjoint(glow_ids), "knowledge ids overlap")

    aqua_query = urllib.parse.urlencode({"brand_id": aqua["id"]})
    glow_query = urllib.parse.urlencode({"brand_id": glow["id"]})
    status, aqua_threads = call("GET", f"/api/conversations?{aqua_query}")
    status_b, glow_threads = call("GET", f"/api/conversations?{glow_query}")
    expect(status == 200 and status_b == 200, "conversation list failed")
    aqua_thread = next(row for row in aqua_threads if "AP-1042" in row["subject"])
    glow_thread = next(row for row in glow_threads if "Serum" in row["subject"])

    status, aqua_hits = call(
        "POST",
        f"/api/conversations/{aqua_thread['id']}/retrieve",
        {"message": AQUA_MESSAGE},
    )
    expect(status == 200, f"AquaPure retrieval failed: {status} {aqua_hits}")
    assert_ranked(aqua_hits, aqua_ids, glow_ids, "AquaPure")
    expect(aqua_hits[0]["category"] == "RETURN", f"AquaPure top hit: {aqua_hits[0]}")

    status, glow_hits = call(
        "POST",
        f"/api/conversations/{glow_thread['id']}/retrieve",
        {"message": GLOW_MESSAGE},
    )
    expect(status == 200, f"GlowNest retrieval failed: {status} {glow_hits}")
    assert_ranked(glow_hits, glow_ids, aqua_ids, "GlowNest")
    expect(glow_hits[0]["category"] == "RETURN", f"GlowNest top hit: {glow_hits[0]}")

    status, empty = call(
        "POST",
        f"/api/conversations/{aqua_thread['id']}/retrieve",
        {"message": UNRELATED_MESSAGE},
    )
    expect(status == 200 and empty == [], f"unrelated message should be empty: {status} {empty}")

    status, created = call(
        "POST",
        f"/api/brands/{aqua['id']}/knowledge",
        {
            "title": "Temporary zephyr note",
            "category": "SHIPPING",
            "content": f"{TOKEN} applies only to this temporary policy.",
            "active": False,
        },
    )
    expect(status == 201, f"inactive policy create failed: {status} {created}")
    entry_id = created["id"]
    try:
        status, hidden = call(
            "POST",
            f"/api/conversations/{aqua_thread['id']}/retrieve",
            {"message": TOKEN},
        )
        expect(status == 200 and hidden == [], f"inactive entry was returned: {status} {hidden}")

        status, updated = call(
            "PUT",
            f"/api/knowledge/{entry_id}?{aqua_query}",
            {
                "title": "Temporary zephyr note",
                "category": "SHIPPING",
                "content": f"{TOKEN} applies only to this temporary policy.",
                "active": True,
            },
        )
        expect(status == 200, f"enable failed: {status} {updated}")
        status, visible = call(
            "POST",
            f"/api/conversations/{aqua_thread['id']}/retrieve",
            {"message": TOKEN},
        )
        expect(status == 200 and isinstance(visible, list), f"active retrieval failed: {status} {visible}")
        expect(
            any(hit["knowledge_entry_id"] == entry_id for hit in visible),
            f"active entry was not found: {visible}",
        )
        expect(all(hit["knowledge_entry_id"] not in glow_ids for hit in visible), visible)

        status, disabled = call(
            "PUT",
            f"/api/knowledge/{entry_id}?{aqua_query}",
            {
                "title": "Temporary zephyr note",
                "category": "SHIPPING",
                "content": f"{TOKEN} applies only to this temporary policy.",
                "active": False,
            },
        )
        expect(status == 200, f"disable failed: {status} {disabled}")
        status, hidden_again = call(
            "POST",
            f"/api/conversations/{aqua_thread['id']}/retrieve",
            {"message": TOKEN},
        )
        expect(
            status == 200 and hidden_again == [],
            f"disabled entry was returned: {status} {hidden_again}",
        )
    finally:
        status, _deleted = call("DELETE", f"/api/knowledge/{entry_id}?{aqua_query}")
        expect(status == 204, f"cleanup delete failed: {status} {_deleted}")

    manipulated = urllib.parse.urlencode({"brand_id": glow["id"]})
    status, forced = call(
        "POST",
        f"/api/conversations/{aqua_thread['id']}/retrieve?{manipulated}",
        {"message": AQUA_MESSAGE, "brand_id": glow["id"]},
    )
    expect(status == 200, f"manipulated retrieval failed: {status} {forced}")
    assert_ranked(forced, aqua_ids, glow_ids, "manipulated AquaPure")
    expect(
        [hit["knowledge_entry_id"] for hit in forced]
        == [hit["knowledge_entry_id"] for hit in aqua_hits],
        f"claimed brand changed the result: {forced}",
    )

    print("retrieval checks passed")


if __name__ == "__main__":
    main()
