# Async Durable Approval Gate

A small, local demo of a **human-in-the-loop approval gate** for high-stakes AI-agent actions. An agent can *propose* a $2,400 refund, an APR change on a funded deal, a 5,000-customer email, or a DMS write-back. A policy decides whether that can auto-approve. If it cannot, the workflow **pauses until a person approves or rejects it**, even if the worker process is killed in the meantime.

This is a **portfolio demo**, not production software. The inbox is a **mock Slack** screen, not real Slack. Approving an action only records a simulated side effect on this machine — it does not move money, email customers, or write to a dealer system.

Built for **Daniel McBrearty** as part of a Forward Deployed Engineer / solutions engineer portfolio. The sample company is **Lakeside Auto Group**, the same fictional mid-size dealer group used in the other portfolio demos.

## Why this matters for FDE work

Enterprises will not let an agent take an irreversible action without a person in the loop and a trail of who said yes.

That is a familiar idea in a dealership. A deal does not go out just because the form can be printed — a desk manager looks at it and signs off. A funded contract’s APR is not something you quietly edit. A $2,400 goodwill refund is not something a cashier decides alone.

After you scope the work and roll out an assistant, the FDE is often the person who has to answer: *what happens when the model wants to do something it cannot undo?* This demo is that control. The headline property is **durability**: if the process that was waiting for approval crashes, the request is not lost, and the refund is not issued twice.

## Quick start

You need Python 3.10+ (3.13 is fine) and a network connection the first time (to install packages and the Temporal CLI). No cloud account, no Slack workspace, no signup.

```bash
cd 07-approval-gate
./run.sh
```

That script will:

1. Download the [Temporal CLI](https://github.com/temporalio/cli) into `bin/temporal` if it is not already there (local dev server, no account).
2. Create a virtualenv and install `requirements.txt`.
3. Start `temporal server start-dev` with a local SQLite file so workflow history survives a server restart too.
4. Start the Python worker.
5. Open the Streamlit app at [http://localhost:8501](http://localhost:8501).

The optional Temporal Web UI is at [http://localhost:8233](http://localhost:8233). You do not need it for the demo; the mock Slack inbox is in the app.

To prove the durability headline, in a second terminal:

```bash
source .venv/bin/activate
python -m approvalgate crash-test
```

Unit tests (policy, idempotency, timeout, Slack-off-by-default). The crash/resume test also runs if `bin/temporal` is present:

```bash
python -m unittest discover -s tests
```

## What’s on the screen

- **Mock Slack inbox** — pending approval cards with Approve / Reject, a comment, and the policy reason. Clearly labeled as a mock.
- **Policy-driven routing** — refunds under $100 auto-approve; larger ones need a Desk Manager or Controller. APR changes and DMS write-backs always need a person. Small transactional email can auto-approve; a 5,000-customer blast cannot.
- **Timeout and escalation** — if the first approver is silent, the workflow escalates (for example, Controller → General Manager). If that window also expires, it **auto-rejects** and does not run the action. Use the “short-timeout refund” sample to watch this in seconds.
- **Dashboard** — pending, approved, rejected, timed out, and whether the side effect ran.
- **Audit log** — who, when, what, and why.
- **Idempotency key** — the final action is stored once. A double-click or a retried activity cannot issue a second refund.

## How it works

This demo uses **real Temporal**, running entirely on your machine.

1. The Streamlit app starts a Temporal **workflow** (`ApprovalGateWorkflow`) with a stable id derived from the proposal’s idempotency key.
2. The workflow evaluates the **policy** as a pure function (deterministic, no I/O, easy to test).
3. Auto-approve goes straight to the **side-effect activity**. Human-required proposals get a mock inbox row, then `workflow.wait_condition` until an Approve/Reject **signal** or a timer.
4. On timeout, the workflow escalates, waits again, and if still silent, marks the request `timed_out` and never executes.
5. The side effect writes to a local SQLite table with a **unique idempotency key**. Retries increment `attempt_count` and keep the original result.

```
Agent proposal
    → policy (auto-approve or require a human)
        → auto-approve → execute once
        → wait (durable) → Approve → execute once
                         → Reject  → do not execute
                         → timeout → escalate → wait again
                                              → timeout → auto-reject
```

If you kill the worker during the wait, Temporal still has the history. A new worker **replays** that history, lands on the same wait, and does not re-run the side effect. A signal sent while the worker is down is held by the server and delivered when it returns. That is what the crash test checks.

### Why Temporal (and not a SQLite-only engine)?

Temporal is the kind of tool many enterprises already trust for long-running, failure-tolerant work. The official CLI’s `temporal server start-dev` runs locally, for free, with no signup, which made it practical for this demo. The worker is disposable; the **server** is the source of truth.

A small event-sourced engine on SQLite could show the same idea, and that is a fair fallback if Temporal cannot be installed. Here, Temporal ran on this machine, so the demo uses the real thing. The local `data/approval_gate.db` file is only the human-readable audit log, the mock inbox, and the idempotency lock for the final action — not a replacement for the workflow server.

### Optional real Slack (off by default, never exercised)

The running inbox is a mock. `approvalgate/slack_adapter.py` is a documented seam for later. It stays off unless `APPROVAL_GATE_SLACK_ENABLED=true` and the usual Slack env vars are set, and even then this demo **refuses to post** rather than talk to Slack by accident. See `.env.example`.

## Honest limitations

- This is a **demo**. Lakeside Auto Group is fictional. “Executing” a refund is a row in a local database with the word `SIMULATED` in it.
- The inbox is **not Slack**. There is no workspace, no OAuth, and no interactive-message signature check.
- The policy is a **short list of rules**, not a customer’s real delegation of authority, SOX control, or fair-lending review.
- Timeouts are simple two-step escalation, then auto-reject. There is no reminder cadence, no out-of-office routing, and no two-person integrity rule.
- The Temporal server in this project is `start-dev`. It is not a production cluster, and the README for that command says so.
- Identity is a dropdown (“You are acting as Pat Kim, Controller”). There is no SSO, no real user, and no guarantee the clicker holds that role.
- One approval is enough. Some real refunds would need two signatures.

## What a production version would add

- Real Slack (or Teams, or email) interactive messages, with signed callbacks and a fallback if Slack is down
- SSO and a directory of who may approve which action, including dollar limits per role
- Two-person approval for high-dollar or compliance-sensitive changes (APR on a funded deal is a good example)
- A real, audited adapter to the payment system, email platform, and DMS — still behind the same idempotency key
- A production Temporal cluster (or equivalent) with HA, backups, and namespace-level isolation per customer
- Retention, e-discovery, and an export of the audit log for compliance
- Open-case dashboards for a controller, not only a demo inbox

## Project layout

```
07-approval-gate/
  app.py                 Streamlit UI (mock Slack inbox + dashboard)
  run.sh                 Starts Temporal, the worker, and the app
  requirements.txt
  README.md
  DEMO_SCRIPT.md
  approvalgate/          Policy, Temporal workflow, worker, crash test
  tests/
  screenshots/
  bin/temporal           Downloaded by run.sh (not committed)
```

## For interviewers

Start `./run.sh`, click **Refund $2,400**, switch to the mock Slack inbox, and talk through the policy reason. Then either approve it as the Controller, or (better, if there is time) mention that `python -m approvalgate crash-test` kills the worker mid-wait and still issues the refund only once. The talk track is in [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

Daniel’s background is car sales, F&I, and auto software sales (Dealr.cloud), not professional workflow-platform engineering. This project is meant to show he understands **why a human has to sign off, why that wait has to survive a crash, and why a second click must not refund twice**.
