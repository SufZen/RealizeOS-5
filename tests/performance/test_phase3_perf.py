"""
Phase 3: Performance and Load Tests — RealizeOS 5 Production Readiness

Tests API concurrency, startup time, memory, and response latency.
Requires: Server running on localhost:8080.
"""

import asyncio
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://localhost:8080"
RESULTS: list[dict] = []


def record(test_id: str, name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"id": test_id, "name": name, "passed": passed, "detail": detail})
    print(f"  [{status}] {test_id}: {name}")
    if detail:
        print(f"         {detail}")


async def run_all():
    # Use a higher timeout and connection pool
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    async with httpx.AsyncClient(base_url=BASE, timeout=30, limits=limits) as c:
        # Verify server
        r = await c.get("/api/health")
        assert r.status_code == 200, f"Server not ready: {r.status_code}"
        print("Server is healthy. Running performance tests...\n")

        # ──────────────────────────────────────────
        # 3.1 Concurrent API calls (50 health checks)
        # ──────────────────────────────────────────
        print("-- 3.1 Concurrent API Calls --")
        # Use /api/health which bypasses rate limiting
        start = time.time()
        tasks = [c.get("/api/health") for _ in range(50)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start

        successes = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 200]
        latencies = [r.elapsed.total_seconds() * 1000 for r in successes]

        if latencies:
            p50 = statistics.median(latencies)
            p95 = sorted(latencies)[int(len(latencies) * 0.95)]
            p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        else:
            p50 = p95 = p99 = 999

        record(
            "3.1a",
            "50 concurrent health checks",
            len(successes) == 50,
            f"{len(successes)}/50 succeeded in {elapsed:.2f}s",
        )
        record(
            "3.1b",
            "Latency percentiles",
            p99 < 500,
            f"p50={p50:.0f}ms, p95={p95:.0f}ms, p99={p99:.0f}ms (target: p99 < 500ms)",
        )

        # ──────────────────────────────────────────
        # 3.2 Concurrent venture operations (10)
        # ──────────────────────────────────────────
        print("\n-- 3.2 Concurrent Venture Operations --")

        async def create_venture(i):
            body = {"key": f"perf-test-{i}", "name": f"Perf Test {i}", "description": f"Load test venture {i}"}
            return await c.post("/api/ventures", json=body)

        start = time.time()
        venture_tasks = [create_venture(i) for i in range(10)]
        venture_results = await asyncio.gather(*venture_tasks, return_exceptions=True)
        v_elapsed = time.time() - start

        v_success = sum(1 for r in venture_results if isinstance(r, httpx.Response) and r.status_code in (200, 201))
        record("3.2", "10 concurrent venture creates", v_success == 10, f"{v_success}/10 succeeded in {v_elapsed:.2f}s")

        # ──────────────────────────────────────────
        # 3.4 Many ventures — dashboard performance
        # ──────────────────────────────────────────
        print("\n-- 3.4 Dashboard with Multiple Ventures --")
        # Dashboard already has the 10 ventures from 3.2
        start = time.time()
        r = await c.get("/api/dashboard")
        dash_latency = (time.time() - start) * 1000
        record(
            "3.4",
            "Dashboard load time",
            dash_latency < 3000 and r.status_code == 200,
            f"{dash_latency:.0f}ms (target: <3000ms), status={r.status_code}",
        )

        # ──────────────────────────────────────────
        # 3.6 Cold start time (measure status endpoint)
        # ──────────────────────────────────────────
        print("\n-- 3.6 Status Endpoint Latency --")
        latencies_status = []
        for _ in range(10):
            start = time.time()
            r = await c.get("/api/status")
            latencies_status.append((time.time() - start) * 1000)

        avg_status = statistics.mean(latencies_status)
        record("3.6", "Status endpoint avg latency", avg_status < 200, f"avg={avg_status:.0f}ms over 10 calls")

        # ──────────────────────────────────────────
        # 3.8 Sustained request throughput
        # ──────────────────────────────────────────
        print("\n-- 3.8 Sustained Throughput --")
        # Send 200 health requests sequentially to measure sustained throughput
        start = time.time()
        sustained_ok = 0
        for _ in range(200):
            r = await c.get("/api/health")
            if r.status_code == 200:
                sustained_ok += 1
        sustained_elapsed = time.time() - start
        rps = sustained_ok / sustained_elapsed

        record(
            "3.8",
            f"Sustained throughput ({sustained_ok} requests)",
            rps > 50,
            f"{rps:.0f} req/s in {sustained_elapsed:.1f}s (target: >50 req/s)",
        )

        # ──────────────────────────────────────────
        # 3.10 Workflow CRUD throughput
        # ──────────────────────────────────────────
        print("\n-- 3.10 Workflow CRUD Throughput --")
        wf_latencies = []
        for i in range(20):
            body = {
                "name": f"perf-wf-{i}",
                "description": f"Test {i}",
                "triggers": ["test"],
                "steps": [{"action": "echo"}],
            }
            start = time.time()
            r = await c.post("/api/workflows", json=body)
            wf_latencies.append((time.time() - start) * 1000)

        if wf_latencies:
            wf_avg = statistics.mean(wf_latencies)
            wf_p95 = sorted(wf_latencies)[int(len(wf_latencies) * 0.95)]
        else:
            wf_avg = wf_p95 = 999

        record(
            "3.10",
            "Workflow create throughput (20x)",
            wf_p95 < 200,
            f"avg={wf_avg:.0f}ms, p95={wf_p95:.0f}ms (target: p95 < 200ms)",
        )

        # Cleanup: delete test ventures and workflows
        print("\n-- Cleanup --")
        for i in range(10):
            await c.delete(f"/api/ventures/perf-test-{i}")
        for i in range(20):
            await c.delete(f"/api/workflows/perf-wf-{i}")
        print("  Cleaned up test data")

    # Summary
    print("\n" + "=" * 60)
    print("PHASE 3 PERFORMANCE - RESULTS")
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
