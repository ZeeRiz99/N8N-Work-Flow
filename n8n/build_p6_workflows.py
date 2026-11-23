"""Builds the P6 workflow files: updates W1 (draft step, error workflow) and writes W4b and W9.

Run from n8n/: python build_p6_workflows.py. The JSON files are the source imported into n8n
by scripts/import-workflows.ps1; this script exists so the node wiring is reviewable as code.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent / "workflows"
SVC = {"httpHeaderAuth": {"id": "rlCredSvcKey0001", "name": "RL Backend Service Key"}}
HOOK = {"httpHeaderAuth": {"id": "rlCredWebhook001", "name": "RL Webhook Secret"}}
SMTP = {"smtp": {"id": "rlCredSmtp000001", "name": "RL SMTP"}}
ERR_WF = "rlW9ErrorMon0001"


def http(nid, name, pos, url, body=None, headers=None, never_error=False, timeout=30000):
    p = {
        "method": "POST",
        "url": url,
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "options": {"timeout": timeout},
    }
    if headers:
        p["sendHeaders"] = True
        p["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers]}
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    if never_error:
        p["options"]["response"] = {"response": {"neverError": True, "fullResponse": True}}
    return {
        "parameters": p,
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos,
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 2000,
        "credentials": SVC,
    }


def sticky(nid, text):
    return {
        "parameters": {"content": text, "height": 280, "width": 440},
        "id": nid,
        "name": "About this workflow",
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [-520, -280],
    }


def if_node(nid, name, pos, left, op_type, op, right=None):
    operator = {"type": op_type, "operation": op}
    if op in ("true", "false"):
        operator["singleValue"] = True
    cond = {"id": nid + "c", "leftValue": left, "operator": operator}
    if right is not None:
        cond["rightValue"] = right
    return {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [cond],
                "combinator": "and",
            },
            "options": {},
        },
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": pos,
    }


def email(nid, name, pos, to, subject, text, on_error=False):
    n = {
        "parameters": {
            "fromEmail": "__ALERT_EMAIL_FROM__",
            "toEmail": to,
            "subject": subject,
            "emailFormat": "text",
            "text": text,
            "options": {"appendAttribution": False},
        },
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.emailSend",
        "typeVersion": 2.1,
        "position": pos,
        "webhookId": nid,
        "credentials": SMTP,
    }
    if on_error:
        n["onError"] = "continueErrorOutput"  # output 0 = sent, output 1 = error
    return n


def link(*pairs):
    c: dict = {}
    for src, dst, out in pairs:
        c.setdefault(src, {"main": []})
        while len(c[src]["main"]) <= out:
            c[src]["main"].append([])
        c[src]["main"][out].append({"node": dst, "type": "main", "index": 0})
    return c


def save(name, data):
    (HERE / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8", newline="\n")


def build_w1():
    path = HERE / "rl-w1-lead-intake.json"
    w1 = json.loads(path.read_text(encoding="utf-8"))
    if any(n["name"] == "Draft reply (backend)" for n in w1["nodes"]):
        return  # already built
    w1["name"] = "RL | W1 | Lead Intake & Orchestration"
    w1["settings"]["errorWorkflow"] = ERR_WF
    nodes = {n["name"]: n for n in w1["nodes"]}
    nodes["About this workflow"]["parameters"]["content"] = (
        "## RL | W1 | Lead Intake & Orchestration\n"
        "**Trigger:** webhook `lead-created` from the backend (header `X-Webhook-Secret`).\n"
        "**Does:** analyze (Gemini, in the backend) -> if High: facts-only alert (email; "
        "Telegram once the bot exists) -> write a reply draft into the Approvals queue (the "
        "backend skips spam and job seekers) -> log the run.\n"
        "**Never sends a reply:** a person approves every draft. Redelivered events are "
        "handled once (idempotency keys)."
    )
    nodes["Log run (backend)"]["position"] = [1440, 0]
    lead = "$('Lead created').item.json.body"
    draft = http(
        "a1b2c3d4-0000-4000-8000-000000000008",
        "Draft reply (backend)",
        [1200, 0],
        f"=__BACKEND_URL__/api/v1/internal/leads/{{{{ {lead}.data.lead_id }}}}/drafts/generate",
        headers=[
            ("X-Request-ID", f"={{{{ {lead}.request_id }}}}"),
            ("Idempotency-Key", f"={{{{ {lead}.event_id }}}}:draft"),
        ],
        timeout=60000,
    )
    w1["nodes"].append(draft)
    log = nodes["Log run (backend)"]["parameters"]
    log["jsonBody"] = log["jsonBody"].replace(
        f"event_id: {lead}.event_id }}",
        f"event_id: {lead}.event_id, "
        "draft_id: $('Draft reply (backend)').item.json.draft_id || null, "
        "draft_skipped: $('Draft reply (backend)').item.json.skipped || null }",
    )
    to_draft = [{"node": "Draft reply (backend)", "type": "main", "index": 0}]
    w1["connections"]["High priority?"]["main"][1] = to_draft
    w1["connections"]["Email the team"]["main"][0] = to_draft
    w1["connections"]["Draft reply (backend)"] = {
        "main": [[{"node": "Log run (backend)", "type": "main", "index": 0}]]
    }
    save(path.name, w1)


def build_w4b():
    b = "b4b00000-0000-4000-8000-0000000000"
    d = "$('Draft approved').item.json.body"
    rid = [("X-Request-ID", f"={{{{ {d}.request_id }}}}")]
    hook = {
        "parameters": {
            "httpMethod": "POST",
            "path": "rl/draft-approved",
            "authentication": "headerAuth",
            "responseMode": "onReceived",
            "options": {},
        },
        "id": b + "01",
        "name": "Draft approved",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, 0],
        "webhookId": "5f3e2a10-6d2b-4c1a-9e7f-000000000b4b",
        "credentials": HOOK,
    }
    base = f"=__BACKEND_URL__/api/v1/internal/drafts/{{{{ {d}.data.draft_id }}}}"
    claim = http(b + "02", "Claim send (backend)", [240, 0], base + "/claim-send",
                 headers=rid, never_error=True)
    claimed = if_node(b + "03", "Claimed?", [480, 0], "={{ $json.statusCode }}", "number",
                      "equals", 200)
    send = email(b + "04", "Send email", [720, -100], "={{ $json.body.to }}",
                 "={{ $json.body.subject }}", "={{ $json.body.body }}", on_error=True)
    sent = http(b + "05", "Mark sent (backend)", [960, -200], base + "/mark-sent",
                body="={{ JSON.stringify({ provider_message_id: $json.messageId || null }) }}",
                headers=rid)
    failed = http(
        b + "06",
        "Mark failed (backend)",
        [960, 0],
        base + "/mark-failed",
        body=(
            "={{ JSON.stringify({ error: String(($json.error && ($json.error.message || "
            "$json.error)) || 'SMTP send failed').slice(0, 290) }) }}"
        ),
        headers=rid,
    )
    log = http(
        b + "07",
        "Log run (backend)",
        [1200, 0],
        "=__BACKEND_URL__/api/v1/internal/workflow-runs",
        body=(
            "={{ JSON.stringify({ workflow_key: 'W4b', n8n_execution_id: String($execution.id), "
            "status: $('Claimed?').item.json.statusCode === 200 ? ($json.status === 'sent' ? "
            "'success' : 'failed') : 'skipped', "
            f"request_id: {d}.request_id, lead_id: {d}.data.lead_id, "
            f"meta: {{ draft_id: {d}.data.draft_id, event_id: {d}.event_id, "
            "claim_status: $('Claimed?').item.json.statusCode, result: $json.status || null } "
            "}) }}"
        ),
        headers=rid,
    )
    save(
        "rl-w4b-send-approved-draft.json",
        {
            "id": "rlW4bSendDraft01",
            "name": "RL | W4b | Send Approved Draft",
            "active": False,
            "nodes": [
                sticky(
                    b + "00",
                    "## RL | W4b | Send Approved Draft\n**Trigger:** webhook `draft-approved` "
                    "from the backend.\n**Does:** claims the draft (atomic approved -> sending; "
                    "409 means already handled, stop) -> sends it by SMTP (Mailpit in dev) -> "
                    "reports sent with the message id, or failed with the error -> logs the "
                    "run.\n**Only approved drafts can be claimed.**",
                ),
                hook, claim, claimed, send, sent, failed, log,
            ],
            "connections": link(
                ("Draft approved", "Claim send (backend)", 0),
                ("Claim send (backend)", "Claimed?", 0),
                ("Claimed?", "Send email", 0),
                ("Claimed?", "Log run (backend)", 1),
                ("Send email", "Mark sent (backend)", 0),
                ("Send email", "Mark failed (backend)", 1),
                ("Mark sent (backend)", "Log run (backend)", 0),
                ("Mark failed (backend)", "Log run (backend)", 0),
            ),
            "settings": {"executionOrder": "v1", "saveManualExecutions": True,
                         "errorWorkflow": ERR_WF},
            "tags": [],
            "pinData": {},
        },
    )


def build_w9():
    e = "e9e90000-0000-4000-8000-0000000000"
    trig = {
        "parameters": {},
        "id": e + "01",
        "name": "On workflow error",
        "type": "n8n-nodes-base.errorTrigger",
        "typeVersion": 1,
        "position": [0, 0],
    }
    log = http(
        e + "02",
        "Log error (backend)",
        [240, 0],
        "=__BACKEND_URL__/api/v1/internal/workflow-errors",
        body=(
            "={{ JSON.stringify({ workflow_key: ((($json.workflow && $json.workflow.name) || "
            "'unknown').split('|')[1] || 'unknown').trim(), "
            "workflow_name: ($json.workflow && $json.workflow.name) || null, "
            "n8n_execution_id: String(($json.execution && $json.execution.id) || $execution.id), "
            "last_node: ($json.execution && $json.execution.lastNodeExecuted) || null, "
            "message: String(($json.execution && $json.execution.error && "
            "$json.execution.error.message) || 'unknown error').slice(0, 1900) }) }}"
        ),
    )
    should = if_node(e + "03", "Alert now?", [480, 0], "={{ $json.should_alert }}", "boolean",
                     "true")
    notify = email(e + "04", "Email the admin", [720, -100], "__ALERT_EMAIL_TO__",
                   "={{ $json.subject }}", "={{ $json.text }}")
    save(
        "rl-w9-error-monitor.json",
        {
            "id": ERR_WF,
            "name": "RL | W9 | Error Monitor",
            "active": False,
            "nodes": [
                sticky(
                    e + "00",
                    "## RL | W9 | Error Monitor\n**Trigger:** n8n Error Trigger (the error "
                    "workflow of every RL workflow).\n**Does:** logs the failed run to the "
                    "backend -> emails the admin only when the backend says `should_alert` "
                    "(once per workflow per 10 minutes; n8n keeps no state). Telegram replaces "
                    "email once the bot exists.",
                ),
                trig, log, should, notify,
            ],
            "connections": link(
                ("On workflow error", "Log error (backend)", 0),
                ("Log error (backend)", "Alert now?", 0),
                ("Alert now?", "Email the admin", 0),
            ),
            "settings": {"executionOrder": "v1", "saveManualExecutions": True},
            "tags": [],
            "pinData": {},
        },
    )


if __name__ == "__main__":
    build_w1()
    build_w4b()
    build_w9()
    print("built W1, W4b, W9")
