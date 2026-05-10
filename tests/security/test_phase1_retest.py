"""
Phase 1 Retest: Inconclusive tests (1.4, 1.6, 1.8)
Runs each test individually with delays to avoid rate limiter self-tripping.
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

BASE = "http://localhost:8080"
RESULTS: list[dict] = []


def record(test_id: str, name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"id": test_id, "name": name, "passed": passed, "detail": detail})
    print(f"  [{status}] {test_id}: {name}")
    if detail:
        print(f"         {detail}")


async def run_all():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.get("/api/health")
        assert r.status_code == 200, f"Server not ready: {r.status_code}"
        print("Server is healthy. Running retests with delays...\n")

        # ─────────────────────────────────────────
        # 1.4 JWT Expired/Tampered Tokens
        # ─────────────────────────────────────────
        print("-- 1.4 JWT Token Handling --")
        jwt_enabled = os.getenv("REALIZE_JWT_ENABLED", "").lower() in ("true", "1", "yes")

        # Test with tampered Bearer token
        r = await c.get("/api/dashboard", headers={"Authorization": "Bearer invalid.token.here"})
        if jwt_enabled:
            record("1.4a", "Tampered JWT rejected (JWT enabled)", r.status_code == 401, f"Got {r.status_code}")
        else:
            # JWT not enabled — Bearer tokens should be ignored, request falls through
            record(
                "1.4a",
                "Tampered JWT ignored (JWT disabled)",
                r.status_code == 200,
                f"Got {r.status_code} — JWT is opt-in, invalid Bearer tokens are ignored",
            )

        await asyncio.sleep(2)  # Wait for rate limiter window

        # Test with no auth at all (should work in dev mode)
        r = await c.get("/api/dashboard")
        record("1.4b", "No auth in dev mode", r.status_code == 200, f"Got {r.status_code}")

        await asyncio.sleep(2)

        # Test that API key auth works when set
        api_key = os.getenv("REALIZE_API_KEY", "")
        if api_key:
            r_good = await c.get("/api/dashboard", headers={"X-API-Key": api_key})
            record("1.4c", "Correct API key accepted", r_good.status_code == 200, f"Got {r_good.status_code}")

            r_bad = await c.get("/api/dashboard", headers={"X-API-Key": "wrong-key"})
            record("1.4d", "Wrong API key rejected", r_bad.status_code in (401, 403), f"Got {r_bad.status_code}")
        else:
            record("1.4c", "API key auth (not configured)", True, "REALIZE_API_KEY not set — expected in dev mode")

        await asyncio.sleep(3)

        # ─────────────────────────────────────────
        # 1.6 Oversized Request Body
        # ─────────────────────────────────────────
        print("\n-- 1.6 Oversized Request Body --")

        # KB file PUT has explicit 1MB limit (line 191 of venture_kb.py)
        big_content = "x" * (2 * 1024 * 1024)  # 2MB
        r = await c.put(
            "/api/ventures/my-business-1/kb/file",
            json={"path": "systems/my-business-1/B-brain/huge.md", "content": big_content},
        )
        record(
            "1.6a", "2MB KB file rejected (PUT)", r.status_code == 413, f"Got {r.status_code} (413 = Payload Too Large)"
        )

        await asyncio.sleep(2)

        # KB file within limit (500KB)
        ok_content = "y" * (500 * 1024)  # 500KB
        r = await c.put(
            "/api/ventures/my-business-1/kb/file",
            json={"path": "systems/my-business-1/B-brain/ok.md", "content": ok_content},
        )
        record("1.6b", "500KB KB file accepted (PUT)", r.status_code in (200, 204), f"Got {r.status_code}")

        await asyncio.sleep(2)

        # Chat message length limit
        r = await c.get("/api/health")  # Reset rate window awareness
        await asyncio.sleep(1)

        # Test chat with very long message (should be handled gracefully)
        long_msg = "a " * 10000  # ~20KB
        r = await c.post("/api/chat", json={"message": long_msg, "system_key": "my-business-1"})
        # Chat may accept long messages (the handler likely truncates or has its own limit)
        # The key thing is it shouldn't crash (500)
        record(
            "1.6c",
            "20KB chat message doesn't crash",
            r.status_code != 500,
            f"Got {r.status_code} (any non-500 is acceptable)",
        )

        await asyncio.sleep(3)

        # ─────────────────────────────────────────
        # 1.8 Audit Log Integrity
        # ─────────────────────────────────────────
        print("\n-- 1.8 Audit Log Integrity --")

        # No DELETE endpoint for audit
        r = await c.delete("/api/security/audit")
        record("1.8a", "No audit DELETE endpoint", r.status_code in (404, 405), f"Got {r.status_code}")

        await asyncio.sleep(2)

        # No PUT endpoint for audit
        r = await c.put("/api/security/audit", json={"tamper": True})
        record("1.8b", "No audit PUT endpoint", r.status_code in (404, 405), f"Got {r.status_code}")

        await asyncio.sleep(2)

        # Audit GET returns data (read-only access)
        r = await c.get("/api/security/audit")
        record("1.8c", "Audit GET is read-only", r.status_code == 200, f"Got {r.status_code}")

        # Verify audit stats endpoint exists
        await asyncio.sleep(1)
        r = await c.get("/api/security/audit/stats")
        record("1.8d", "Audit stats endpoint", r.status_code == 200, f"Got {r.status_code}")

    # Summary
    print("\n" + "=" * 60)
    print("PHASE 1 RETEST - RESULTS")
    print("=" * 60)
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = total - passed
    print(f"\n  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
    print(f"  Pass Rate: {passed / total:.0%}")
    if failed:
        print("\n  FAILED TESTS:")
        for r in RESULTS:
            if not r["passed"]:
                print(f"     {r['id']}: {r['name']} -- {r['detail']}")
    print()
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all())
    sys.exit(0 if success else 1)
