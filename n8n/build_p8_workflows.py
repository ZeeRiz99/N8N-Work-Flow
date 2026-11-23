"""Builds the P8 workflows: W5 follow-ups, W6 recovery, W7 duplicate scan, W9b sweeper.

Run from n8n/: python build_p8_workflows.py. None of them can send a customer email: they only
ask the backend to prepare drafts (into the Approvals queue) or to sweep, and email the team.
"""

from build_p6_workflows import ERR_WF, email, http, if_node, link, save, sticky


def schedule(nid, name, rule):
    return {
        "parameters": {"rule": {"interval": [rule]}},
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [0, 0],
    }


def split(nid, name, pos, field="items"):
    return {
        "parameters": {"fieldToSplitOut": field, "options": {}},
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.splitOut",
        "typeVersion": 1,
        "position": pos,
    }


def log_run(nid, pos, key, meta):
    n = http(
        nid,
        "Log run (backend)",
        pos,
        "=__BACKEND_URL__/api/v1/internal/workflow-runs",
        body=(
            f"={{{{ JSON.stringify({{ workflow_key: '{key}', n8n_execution_id: "
            f"String($execution.id), status: 'success', meta: {meta} }}) }}}}"
        ),
    )
    n["executeOnce"] = True
    return n


def wf(wid, name, note, nodes, connections):
    return {
        "id": wid,
        "name": name,
        "active": False,
        "nodes": [sticky(wid + "n", note), *nodes],
        "connections": connections,
        "settings": {"executionOrder": "v1", "saveManualExecutions": True,
                     "errorWorkflow": ERR_WF},
        "tags": [],
        "pinData": {},
    }


def build_w5():
    p = "f5f50000-0000-4000-8000-0000000000"
    due = http(p + "02", "Due follow-ups (backend)", [240, 0],
               "=__BACKEND_URL__/api/v1/internal/follow-ups/due")
    due["parameters"]["method"] = "GET"
    each = split(p + "03", "Each follow-up", [480, 0])
    prep = http(p + "04", "Prepare (backend)", [720, 0],
                "=__BACKEND_URL__/api/v1/internal/follow-ups/{{ $json.id }}/prepare",
                timeout=60000)
    waiting = if_node(p + "05", "Draft waiting?", [960, 0], "={{ $json.status }}", "string",
                      "equals", "awaiting_approval")
    notify = email(p + "06", "Email the team", [1200, -100], "__ALERT_EMAIL_TO__",
                   "Replyline: follow-up drafts are waiting for approval",
                   "={{ 'Follow-up drafts are ready in Approvals. Nothing is sent until you "
                   "approve them.\\n' + '__FRONTEND_URL__/approvals' }}")
    notify["executeOnce"] = True
    log = log_run(p + "07", [1440, 0], "W5",
                  "{ prepared: $('Prepare (backend)').all().length }")
    save("rl-w5-follow-up-scheduler.json", wf(
        "rlW5FollowUps001", "RL | W5 | Follow-Up Scheduler",
        "## RL | W5 | Follow-Up Scheduler\n**Trigger:** every hour.\n**Does:** asks the backend "
        "for follow-ups that are due (only organizations inside their own business hours) -> "
        "for each, the backend checks the contact rules and skips with a reason or writes a "
        "draft for approval -> emails the team when drafts are waiting.\n**Never sends.**",
        [schedule(p + "01", "Every hour", {"field": "hours", "hoursInterval": 1}),
         due, each, prep, waiting, notify, log],
        link(("Every hour", "Due follow-ups (backend)", 0),
             ("Due follow-ups (backend)", "Each follow-up", 0),
             ("Each follow-up", "Prepare (backend)", 0),
             ("Prepare (backend)", "Draft waiting?", 0),
             ("Draft waiting?", "Email the team", 0),
             ("Draft waiting?", "Log run (backend)", 1),
             ("Email the team", "Log run (backend)", 0)),
    ))


def build_w6():
    p = "f6f60000-0000-4000-8000-0000000000"
    manual = {
        "parameters": {"httpMethod": "POST", "path": "rl/manual/W6",
                       "authentication": "headerAuth", "responseMode": "onReceived",
                       "options": {}},
        "id": p + "08", "name": "Run now (manual)", "type": "n8n-nodes-base.webhook",
        "typeVersion": 2, "position": [0, 200], "webhookId": "5f3e2a10-6d2b-4c1a-9e7f-0000000000w6",
        "credentials": {"httpHeaderAuth": {"id": "rlCredWebhook001",
                                           "name": "RL Webhook Secret"}},
    }
    cands = http(p + "02", "Recovery candidates (backend)", [240, 0],
                 "=__BACKEND_URL__/api/v1/internal/leads/recovery-candidates")
    cands["parameters"]["method"] = "GET"
    each = split(p + "03", "Each quiet lead", [480, 0])
    sug = http(p + "04", "Suggest check-in (backend)", [720, 0],
               "=__BACKEND_URL__/api/v1/internal/leads/{{ $json.lead_id }}/recovery-suggestion",
               timeout=60000)
    made = if_node(p + "05", "Draft written?", [960, 0], "={{ $json.draft_id }}", "string",
                   "exists")
    notify = email(p + "06", "Email the team", [1200, -100], "__ALERT_EMAIL_TO__",
                   "Replyline: check-in drafts for quiet leads",
                   "={{ 'Check-in drafts for leads that went quiet are waiting in Approvals.\\n' "
                   "+ '__FRONTEND_URL__/approvals' }}")
    notify["executeOnce"] = True
    log = log_run(p + "07", [1440, 0], "W6",
                  "{ suggested: $('Suggest check-in (backend)').all().length }")
    save("rl-w6-lost-lead-recovery.json", wf(
        "rlW6Recovery0001", "RL | W6 | Lost-Lead Recovery",
        "## RL | W6 | Lost-Lead Recovery\n**Trigger:** weekly (Monday 10:00) or manual webhook "
        "`rl/manual/W6`.\n**Does:** open leads quiet for 14+ days that may still be contacted "
        "-> a gentle check-in draft for each (reasons come from stored records, never guessed) "
        "-> Approvals queue -> email the team.\n**Never sends.**",
        [schedule(p + "01", "Weekly",
                  {"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1],
                   "triggerAtHour": 10}),
         manual, cands, each, sug, made, notify, log],
        link(("Weekly", "Recovery candidates (backend)", 0),
             ("Run now (manual)", "Recovery candidates (backend)", 0),
             ("Recovery candidates (backend)", "Each quiet lead", 0),
             ("Each quiet lead", "Suggest check-in (backend)", 0),
             ("Suggest check-in (backend)", "Draft written?", 0),
             ("Draft written?", "Email the team", 0),
             ("Draft written?", "Log run (backend)", 1),
             ("Email the team", "Log run (backend)", 0)),
    ))


def build_w7():
    p = "f7f70000-0000-4000-8000-0000000000"
    scan = http(p + "02", "Scan for duplicates (backend)", [240, 0],
                "=__BACKEND_URL__/api/v1/internal/duplicates/scan")
    new = if_node(p + "03", "New pairs?", [480, 0], "={{ $json.notify }}", "boolean", "true")
    notify = email(p + "04", "Email the team", [720, -100], "__ALERT_EMAIL_TO__",
                   "={{ $json.subject }}", "={{ $json.text }}")
    log = log_run(p + "05", [960, 0], "W7",
                  "{ added: $('Scan for duplicates (backend)').item.json.added }")
    save("rl-w7-duplicate-scan.json", wf(
        "rlW7DupScan00001", "RL | W7 | Duplicate Scan",
        "## RL | W7 | Duplicate Scan\n**Trigger:** daily 08:00.\n**Does:** the backend finds "
        "new possible duplicate pairs -> email the team only when there are new ones.\n"
        "**Never merges:** a person reviews every pair.",
        [schedule(p + "01", "Daily", {"field": "days", "daysInterval": 1, "triggerAtHour": 8}),
         scan, new, notify, log],
        link(("Daily", "Scan for duplicates (backend)", 0),
             ("Scan for duplicates (backend)", "New pairs?", 0),
             ("New pairs?", "Email the team", 0),
             ("New pairs?", "Log run (backend)", 1),
             ("Email the team", "Log run (backend)", 0)),
    ))


def build_w9b():
    p = "f9b90000-0000-4000-8000-0000000000"
    sweep = http(p + "02", "Redispatch outbox (backend)", [240, 0],
                 "=__BACKEND_URL__/api/v1/internal/outbox/redispatch")
    retry = http(p + "03", "Retry AI (backend)", [480, 0],
                 "=__BACKEND_URL__/api/v1/internal/leads/retry-ai", timeout=120000)
    log = log_run(p + "04", [720, 0], "W9b",
                  "{ requeued: $('Redispatch outbox (backend)').item.json.requeued, "
                  "dispatched: $('Redispatch outbox (backend)').item.json.dispatched, "
                  "stuck: $json.requeued_stuck, recovered: $json.recovered }")
    save("rl-w9b-retry-sweeper.json", wf(
        "rlW9bSweeper0001", "RL | W9b | Retry Sweeper",
        "## RL | W9b | Retry Sweeper\n**Trigger:** every 10 minutes.\n**Does:** requeues and "
        "delivers stalled outbox events, re-sends leads stuck by a crash, retries failed AI "
        "analyses (capped, idempotent).",
        [schedule(p + "01", "Every 10 minutes", {"field": "minutes", "minutesInterval": 10}),
         sweep, retry, log],
        link(("Every 10 minutes", "Redispatch outbox (backend)", 0),
             ("Redispatch outbox (backend)", "Retry AI (backend)", 0),
             ("Retry AI (backend)", "Log run (backend)", 0)),
    ))


if __name__ == "__main__":
    build_w5()
    build_w6()
    build_w7()
    build_w9b()
    print("built W5, W6, W7, W9b")
