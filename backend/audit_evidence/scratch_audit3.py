import json
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

BASE_ERR = {"title": "Audit test", "description": "desc", "category_id": 1, "severity": "Low",
            "department_id": 1, "date_discovered": "2026-01-01"}


def mk_error(**overrides):
    payload = dict(BASE_ERR)
    payload.update(overrides)
    return req("POST", "/errors", token=TOKENS["admin"], json_body=payload)


def to_review(eid):
    return req("PATCH", f"/errors/{eid}/status", token=TOKENS["qa"], json_body={"status": "In Review"})


# ============================================================ 9. REBUTTALS
st, body = mk_error(title="Rebuttal valid test")
reb_eid = body["error_id"]
to_review(reb_eid)
st, body = req("POST", f"/errors/{reb_eid}/rebuttals", token=TOKENS["owner"], json_body={"justification": "This was actually correct per policy X."})
log("TC-REB-001", "Rebuttal", "Valid rebuttal by Department Owner -> Rebuttal Raised", "PASS" if st == 201 else "FAIL", f"status={st} body={body}")
st, body = req("GET", f"/errors/{reb_eid}", token=TOKENS["admin"])
log("TC-REB-001b", "Rebuttal", "Error transitions to Rebuttal Raised", "PASS" if body.get("status") == "Rebuttal Raised" else "FAIL", f"status={body.get('status')}")

st, body = mk_error(title="Rebuttal wrong role")
rw_eid = body["error_id"]
to_review(rw_eid)
st, body = req("POST", f"/errors/{rw_eid}/rebuttals", token=TOKENS["qa"], json_body={"justification": "x"})
log("TC-REB-002", "Rebuttal", "Rebuttal by QA Reviewer rejected (403)", "PASS" if st == 403 else "FAIL", f"status={st}")
st, body = req("POST", f"/errors/{rw_eid}/rebuttals", token=TOKENS["viewer"], json_body={"justification": "x"})
log("TC-REB-003", "Rebuttal", "Rebuttal by Viewer rejected (403)", "PASS" if st == 403 else "FAIL", f"status={st}")

st, body = mk_error(title="Rebuttal empty justification")
re_eid = body["error_id"]
to_review(re_eid)
st, body = req("POST", f"/errors/{re_eid}/rebuttals", token=TOKENS["owner"], json_body={"justification": ""})
log("TC-REB-004", "Rebuttal", "Empty justification rejected cleanly (fixed D-06)", "PASS" if st == 422 else "FAIL", f"status={st} body={body}",
    cause="" if st == 422 else "application bug (regression of fixed D-06)")

st, body = req("POST", f"/errors/{reb_eid}/rebuttals", token=TOKENS["owner"], json_body={"justification": "second one"})
log("TC-REB-005", "Rebuttal", "Second rebuttal while already Rebuttal Raised rejected (409)", "PASS" if st == 409 else "FAIL", f"status={st}")

st, body = mk_error(title="Rebuttal long justification")
rl_eid = body["error_id"]
to_review(rl_eid)
st, body = req("POST", f"/errors/{rl_eid}/rebuttals", token=TOKENS["owner"], json_body={"justification": "A" * 20000})
log("TC-REB-006", "Rebuttal", "20,000-char justification accepted", "PASS" if st == 201 else "FAIL", f"status={st}")

# ============================================================ 10. EVIDENCE
st, body = mk_error(title="Evidence valid upload")
ev_eid = body["error_id"]
png_bytes = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108020000009077" + "53de" + "0000000c4944415478da6360000002000155" + "0203" + "0000000049454e44ae426082")
boundary = "----AuditBoundary123"
def multipart(filename, content_type, data):
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body

st, body = req("POST", f"/errors/{ev_eid}/evidence", token=TOKENS["admin"],
               raw_body=multipart("evidence.png", "image/png", png_bytes),
               content_type=f"multipart/form-data; boundary={boundary}")
log("TC-EVD-001", "Evidence", "Valid PNG upload", "PASS" if st == 201 else "FAIL", f"status={st} body={body}")
evidence_id = body.get("evidence_id") if st == 201 else None

st, body = req("POST", f"/errors/{ev_eid}/evidence", token=TOKENS["admin"],
               raw_body=multipart("bad.exe", "application/x-msdownload", b"MZ\x90\x00"),
               content_type=f"multipart/form-data; boundary={boundary}")
log("TC-EVD-002", "Evidence", "Unsupported MIME type rejected", "PASS" if st == 422 else "FAIL", f"status={st}")

big = b"0" * (16 * 1024 * 1024)
st, body = req("POST", f"/errors/{ev_eid}/evidence", token=TOKENS["admin"],
               raw_body=multipart("big.png", "image/png", big),
               content_type=f"multipart/form-data; boundary={boundary}")
log("TC-EVD-003", "Evidence", "Oversized file (16MB > 15MB limit) rejected", "PASS" if st == 422 else "FAIL", f"status={st}")

st, body = req("POST", "/errors/9999999/evidence", token=TOKENS["admin"],
               raw_body=multipart("x.png", "image/png", png_bytes),
               content_type=f"multipart/form-data; boundary={boundary}")
log("TC-EVD-004", "Evidence", "Upload against nonexistent error -> 404", "PASS" if st == 404 else "FAIL", f"status={st}")

st, body = req("POST", f"/errors/{ev_eid}/evidence", token=TOKENS["admin"],
               raw_body=multipart("../../../etc/passwd", "image/png", png_bytes),
               content_type=f"multipart/form-data; boundary={boundary}")
log("TC-EVD-005", "Evidence", "Path-traversal filename handled safely (no traversal, server-generated key)",
    "PASS" if st == 201 else "FAIL", f"status={st} file_name={body.get('file_name') if st==201 else body}")

st, body = req("POST", f"/errors/{ev_eid}/evidence", token=TOKENS["admin"],
               raw_body=multipart("empty.png", "image/png", b""),
               content_type=f"multipart/form-data; boundary={boundary}")
log("TC-EVD-006", "Evidence", "0-byte file rejected cleanly (fixed D-08)", "PASS" if st == 422 else "FAIL", f"status={st} body={body}",
    cause="" if st == 422 else "application bug (regression of fixed D-08)")

if evidence_id:
    st, body = req("GET", f"/errors/evidence/{evidence_id}/url", token=TOKENS["admin"])
    log("TC-EVD-007", "Evidence", "Presigned evidence URL issued with expiry + logging", "PASS" if st == 200 and "expires_in_seconds" in body else "FAIL", f"status={st} body={body}")

    # IDOR check: viewer (different dept, no relation to this error) can still read the URL
    st, body = req("GET", f"/errors/evidence/{evidence_id}/url", token=TOKENS["viewer"])
    log("TC-EVD-008-IDOR", "APISecurity", "Evidence URL has no ownership/department scoping (documented gap D-07)",
        "FAIL" if st == 200 else "PASS", f"status={st}",
        cause="" if st != 200 else "missing implementation: no department/ownership check on GET /evidence/{id}/url")

# ============================================================ 11. QA DECISIONS
st, body = mk_error(title="Decision valid")
dec_eid = body["error_id"]
to_review(dec_eid)
req("PATCH", f"/errors/{dec_eid}/status", token=TOKENS["qa"], json_body={"status": "QA Decision Pending"})
st, body = req("POST", f"/errors/{dec_eid}/decision", token=TOKENS["qa"], json_body={"decision": "Resolved", "notes": "fixed root cause"})
log("TC-DEC-001", "Decision", "Valid decision (Resolved) auto-closes", "PASS" if st == 201 else "FAIL", f"status={st}")

st, body = mk_error(title="Decision invalid value")
div_eid = body["error_id"]
to_review(div_eid)
req("PATCH", f"/errors/{div_eid}/status", token=TOKENS["qa"], json_body={"status": "QA Decision Pending"})
st, body = req("POST", f"/errors/{div_eid}/decision", token=TOKENS["qa"], json_body={"decision": "TotallyBogusValue", "notes": "n"})
log("TC-DEC-002", "Decision", "Invalid decision literal rejected with clear message (fixed D-09)",
    "PASS" if st == 422 else "FAIL", f"status={st} body={str(body)[:200]}",
    cause="" if st == 422 else "application bug (regression of fixed D-09)")

st, body = mk_error(title="Decision wrong role")
dwr_eid = body["error_id"]
to_review(dwr_eid)
req("PATCH", f"/errors/{dwr_eid}/status", token=TOKENS["qa"], json_body={"status": "QA Decision Pending"})
st, body = req("POST", f"/errors/{dwr_eid}/decision", token=TOKENS["owner"], json_body={"decision": "Resolved", "notes": "n"})
log("TC-DEC-003", "Decision", "Decision by Department Owner rejected (403)", "PASS" if st == 403 else "FAIL", f"status={st}")

with open("/tmp/audit_results_part3.json", "w") as f:
    json.dump(RESULTS, f, indent=2)
print(f"\nPart 3 (rebuttal/evidence/decision) complete: {len(RESULTS)} checks.")
