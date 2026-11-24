"""Async Durable Approval Gate — Streamlit UI (mock Slack inbox + dashboard).

Run with ./run.sh  (starts Temporal, the worker, and this app)
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from approvalgate.client import get_snapshot, signal_decision, start_proposal, temporal_is_up
from approvalgate.models import ACTION_LABELS, ACTION_TYPES, PERSONAS, Proposal
from approvalgate.policy import evaluate
from approvalgate.samples import SAMPLES
from approvalgate.settings import COMPANY, temporal_ui_port
from approvalgate.slack_adapter import describe as slack_describe
from approvalgate.store import counts, get_execution, list_audit, workflow_rows
from approvalgate.worker_status import worker_seems_running

st.set_page_config(
    page_title="Approval Gate",
    page_icon="blueprint",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
  .block-container { padding-top: 1.2rem; max-width: 1280px; }
  .demo-banner {
    background: #fff6e5;
    border: 1px solid #e6d2a8;
    color: #5a4500;
    padding: 0.7rem 1rem;
    border-radius: 8px;
    font-size: 0.95rem;
    margin-bottom: 0.8rem;
  }
  .slack-card {
    background: #fff;
    border: 1px solid #d5dbe3;
    border-left: 4px solid #1e3a5f;
    border-radius: 10px;
    padding: 0.85rem 1rem 0.7rem;
    margin: 0 0 0.8rem;
  }
  .slack-card.escalated { border-left-color: #c47b2b; }
  .slack-label {
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #4a5a70;
    font-weight: 700;
    margin: 0 0 0.35rem;
  }
  .risk-high { color: #9b2c2c; font-weight: 700; }
  .risk-medium { color: #8a5a00; font-weight: 700; }
  .risk-low { color: #2a7f6f; font-weight: 700; }
  h1 { letter-spacing: -0.02em; }
  div[data-testid="stMetric"] {
    background: #f3f5f8;
    border: 1px solid #d5dbe3;
    border-radius: 10px;
    padding: 8px 12px;
  }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

STATUS_LABELS = {
    "waiting_primary": "Pending",
    "escalated": "Escalated",
    "approved": "Approved",
    "auto_approved": "Auto-approved",
    "rejected": "Rejected",
    "timed_out": "Timed out",
}


def _money(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"${float(value):,.0f}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
temporal_up = temporal_is_up()
worker_up = worker_seems_running()

with st.sidebar:
    st.header("How this works")
    st.markdown(
        """
An AI agent proposes a high-stakes action. A **policy** decides whether it can auto-approve or must wait for a person.

If a human is required, the workflow **pauses durably** in Temporal. Approving or rejecting happens in the **mock Slack inbox** on the right. If nobody answers, it **escalates**, then **auto-rejects**.

If you kill the worker mid-wait and start it again, the same approval is still there — and the final action still runs **at most once**.
        """
    )
    st.markdown("---")
    st.markdown("**Process status**")
    st.write("Temporal server:", "reachable" if temporal_up else "not reachable — start with `./run.sh`")
    st.write("Worker:", "running" if worker_up else "not detected — start with `./run.sh`")
    st.caption(f"Optional Temporal Web UI: http://127.0.0.1:{temporal_ui_port()}")
    st.caption(slack_describe())
    st.markdown("---")
    st.subheader("Propose an action")
    st.caption("These are sample asks from a fictional Lakeside Auto Group agent. Nothing is sent to a real bank, mailbox, or DMS.")
    if not temporal_up:
        st.warning("Temporal is not up, so new proposals cannot start.")
    for key, meta in SAMPLES.items():
        if st.button(meta["title"], key=f"sample_{key}", disabled=not temporal_up, use_container_width=True):
            proposal: Proposal = meta["factory"]()
            try:
                info = start_proposal(proposal)
                st.session_state["last_start"] = {
                    "title": proposal.title,
                    "workflow_id": info["workflow_id"],
                    "already_existed": info["already_existed"],
                    "policy": evaluate(proposal).reason,
                }
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not start workflow: {exc}")
    st.markdown("---")
    st.caption(f"Portfolio demo for Daniel McBrearty · {COMPANY}")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Async Durable Approval Gate")
st.caption(
    "Pause a high-stakes agent action until a person signs off. "
    "A portfolio demo — not a production control plane, and not connected to Slack."
)
st.markdown(
    '<div class="demo-banner">'
    "<strong>Honest label:</strong> this is a demo for "
    f"{COMPANY}. The inbox below is a <em>mock</em> of a Slack approval message, "
    "not real Slack. Approving a refund, APR change, email, or DMS write-back only "
    "records a simulated side effect on this machine. It does not move money, "
    "email customers, or write to a dealer system. Temporal runs locally with no account."
    "</div>",
    unsafe_allow_html=True,
)

if st.session_state.get("last_start"):
    last = st.session_state["last_start"]
    existed = " (same idempotency key was already running)" if last.get("already_existed") else ""
    st.info(f"Started: {last['title']}{existed}. Policy: {last['policy']}")

# ---------------------------------------------------------------------------
# Snapshot metrics
# ---------------------------------------------------------------------------
stats = counts()
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Pending", stats["pending"])
m2.metric("Approved", stats["approved"] + stats["auto_approved"])
m3.metric("Rejected", stats["rejected"])
m4.metric("Timed out", stats["timed_out"])
m5.metric("Actions executed", stats["executed"])

tab_inbox, tab_board, tab_audit, tab_custom = st.tabs(
    ["Mock Slack inbox", "Workflow dashboard", "Audit log", "Custom proposal"]
)

# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------
with tab_inbox:
    st.markdown("#### Mock Slack · `#approvals`")
    st.caption("This is not Slack. It is a stand-in for the interactive message an approver would get.")
    persona_labels = [f"{p['name']} · {p['role']}" for p in PERSONAS]
    who = st.selectbox("You are acting as", persona_labels, index=1)
    actor_name, actor_role = [part.strip() for part in who.split("·")]
    auto = st.checkbox("Auto-refresh this inbox every 3 seconds", value=False)

    def render_inbox():
        rows = [r for r in workflow_rows() if r["status"] in {"waiting_primary", "escalated"}]
        if not rows:
            st.write("No pending approvals. Propose an action from the sidebar — try the $2,400 refund.")
            return
        for row in rows:
            escalated = row["status"] == "escalated"
            role_needed = row["escalation_role"] if escalated else row["primary_role"]
            label = "MOCK SLACK · APPROVAL REQUEST" + (" · ESCALATED" if escalated else "")
            st.caption(label)
            st.markdown(f"**{row['title']}**")
            st.write(row["summary"])
            c1, c2, c3, c4 = st.columns(4)
            c1.write(f"Store: {row['store']}")
            c2.write(f"Department: {row['department']}")
            c3.write(f"Amount: {_money(row['amount_usd'])}")
            c4.markdown(
                f"Risk: <span class='risk-{row.get('risk') or 'medium'}'>{(row.get('risk') or '').upper()}</span>",
                unsafe_allow_html=True,
            )
            st.write(f"Requested by: {row['requested_by']}")
            st.write(f"Why the agent asked: {row['reason']}")
            st.info(row.get("policy_reason") or "")
            if escalated:
                st.warning(
                    f"Escalated to **{row['escalation_role']}** after no response from {row['primary_role']}."
                )
            else:
                st.caption(f"Waiting on **{role_needed}**. If nobody answers, this escalates, then auto-rejects.")
            comment_key = f"comment_{row['workflow_id']}"
            comment = st.text_input("Comment (optional, goes in the audit log)", key=comment_key)
            b1, b2, b3 = st.columns([1, 1, 3])
            with b1:
                if st.button("Approve", key=f"ok_{row['workflow_id']}", type="primary"):
                    try:
                        signal_decision(
                            row["workflow_id"],
                            "approve",
                            actor_name,
                            actor_role,
                            comment,
                        )
                        st.success("Approval sent. The worker will execute the action once.")
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Could not signal approval: {exc}")
            with b2:
                if st.button("Reject", key=f"no_{row['workflow_id']}"):
                    try:
                        signal_decision(
                            row["workflow_id"],
                            "reject",
                            actor_name,
                            actor_role,
                            comment or "Rejected.",
                        )
                        st.success("Rejection sent. The action will not run.")
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Could not signal rejection: {exc}")
            st.caption(f"Workflow `{row['workflow_id']}` · key `{row['idempotency_key']}`")
            st.markdown("---")

    if auto:
        @st.fragment(run_every=timedelta(seconds=3))
        def _auto_inbox():
            render_inbox()

        _auto_inbox()
    else:
        render_inbox()

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
with tab_board:
    rows = workflow_rows()
    if not rows:
        st.write("No workflows yet.")
    else:
        frame = pd.DataFrame(rows)
        frame["status_label"] = frame["status"].map(lambda s: STATUS_LABELS.get(s, s))
        frame["amount"] = frame["amount_usd"].map(_money)
        show = frame[
            [
                "updated_at",
                "title",
                "action_type",
                "store",
                "department",
                "amount",
                "status_label",
                "primary_role",
                "requested_by",
                "idempotency_key",
                "executed",
            ]
        ].rename(
            columns={
                "updated_at": "Updated (UTC)",
                "title": "Action",
                "action_type": "Type",
                "store": "Store",
                "department": "Department",
                "amount": "Amount",
                "status_label": "Status",
                "primary_role": "Approver role",
                "requested_by": "Requested by",
                "idempotency_key": "Idempotency key",
                "executed": "Executed?",
            }
        )
        st.dataframe(show, hide_index=True, use_container_width=True)
        pick = st.selectbox("Inspect a workflow", frame["workflow_id"].tolist())
        if pick and temporal_up:
            try:
                snap = get_snapshot(pick)
                st.json(snap)
            except Exception as exc:  # noqa: BLE001
                st.caption(f"Live Temporal snapshot unavailable: {exc}")
            execution = get_execution(frame.set_index("workflow_id").loc[pick, "idempotency_key"])
            if execution:
                st.success(
                    f"Side effect recorded once at {execution['first_executed_at']} "
                    f"(attempts: {execution['attempt_count']}): {execution['result']}"
                )

# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
with tab_audit:
    events = list_audit(250)
    if not events:
        st.write("No audit events yet.")
    else:
        audit = pd.DataFrame(events)
        st.dataframe(
            audit[
                ["ts", "event_type", "actor", "actor_role", "message", "workflow_id", "idempotency_key"]
            ].rename(
                columns={
                    "ts": "Time (UTC)",
                    "event_type": "Event",
                    "actor": "Who",
                    "actor_role": "Role",
                    "message": "What / why",
                    "workflow_id": "Workflow",
                    "idempotency_key": "Idempotency key",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.caption("This is the trail a compliance or F&I manager would want: who, when, what, and why.")

# ---------------------------------------------------------------------------
# Custom proposal
# ---------------------------------------------------------------------------
with tab_custom:
    st.markdown("#### Build your own proposal")
    with st.form("custom"):
        action_type = st.selectbox(
            "Action type",
            list(ACTION_TYPES),
            format_func=lambda k: ACTION_LABELS[k],
        )
        title = st.text_input("Title", value="Custom proposed action")
        summary = st.text_area("Summary", value="A custom high-stakes action for the demo.")
        reason = st.text_input("Why the agent wants this")
        department = st.selectbox("Department", ["Sales", "F&I", "Service", "Accounting", "Marketing", "IT / Support"])
        store = st.text_input("Store", value="Lakeside Honda")
        amount = st.number_input("Amount (USD, if applicable)", min_value=0.0, value=0.0, step=50.0)
        recipients = st.number_input("Recipient count (for email)", min_value=0, value=0, step=1)
        timeout = st.number_input("Approval timeout (seconds)", min_value=5, value=600, step=5)
        escalation = st.number_input("Escalation timeout (seconds)", min_value=5, value=600, step=5)
        submitted = st.form_submit_button("Submit to the approval gate", disabled=not temporal_up)
    if submitted:
        import uuid

        proposal = Proposal(
            idempotency_key=f"custom-{uuid.uuid4().hex[:10]}",
            action_type=action_type,
            title=title,
            summary=summary,
            reason=reason or "Custom demo proposal.",
            requested_by="Custom form (agent)",
            department=department,
            store=store,
            amount_usd=amount or None,
            recipient_count=int(recipients) or None,
            timeout_seconds=int(timeout),
            escalation_timeout_seconds=int(escalation),
        )
        try:
            info = start_proposal(proposal)
            st.session_state["last_start"] = {
                "title": proposal.title,
                "workflow_id": info["workflow_id"],
                "already_existed": info["already_existed"],
                "policy": evaluate(proposal).reason,
            }
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not start workflow: {exc}")

    st.markdown("#### Crash test")
    st.markdown(
        "To prove durability, from another terminal in this project folder run:\n\n"
        "```bash\npython -m approvalgate crash-test\n```\n\n"
        "That script starts its own Temporal server, submits a $2,400 refund, **kills the worker**, "
        "restarts it, approves the same workflow, and checks that the refund simulated **exactly once**."
    )

with st.expander("How the math / durability works"):
    st.markdown(
        """
- **Policy.** A small rules engine: refunds under $100 auto-approve; $100–$999 need a Desk Manager; $1,000+ need a Controller. APR changes and DMS write-backs always need a person. Bulk email under 25 recipients can auto-approve; 25 or more needs Marketing.
- **Durable wait.** Temporal records the workflow history. `wait_condition` is a timer + a signal. If the worker dies, the server keeps the state. A new worker replay the history and sits on the same wait — it does not start over, and it does not run the side effect.
- **Signals.** Approve / Reject is a Temporal signal. If you click while the worker is down, Temporal holds the signal and delivers it when the worker returns.
- **Idempotency.** The final side effect is keyed by `idempotency_key` in SQLite with a unique constraint. A retried activity or a double-click cannot insert a second refund.
- **Timeout.** If the first approver is silent, the workflow escalates. If the second window also expires, it auto-rejects and never executes.
        """
    )
