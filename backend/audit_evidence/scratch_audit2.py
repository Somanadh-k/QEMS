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


def req(method, path, token=None, json_body=None, raw_body=None, content_type=None, headers=None):
    url = f"{BASE}{path}"
    hdrs = {}
    if content_type:
        hdrs["Content-Type"] = content_type
    elif json_body is not None:
        hdrs["Content-Type"] = "application/json"
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
        with urllib.request.urlopen(r, timeout=20) as resp:
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

BASE_ERR = {"title": "Audit test error", "description": "Something failed in audit testing.",
            "category_id": 1, "severity": "Low", "department_id": 1, "date_discovered": "2026-01-01"}


def mk_error(**overrides):
    payload = dict(BASE_ERR)
    payload.update(overrides)
    return req("POST", "/errors", token=TOKENS["admin"], json_body=payload)


# ============================================================ 4/5/6. CREATION & VALIDATION & UNIQUE IDs
st, body = mk_error(title="Valid error creation test")
log("TC-ERR-001", "ErrorCreation", "Valid error creation", "PASS" if st == 201 else "FAIL", f"status={st} body={body}")
valid_eid = body.get("error_id") if st == 201 else None

st, body = req("POST", "/errors", token=TOKENS["admin"], json_body={"description": "x", "category_id": 1,
               "severity": "Low", "department_id": 1, "date_discovered": "2026-01-01"})
log("TC-ERR-002", "ErrorValidation", "Missing required field (title) rejected", "PASS" if st == 422 else "FAIL", f"status={st}")

st, body = mk_error(title="")
log("TC-ERR-003", "ErrorValidation", "Empty title rejected", "PASS" if st == 422 else "FAIL", f"status={st} body={str(body)[:150]}")

st, body = mk_error(title="A" * 5000)
log("TC-ERR-004", "ErrorValidation", "5000-char title rejected cleanly (was 500 crash, D-04)",
    "PASS" if st == 422 else "FAIL", f"status={st}",
    cause="" if st == 422 else "application bug (regression of fixed D-04)")

st, body = mk_error(title="A" * 200)
log("TC-ERR-004b", "ErrorValidation", "Exactly-200-char title boundary accepted", "PASS" if st == 201 else "FAIL", f"status={st}")

st, body = mk_error(title="A" * 201)
log("TC-ERR-004c", "ErrorValidation", "201-char title rejected (just over boundary)", "PASS" if st == 422 else "FAIL", f"status={st}")

st, body = mk_error(description="")
log("TC-ERR-005", "ErrorValidation", "Empty description rejected", "PASS" if st == 422 else "FAIL", f"status={st}")

st, body = mk_error(department_id=999999)
log("TC-ERR-006", "ErrorValidation", "Nonexistent department_id", "PASS" if st in (404, 422) else "FAIL", f"status={st} body={str(body)[:150]}",
    cause="" if st in (404,422) else "application bug: FK violation not cleanly handled" )

st, body = mk_error(category_id=999999)
log("TC-ERR-007", "ErrorValidation", "Nonexistent category_id", "PASS" if st in (404, 422) else "FAIL", f"status={st} body={str(body)[:150]}",
    cause="" if st in (404,422) else "application bug: FK violation not cleanly handled")

st, body = mk_error(severity="Bogus")
log("TC-ERR-008", "ErrorValidation", "Invalid severity value", "PASS" if st in (400, 422) else "FAIL", f"status={st} body={str(body)[:150]}",
    cause="" if st in (400,422) else "application bug: no severity enum validation")

st, body = mk_error(date_discovered="not-a-date")
log("TC-ERR-009", "ErrorValidation", "Malformed date_discovered", "PASS" if st == 422 else "FAIL", f"status={st}")

# unique ID generation - rapid sequential creation
codes = []
ok = True
for i in range(6):
    st, body = mk_error(title=f"Rapid uniqueness test {i}")
    if st != 201:
        ok = False
        break
    codes.append(body["qa_error_code"])
unique = len(set(codes)) == len(codes)
log("TC-ID-001", "UniqueID", "6 rapid sequential creations -> unique qa_error_code", "PASS" if (ok and unique) else "FAIL",
    f"codes={codes}")

# ============================================================ 7/8. LIFECYCLE
st, body = mk_error(title="Lifecycle happy path")
lc_eid = body["error_id"]
st, body = req("PATCH", f"/errors/{lc_eid}/status", token=TOKENS["qa"], json_body={"status": "In Review"})
log("TC-LC-001", "Lifecycle", "Open -> In Review", "PASS" if st == 200 else "FAIL", f"status={st}")
st, body = req("PATCH", f"/errors/{lc_eid}/status", token=TOKENS["qa"], json_body={"status": "QA Decision Pending"})
log("TC-LC-002", "Lifecycle", "In Review -> QA Decision Pending", "PASS" if st == 200 else "FAIL", f"status={st}")
st, body = req("POST", f"/errors/{lc_eid}/decision", token=TOKENS["qa"], json_body={"decision": "Resolved", "notes": "fixed"})
log("TC-LC-003", "Lifecycle", "record_decision Resolved auto-closes error", "PASS" if st == 201 else "FAIL", f"status={st}")
st, body = req("GET", f"/errors/{lc_eid}", token=TOKENS["admin"])
closed_ok = body.get("status") == "Closed" and body.get("closed_at")
log("TC-LC-004", "Lifecycle", "Error ends Closed with closed_at populated", "PASS" if closed_ok else "FAIL", f"status={body.get('status')} closed_at={body.get('closed_at')}")

# invalid transitions
st, body = mk_error(title="Invalid transition tests")
it_eid = body["error_id"]
st, body = req("PATCH", f"/errors/{it_eid}/status", token=TOKENS["qa"], json_body={"status": "QA Decision Pending"})
log("TC-LC-005", "Lifecycle", "Open -> QA Decision Pending (skip) rejected", "PASS" if st == 409 else "FAIL", f"status={st}")

req("PATCH", f"/errors/{it_eid}/status", token=TOKENS["qa"], json_body={"status": "In Review"})
st, body = req("PATCH", f"/errors/{it_eid}/status", token=TOKENS["qa"], json_body={"status": "In Review"})
log("TC-LC-006", "Lifecycle", "In Review -> In Review (repeat) rejected", "PASS" if st == 409 else "FAIL", f"status={st}")

st, body = req("PATCH", f"/errors/{it_eid}/status", token=TOKENS["qa"], json_body={"status": "NotARealStatus"})
log("TC-LC-007", "Lifecycle", "Unrecognized status string rejected cleanly (was 500 crash, D-03)",
    "PASS" if st == 422 else ("FAIL" if st == 500 else "FAIL"), f"status={st} body={str(body)[:200]}",
    cause="" if st == 422 else "application bug (regression of fixed D-03)" if st == 500 else "unexpected status")

# drive to Closed then test closed-state rejections
req("PATCH", f"/errors/{it_eid}/status", token=TOKENS["qa"], json_body={"status": "QA Decision Pending"})
req("POST", f"/errors/{it_eid}/decision", token=TOKENS["qa"], json_body={"decision": "Rejected", "notes": "n"})
st, body = req("GET", f"/errors/{it_eid}", token=TOKENS["admin"])
closed_state = body.get("status")
st, body = req("PATCH", f"/errors/{it_eid}/status", token=TOKENS["qa"], json_body={"status": "Open"})
log("TC-LC-008", "Lifecycle", "Closed -> Open rejected", "PASS" if st == 409 else "FAIL", f"status={st} (was {closed_state})")

st, body = req("POST", f"/errors/{it_eid}/rebuttals", token=TOKENS["owner"], json_body={"justification": "too late"})
log("TC-LC-009", "Lifecycle", "Rebuttal on Closed error rejected", "PASS" if st == 409 else "FAIL", f"status={st}")

st, body = req("POST", f"/errors/{it_eid}/decision", token=TOKENS["qa"], json_body={"decision": "Resolved", "notes": "n"})
log("TC-LC-010", "Lifecycle", "Duplicate decision on Closed error rejected", "PASS" if st == 409 else "FAIL", f"status={st}")

# admin override
st, body = mk_error(title="Admin override test")
ao_eid = body["error_id"]
st, body = req("PATCH", f"/errors/{ao_eid}/status", token=TOKENS["qa"], json_body={"status": "QA Decision Pending", "admin_override": True})
log("TC-LC-011", "Lifecycle", "Non-admin admin_override:true silently ignored, normal rule applies (409)",
    "PASS" if st == 409 else "FAIL", f"status={st}")
st, body = req("PATCH", f"/errors/{ao_eid}/status", token=TOKENS["admin"], json_body={"status": "QA Decision Pending", "admin_override": True})
log("TC-LC-012", "Lifecycle", "Admin override actually skips state machine (Admin role)", "PASS" if st == 200 else "FAIL", f"status={st}")

with open("/tmp/audit_results_part2.json", "w") as f:
    json.dump(RESULTS, f, indent=2)
print(f"\nPart 2 (creation/validation/lifecycle) complete: {len(RESULTS)} checks.")
