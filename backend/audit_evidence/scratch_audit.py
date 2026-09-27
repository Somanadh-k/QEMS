"""
Ad-hoc QA audit harness. Not part of the pytest suite -- exercises the LIVE running
backend over HTTP to produce evidence for TEST_REPORT.md. Read-only w.r.t. application
code; creates ordinary API-driven data the same way a real user would.
"""
import json
import random
import string
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api/v1"
PW = "Password123!"

RESULTS = []  # list of dicts: {id, category, desc, status, evidence, cause}


def log(tid, category, desc, status, evidence="", cause=""):
    RESULTS.append({"id": tid, "category": category, "desc": desc, "status": status,
                     "evidence": evidence, "cause": cause})
    print(f"[{status:14}] {tid:22} {desc}  ({evidence})")


def req(method, path, token=None, json_body=None, raw_body=None, headers=None):
    url = f"{BASE}{path}"
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
    elif raw_body is not None:
        data = raw_body
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
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
REFRESH = {}
for role, email in [("admin", "admin@qemscorp.dev"), ("qa", "qa@qemscorp.dev"),
                     ("owner", "owner@qemscorp.dev"), ("viewer", "viewer@qemscorp.dev")]:
    st, body = login(email)
    if st == 200:
        TOKENS[role] = body["access_token"]
        REFRESH[role] = body.get("refresh_token")
    else:
        print(f"LOGIN FAILED for {role}: {st} {body}")

# ============================================================ 2. AUTHENTICATION
log("TC-AUTH-001", "Auth", "Valid login all 4 seeded roles", "PASS" if len(TOKENS) == 4 else "FAIL",
    f"tokens obtained: {list(TOKENS.keys())}")

st, body = login("admin@qemscorp.dev", "WrongPassword!")
log("TC-AUTH-002", "Auth", "Invalid password rejected", "PASS" if st == 401 else "FAIL", f"status={st} body={body}")

st, body = login("nobody@qemscorp.dev", "whatever")
log("TC-AUTH-003", "Auth", "Unknown user rejected, no enumeration", "PASS" if st == 401 else "FAIL", f"status={st} body={body}")
same_msg = None
st1, b1 = login("admin@qemscorp.dev", "WrongPassword!")
st2, b2 = login("nobody@qemscorp.dev", "whatever")
enum_safe = (st1 == st2 == 401) and (str(b1) == str(b2))
log("TC-AUTH-003b", "Auth", "Wrong-password vs unknown-user messages identical (no enumeration)",
    "PASS" if enum_safe else "FAIL", f"{b1} vs {b2}")

st, body = req("GET", "/errors", token="garbage.token.value")
log("TC-AUTH-004", "Auth", "Malformed/garbage token rejected", "PASS" if st == 401 else "FAIL", f"status={st}")

st, body = req("GET", "/errors")
log("TC-AUTH-005", "Auth", "Missing token rejected on protected route", "PASS" if st in (401, 403) else "FAIL", f"status={st}")

# refresh token used as access token
if "admin" in REFRESH and REFRESH["admin"]:
    st, body = req("GET", "/errors", token=REFRESH["admin"])
    log("TC-AUTH-006", "Auth", "Refresh token rejected when used as access token", "PASS" if st == 401 else "FAIL", f"status={st}")
else:
    log("TC-AUTH-006", "Auth", "Refresh token rejected when used as access token", "BLOCKED", "no refresh token returned by login")

st, body = req("GET", "/auth/me", token=TOKENS.get("admin"))
log("TC-AUTH-008", "Auth", "GET /auth/me returns current user", "PASS" if st == 200 else "FAIL", f"status={st} body={body}")

# logout
st, body = req("POST", "/auth/logout", token=TOKENS.get("admin"))
log("TC-AUTH-007", "Auth", "POST /auth/logout endpoint", "NOT IMPLEMENTED" if st == 404 else ("PASS" if st == 200 else "FAIL"), f"status={st}")

if "admin" in REFRESH and REFRESH["admin"]:
    st, body = req("POST", "/auth/refresh", json_body={"refresh_token": REFRESH["admin"]})
    log("TC-AUTH-009", "Auth", "POST /auth/refresh with valid refresh token", "PASS" if st == 200 else "FAIL", f"status={st}")

# ============================================================ 3. RBAC MATRIX
def get_open_error_id(dept=1):
    st, body = req("GET", "/errors", token=TOKENS["admin"], )
    for it in body.get("items", []):
        if it["status"] == "Open":
            return it["error_id"]
    return None

rbac_cases = [
    ("create_error", "POST", "/errors", {"title": "RBAC probe", "description": "x", "category_id": 1,
                                          "severity": "Low", "department_id": 1, "date_discovered": "2026-01-01"},
     {"admin": 201, "qa": 201, "owner": 201, "viewer": 201}),
    ("list_errors", "GET", "/errors", None, {"admin": 200, "qa": 200, "owner": 200, "viewer": 200}),
    ("audit_verify", "GET", "/audit/verify", None, {"admin": 200, "qa": 403, "owner": 403, "viewer": 403}),
    ("reports_summary", "GET", "/reports/summary", None, {"admin": 200, "qa": 200, "owner": 403, "viewer": 200}),
    ("ai_root_cause_perm", "POST", "/ai/root-cause", {"error_id": 1}, {"admin": None, "qa": None, "owner": 403, "viewer": 403}),
]

for name, method, path, body_, expected in rbac_cases:
    for role, tok in TOKENS.items():
        exp = expected.get(role)
        if exp is None:
            continue
        st, resp = req(method, path, token=tok, json_body=body_)
        ok = (st == exp)
        log(f"TC-RBAC-{name}-{role}", "RBAC", f"{role} {method} {path} expect {exp}",
            "PASS" if ok else "FAIL", f"status={st} expected={exp} body={str(resp)[:150]}")

# state-changing endpoints role checks
eid = get_open_error_id()
if eid:
    for role, exp in [("admin", 200), ("qa", 200), ("owner", 403), ("viewer", 403)]:
        st, body = req("PATCH", f"/errors/{eid}/status", token=TOKENS[role], json_body={"status": "In Review"})
        # only first successful transition actually changes state; subsequent will 409. Track via cause.
        ok = (st == exp) or (exp == 200 and st == 409)  # 409 acceptable if already transitioned by a previous role in loop
        log(f"TC-RBAC-transition-{role}", "RBAC", f"{role} PATCH status expect {exp} (or 409 if already moved)",
            "PASS" if ok else "FAIL", f"status={st}")
else:
    log("TC-RBAC-transition", "RBAC", "role-gated status transition", "BLOCKED", "no Open error found")

for role, exp in [("admin", 201), ("qa", 403), ("owner", None), ("viewer", 403)]:
    if exp is None:
        continue
    # use a fresh open error per role to avoid state collisions
    st, cerr = req("POST", "/errors", token=TOKENS["admin"], json_body={
        "title": f"RBAC rebuttal probe {role}", "description": "x", "category_id": 1,
        "severity": "Low", "department_id": 1, "date_discovered": "2026-01-01"})
    new_eid = cerr.get("error_id") if st == 201 else None
    if new_eid:
        req("PATCH", f"/errors/{new_eid}/status", token=TOKENS["qa"], json_body={"status": "In Review"})
        st2, rbody = req("POST", f"/errors/{new_eid}/rebuttals", token=TOKENS[role], json_body={"justification": "test"})
        log(f"TC-RBAC-rebuttal-{role}", "RBAC", f"{role} submit rebuttal expect {exp}",
            "PASS" if st2 == exp else "FAIL", f"status={st2}")

for role, exp in [("admin", 201), ("qa", 201), ("owner", 403), ("viewer", 403)]:
    st, cerr = req("POST", "/errors", token=TOKENS["admin"], json_body={
        "title": f"RBAC decision probe {role}", "description": "x", "category_id": 1,
        "severity": "Low", "department_id": 1, "date_discovered": "2026-01-01"})
    new_eid = cerr.get("error_id") if st == 201 else None
    if new_eid:
        req("PATCH", f"/errors/{new_eid}/status", token=TOKENS["qa"], json_body={"status": "In Review"})
        req("PATCH", f"/errors/{new_eid}/status", token=TOKENS["qa"], json_body={"status": "QA Decision Pending"})
        st2, dbody = req("POST", f"/errors/{new_eid}/decision", token=TOKENS[role], json_body={"decision": "Resolved", "notes": "n"})
        log(f"TC-RBAC-decision-{role}", "RBAC", f"{role} record decision expect {exp}",
            "PASS" if st2 == exp else "FAIL", f"status={st2}")

st, body = req("POST", f"/errors/{eid or 1}/sla/pause", token=TOKENS["qa"], json_body={"reason": "test"})
log("TC-RBAC-sla-pause-qa", "RBAC", "QA Reviewer cannot pause SLA (Admin-only)", "PASS" if st == 403 else "FAIL", f"status={st}")

print("\n--- continuing to error creation / validation / lifecycle / rebuttal / evidence / decision / SLA / reports / AI / security / db ---\n")

with open("/tmp/audit_results_part1.json", "w") as f:
    json.dump(RESULTS, f, indent=2)
print(f"\nPart 1 complete: {len(RESULTS)} checks logged.")
