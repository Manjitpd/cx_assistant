"""Exercise conversation reads, customer messages, and manual replies."""

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:8001"


def call(
    method: str,
    path: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode()
    merged = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers=merged,
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
    expect(status == 200 and isinstance(brands, list), f"brands: {status} {brands}")
    by_name = {brand["name"]: brand for brand in brands}
    aqua = by_name["AquaPure"]
    glow = by_name["GlowNest"]
    aqua_query = urllib.parse.urlencode({"brand_id": aqua["id"]})
    glow_query = urllib.parse.urlencode({"brand_id": glow["id"]})

    status, aqua_threads = call("GET", f"/api/conversations?{aqua_query}")
    status_b, glow_threads = call("GET", f"/api/conversations?{glow_query}")
    expect(status == 200 and status_b == 200, "list failed")
    expect(len(aqua_threads) == 2 and len(glow_threads) == 2, f"counts {len(aqua_threads)} {len(glow_threads)}")
    expect(all(row["brand"]["id"] == aqua["id"] for row in aqua_threads), "AquaPure inbox leaked another brand")
    expect(all(row["brand"]["id"] == glow["id"] for row in glow_threads), "GlowNest inbox leaked another brand")

    leak = next(row for row in aqua_threads if "AP-1042" in row["subject"])
    glow_thread = glow_threads[0]
    status, detail = call("GET", f"/api/conversations/{leak['id']}?{aqua_query}")
    expect(status == 200, f"detail failed: {status} {detail}")
    for key in ("customer", "brand", "order", "status", "messages"):
        expect(key in detail, f"detail missing {key}")
    expect(detail["customer"]["full_name"] == "Maya Chen", detail["customer"])
    expect(detail["order"]["order_number"] == "AP-1042", detail["order"])
    expect(detail["brand"]["name"] == "AquaPure", detail["brand"])
    expect(all(message["created_at"] for message in detail["messages"]), "missing timestamps")
    expect({message["author_type"] for message in detail["messages"]} <= {"CUSTOMER", "AGENT"}, detail["messages"])
    before = len(detail["messages"])

    status, blocked = call(
        "POST",
        f"/api/conversations/{leak['id']}/messages?{glow_query}",
        {"body": "This must not be saved on AquaPure."},
    )
    expect(status == 404, f"cross-brand customer message should be 404, got {status} {blocked}")

    customer_body = "I checked the base again and the leak is still there."
    status, updated = call(
        "POST",
        f"/api/conversations/{leak['id']}/messages?{aqua_query}",
        {"body": customer_body},
    )
    expect(status == 200, f"customer message failed: {status} {updated}")
    expect(updated["messages"][-1]["author_type"] == "CUSTOMER", updated["messages"][-1])
    expect(updated["messages"][-1]["body"] == customer_body, updated["messages"][-1])
    expect(len(updated["messages"]) == before + 1, "customer message was not appended")

    status, reread = call("GET", f"/api/conversations/{leak['id']}?{aqua_query}")
    expect(status == 200 and reread["messages"][-1]["body"] == customer_body, "message missing after reload")

    agent_body = "The prepaid label is on its way to your email."
    status, replied = call(
        "POST",
        f"/api/conversations/{leak['id']}/manual-reply?{aqua_query}",
        {"body": agent_body},
        {"Idempotency-Key": str(uuid.uuid4())},
    )
    expect(status == 200 and replied["messages"][-1]["author_type"] == "AGENT", f"manual reply failed: {status}")
    expect(replied["messages"][-1]["body"] == agent_body, replied["messages"][-1])

    status, blocked = call(
        "POST",
        f"/api/conversations/{glow_thread['id']}/manual-reply?{aqua_query}",
        {"body": "AquaPure must not reply on this GlowNest thread."},
        {"Idempotency-Key": str(uuid.uuid4())},
    )
    expect(status == 404, f"cross-brand manual reply should be 404, got {status} {blocked}")
    status, glow_detail = call("GET", f"/api/conversations/{glow_thread['id']}?{glow_query}")
    expect(
        all(message["body"] != "AquaPure must not reply on this GlowNest thread." for message in glow_detail["messages"]),
        "cross-brand reply was stored",
    )

    status, final = call("GET", f"/api/conversations/{leak['id']}?{aqua_query}")
    bodies = [message["body"] for message in final["messages"]]
    expect(customer_body in bodies and agent_body in bodies, "persisted messages missing on a fresh read")
    print("conversation API checks passed")
    print(f"thread={leak['id']} messages={len(final['messages'])}")


if __name__ == "__main__":
    main()
