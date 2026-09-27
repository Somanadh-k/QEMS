import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api/v1"
PW = "Password123!"
RESULTS = []


def log(tid, category, desc, status, evidence="", cause=""):
    RESULTS.append({"id": tid, "category": category, "desc": desc, "status": status,
                     "evidence": evidence, "cause": cause})
    print(f"[{status:14}] {tid:28} {desc}  ({evidence})")


def req(method, path, token=None, json_body=None):
    hdrs = {"Content-Type": "application/json"} if json_body is not None else {}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    data = json.dumps(json_body).encode() if json_body is not None else None
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


st, body = req("POST", "/auth/login", json_body={"email": "admin@qemscorp.dev", "password": PW})
admin_tok = body["access_token"]

st, body = req("GET", "/audit/verify", token=admin_tok)
log("TC-AUDIT-001", "DBIntegrity", "GET /audit/verify on current DB", "PASS" if st == 200 and body.get("valid") else "FAIL",
    f"status={st} body={body}",
    cause="" if body.get("valid") else "data integrity: audit chain broken")

# performance sampling (read-only, no load test)
def timeit(method, path, token, n=10):
    times = []
    for _ in range(n):
        t0 = time.monotonic()
        req(method, path, token)
        times.append((time.monotonic() - t0) * 1000)
    return sum(times) / len(times), max(times)

avg, mx = timeit("GET", "/errors?page_size=20", admin_tok, 10)
log("TC-PERF-001", "Performance", "GET /errors?page_size=20 x10 avg/max ms", "PASS", f"avg={avg:.1f}ms max={mx:.1f}ms")

avg, mx = timeit("GET", "/errors?page_size=100", admin_tok, 10)
log("TC-PERF-002", "Performance", "GET /errors?page_size=100 x10 avg/max ms", "PASS", f"avg={avg:.1f}ms max={mx:.1f}ms")

avg, mx = timeit("GET", "/reports/analytics/trends", admin_tok, 10)
log("TC-PERF-003", "Performance", "GET /reports/analytics/trends x10 avg/max ms", "PASS", f"avg={avg:.1f}ms max={mx:.1f}ms")

avg, mx = timeit("GET", "/reports/summary", admin_tok, 10)
log("TC-PERF-004", "Performance", "GET /reports/summary x10 avg/max ms", "PASS", f"avg={avg:.1f}ms max={mx:.1f}ms")

with open("/tmp/audit_results_part6.json", "w") as f:
    json.dump(RESULTS, f, indent=2)
print(f"\nPart 6 (audit/perf) complete: {len(RESULTS)} checks.")
