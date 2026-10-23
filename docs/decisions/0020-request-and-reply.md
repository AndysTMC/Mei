# 0020. The conversation is requests and replies; what Mei waits for is the input; details on demand

Status: accepted
Date: 2026-10-23
Deciders: owner
Supersedes: — (narrows §18.2's timeline of cards)
Superseded-by: —

## Context

§18.2 drew a conversation as a timeline: messages, then the agent's cards in place (activity, plan, approval, question, outcome, memory). In use, the owner found this noisy and confusing:
- One request could show two replies: the model's last words and then the task's summary.
- A green "Verified by Mei" card read like a third.
- Steps and checks were always on screen.
- Approvals sat in the chat as isolated boxes, and in the small popup they stayed after being answered.
- Voice showed as a bar inside the chat.

The owner asked for a standard rhythm (request, reply, request, reply), simplification rather than more elements, interactions that take the place of the input, and a mic for dictation separate from a voice button for conversation.

## Decision

- **A request gets one reply:** the latest thing Mei said for that task. The runtime makes a task's summary the reply only when the model's finishing turn said nothing, carrying that turn's model details.
- **Details are on demand:** what Mei said on the way, the steps it took, and how it checked the task are the reply's details. They sit behind icons under the reply (copy · regenerate · steps · checks · info), whose labels slide out on hover or focus. Each opens one panel below; one is open at a time. The checks icon itself signals a problem. While a task runs, its steps show beneath as progress, except a step waiting on the person.
- **What Mei waits for is the input:**
  - An approval or question replaces the message box and Ask, in both popup sizes, until answered.
  - **Approval:** "Mei wants to …", Details on demand, its scopes and Deny, and a field to decline and say what to do instead.
  - **Question:** its choices plus a field for any other answer, or its form and Send, or just an answer field.
  - If the answer doesn't reach Mei, it can be given again.
- **Mic and voice are two things:**
  - The mic dictates into the message box, to edit and send.
  - The voice button holds a conversation: Mei listens, answers out loud, and the box shows what voice is doing and heard. The same button then means Stop.
  - Each hides the other and Ask while it's in use.
  - The panel marks listening and speaking with a small icon beside "Mei".
- **Notices close:** they carry an action when there's a way forward (voice not ready: Set up), and clear when their cause does.
- **Monochrome everywhere:**
  - Greys, and the text's own color, inverted, as the one emphasis.
  - Standard symbolic icons; Mei ships only a waveform for voice, which Adwaita lacks.
  - Mei's Settings window uses the same accent rule.

## Consequences

- Most of a task is one line of text plus quiet icons. The trust model (§8.5: claim only what was checked) still holds: it lives in the Checks panel.
- The timeline model (`src/runtime/timeline.ts`) carries reply details and a separate pending interaction. The UI is rebuilt from it on every change, so a stale card can't linger in either popup size.
- The e2e test answers an approval from the small popup and checks there's one reply per request.
