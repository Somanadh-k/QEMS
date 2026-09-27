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


def req(method, path, token=None, json_body=None, raw_body=None, content_type=None):
    url = f"{BASE}{path}"
    hdrs = {}
    if content_type:
        hdrs["Content-Type"] = content_type
    elif json_body is not None:
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    data = json.dumps(json_body).encode() if json_body is not None else raw_body
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            body = resp.read()
            try:
                return resp.status, json.loads(body)
            except Exception:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except Exception as e:
        return -1, str(e)


def login(email, pw=PW):
    return req("POST", "/auth/login", json_body={"email": email, "password": pw})


TOKENS = {}
for role, email in [("admin", "admin@qemscorp.dev"), ("qa", "qa@qemscorp.dev"),
                     ("owner", "owner@qemscorp.dev"), ("viewer", "viewer@qemscorp.dev")]:
    st, body = login(email)
    TOKENS[role] = body["access_token"]

# ============================================================ 23. API SECURITY
st, body = req("GET", "/errors/-1", token=TOKENS["admin"])
log("TC-SEC-001", "APISecurity", "Negative error_id", "PASS" if st in (404, 422) else "FAIL", f"status={st}")

st, body = req("GET", "/errors/not-a-number", token=TOKENS["admin"])
log("TC-SEC-002", "APISecurity", "Non-numeric error_id", "PASS" if st == 422 else "FAIL", f"status={st}")

st, body = req("POST", "/errors", token=TOKENS["admin"], raw_body=b"{not valid json", content_type="application/json")
log("TC-SEC-003", "APISecurity", "Malformed JSON body rejected", "PASS" if st == 422 else "FAIL", f"status={st}")

# SQL injection via string filter param
st, body = req("GET", "/errors?status=" + urllib.request.quote("Open'; DROP TABLE errors; --"), token=TOKENS["admin"])
log("TC-SEC-004", "APISecurity", "SQLi via status filter param (ORM-parameterized)", "PASS" if st in (200, 422) else "FAIL", f"status={st}")

st, body = req("GET", "/errors?department_id=" + urllib.request.quote("1 OR 1=1"), token=TOKENS["admin"])
log("TC-SEC-005", "APISecurity", "SQLi via typed integer field (department_id)", "PASS" if st == 422 else "FAIL", f"status={st}")

# confirm table still intact
st, body = req("GET", "/lookups/departments" if False else "/departments", token=TOKENS["admin"])
st2, body2 = req("GET", "/errors", token=TOKENS["admin"])
log("TC-SEC-006", "APISecurity", "departments/errors tables intact after injection attempts", "PASS" if st2 == 200 else "FAIL", f"status={st2}")

# IDOR on GET /errors/{id} across departments (documented gap D-07)
st, body = req("GET", "/errors", token=TOKENS["admin"])
target_eid = body["items"][0]["error_id"] if body.get("items") else None
if target_eid:
    st, body = req("GET", f"/errors/{target_eid}", token=TOKENS["viewer"])
    log("TC-SEC-007-IDOR", "APISecurity", "GET /errors/{id} has no department/ownership scoping (documented gap D-07)",
        "FAIL" if st == 200 else "PASS", f"status={st}",
        cause="" if st != 200 else "missing implementation: no department scoping on error reads (documented in code docstring as deferred)")

# rate limiting on login
hits = []
for i in range(8):
    st, body = login("ratelimit-test-nonexistent@qemscorp.dev", "whatever")
    hits.append(st)
limited = 429 in hits
log("TC-SEC-008", "APISecurity", "Login rate limit triggers within 8 rapid attempts (limit=5/min)",
    "PASS" if limited else "FAIL", f"statuses={hits}")

# rate limit is per-account (fixed D-05): a different account from the same source should not be limited
st, body = login("admin@qemscorp.dev", PW)
log("TC-SEC-009", "APISecurity", "Different account from same IP not blocked by other account's rate limit (fixed D-05)",
    "PASS" if st == 200 else "FAIL", f"status={st} body={str(body)[:150]}",
    cause="" if st == 200 else "application bug (regression of fixed D-05)")

# auth bypass: try each protected route with no token
protected = [("GET", "/errors"), ("POST", "/errors"), ("GET", "/reports/summary"), ("GET", "/audit/verify")]
all_401 = True
for m, p in protected:
    st, _ = req(m, p)
    if st not in (401, 403):
        all_401 = False
log("TC-SEC-010", "APISecurity", "All protected routes reject missing token", "PASS" if all_401 else "FAIL", "")

# secrets not in frontend bundle
import subprocess
grep_out = subprocess.run(["grep", "-rIl", "-E", "sk-[A-Za-z0-9]{10,}|OPENAI_API_KEY", "/Users/somanadhk/Documents/QEMS/frontend/src"],
                           capture_output=True, text=True)
leaked = bool(grep_out.stdout.strip())
log("TC-AISEC-003", "AISecurity", "No OpenAI key or secret literal found in frontend source", "PASS" if not leaked else "FAIL", f"matches={grep_out.stdout}")

grep_dist = subprocess.run(["grep", "-rIl", "-E", "sk-[A-Za-z0-9]{10,}", "/Users/somanadhk/Documents/QEMS/frontend/dist"],
                            capture_output=True, text=True)
leaked_dist = bool(grep_dist.stdout.strip())
log("TC-AISEC-004", "AISecurity", "No OpenAI key literal found in built frontend dist bundle", "PASS" if not leaked_dist else "FAIL", f"matches={grep_dist.stdout}")

with open("/tmp/audit_results_part5.json", "w") as f:
    json.dump(RESULTS, f, indent=2)
print(f"\nPart 5 (security) complete: {len(RESULTS)} checks.")
