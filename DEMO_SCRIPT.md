# Demo script (~1 minute)

A talk track you can say out loud in an interview. Plain language. Practice it once with the app open. You do not need to memorize it word for word.

**Setup:** `./run.sh` is already running. You will click **Refund $2,400 (needs approval)** in the sidebar, then open the **Mock Slack inbox** tab.

---

## The talk track

“In F&I, a deal doesn’t just go out because the computer can print it. A desk manager looks at it and signs off. That’s the same idea here, for an AI agent.

If an assistant wants to issue a $2,400 customer refund, or change the APR on a deal that’s already funded, or email five thousand customers, it shouldn’t just do it. This gate pauses that action until a person approves it. The policy is a simple rulebook — a forty-five-dollar goodwill refund can go through on its own; twenty-four hundred dollars has to go to a controller.

The inbox you’re looking at is a mock Slack message, not the real thing. I click Approve or Reject, I can leave a comment, and that becomes part of the audit log: who, when, what, and why.

The part I care about most is what happens if the process crashes while we’re waiting. This is running on Temporal, locally, no cloud account. If I kill the worker mid-wait and start it again, the same approval is still sitting there, and when someone finally approves, the refund is simulated exactly once. A second click doesn’t pay it twice. That’s the ‘durable’ in the name, and that’s what a customer is going to ask about before they let an agent near money or the DMS.”

---

## Timing notes

Spoken at a normal pace, that is about 50–60 seconds. If you have a few extra seconds, point at the policy reason on the $2,400 card (“a Controller must sign off”) and at the idempotency key under the buttons. Then stop and let them ask questions.

If you have two minutes, run `python -m approvalgate crash-test` in a terminal *before* the meeting so you can show the PASS lines, or walk through what the script does without waiting on it live.

## If they ask a follow-up

- **“Why Temporal?”**  
  “Because the wait has to live outside the web process. Temporal is what a lot of enterprises already use for that: the worker can die, the history doesn’t. It also runs on a laptop with `temporal server start-dev` and no signup, which is why I used the real thing instead of faking a workflow engine.”

- **“Why not just a row in a database?”**  
  “A row can store ‘pending,’ but you still have to get the timeouts, the crash recovery, the signals, and the ‘run this once’ part right yourself. That’s what Temporal is doing here. The SQLite file is the audit log and the idempotency lock, not the workflow brain.”

- **“What if they click Approve twice?”**  
  “The first signal wins in the workflow, and the side effect table has a unique key. The second click doesn’t issue a second refund. That’s in the crash test.”

- **“Is this real Slack?”**  
  “No, and I label it as a mock. There’s a documented seam for real Slack later, but it’s off by default and this demo won’t post even if you turn the flag on. I didn’t want a portfolio project talking to a real workspace by accident.”

- **“What would you do on a real dealer group?”**  
  “Agree the dollar limits and who can approve what — desk manager vs controller vs GM — the same way they already delegate deals. Put real Slack or a dealer inbox in front. And put the actual refund or DMS write behind the same idempotency key, with SSO so ‘Pat Kim, Controller’ is really Pat Kim.”
