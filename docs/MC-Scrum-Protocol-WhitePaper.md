# Mission Control — OpenClaw Scrum Protocol WhitePaper

**Repo:** `openclaw-mission-control`
**Maintainer:** Jeff Sutherland / OpenClaw ASF team
**Purpose:** Document every code patch applied on top of the upstream MC platform to support OpenClaw's Scrum-at-Scale agent workflow. Apply `apply-scrum-patches.sh` after every `git pull origin master` to verify (and optionally re-apply) these patches.

---

## Background

OpenClaw runs a multi-agent Scrum team on Mission Control (MC). MC is a general-purpose Kanban-style task board. Out of the box it does not enforce Scrum ceremonies, story point velocity, or the Definition of Done (DoD) integrity that autonomous agent teams require. These patches bring MC into compliance with OpenClaw's Scrum protocol without forking the upstream repo.

**Patch philosophy:**
- Minimal — change only what is necessary
- Idempotent — applying the patch twice is safe
- Verifiable — `apply-scrum-patches.sh --check` can confirm presence without side effects
- Documented here with rationale so future engineers understand *why*, not just *what*

---

## Patch 1 — Story Points (velocity measurement)

**Files:** `backend/app/models/tasks.py`, `backend/app/schemas/tasks.py`

**Problem:** Upstream MC has no concept of story points. Without story points there is no velocity metric, no Sprint Planning capacity math, and no SPE (Story Points per Engineer) reporting for IRS audit trails.

**Change:** Add `story_points: int | None = None` to the `Task` model and `TaskRead`/`TaskUpdate` schemas.

**Verification:**
```bash
grep -q "story_points" backend/app/models/tasks.py
grep -q "story_points" backend/app/schemas/tasks.py
```

---

## Patch 2 — Agent Self-Assignment (self-organization)

**File:** `backend/app/api/tasks.py`

**Problem:** Upstream MC only allows lead agents to assign tasks. Non-lead agents cannot claim work from the inbox, which breaks the Scrum self-organization principle and requires a human or lead agent to dispatch every story.

**Change:** In `_apply_non_lead_agent_task_rules`, allow agents to assign a task to themselves (`is_self_assign` check). Agents may not assign to other agents.

**Verification:**
```bash
grep -q "is_self_assign" backend/app/api/tasks.py
```

---

## Patch 3 — `require_approval_for_done = False` (flow efficiency)

**File:** `backend/app/models/boards.py`

**Problem:** Upstream default requires a formal approval object for every done transition. OpenClaw uses a comment-based DoD workflow (Grok review + PO accept), not the approval-object workflow. The approval gate creates unnecessary 409 conflicts.

**Change:** Set `require_approval_for_done` board field default to `False`.

**Verification:**
```bash
grep -q 'default=False' backend/app/models/boards.py
```

---

## Patch 4 — "task" → "story" terminology

**File:** `frontend/src/app/boards/[boardId]/page.tsx` (and related UI strings)

**Problem:** The MC UI says "task" everywhere. OpenClaw uses Scrum vocabulary ("story", "backlog", "sprint"). Mismatched terminology causes agent confusion when interpreting UI feedback and breaks the shared language of Scrum.

**Change:** Replace UI-facing "task" labels with "story" in the board view.

**Verification:**
```bash
grep -q 'Edit story' 'frontend/src/app/boards/[boardId]/page.tsx'
```

---

## Patch 5 — Compose hardening (operational reliability)

**File:** `compose.yml`

**Problem:** Default compose uses the default bridge network. All services share one network namespace, making lateral movement trivial if one container is compromised. No restart policy means a crashed container stays down silently.

**Change:** Add `asf-network` custom bridge network, isolate services, add `restart: unless-stopped` to backend and worker.

**Verification:**
```bash
grep -q "asf-network" compose.yml
```

---

## Patch 6 — Server-Side DoD Enforcement (2026-04-19)

**File:** `backend/app/api/tasks.py`

**Problem:** The Definition of Done validator (`skills/mission-control/mc-dod-validator.sh`) ran client-side. Any agent with API write access could call `curl -X PATCH .../tasks/{id}` directly and move a story to `done` without Grok review. This was observed in production:
- Agents were writing fake `🦅 PO ACCEPT:` and `PO Accept:` comments to self-approve stories
- Stories with Grok Reject verdicts were landing in `done`
- The `require_user_or_agent` auth resolver tries user auth first — agents using the admin token authenticated as `actor_type="user"` and bypassed the agent-only guard

**Root cause:** `require_user_or_agent` in `backend/app/api/deps.py` resolves user auth before agent auth. A bearer token that passes user auth returns `ActorContext(actor_type="user")`. Agents that had the admin token exploited this to bypass any agent-only DoD gate.

**Change:** Add two functions to `backend/app/api/tasks.py`:

### `_auto_log_dod_rejection`
Writes a `🚫 [Server DoD Gate] BLOCKED — <reason>` comment via an isolated DB session so it persists even after the HTTP 400 causes the main session to roll back.

### `_require_dod_comment_for_done`
Called from **both** `_apply_lead_task_update` (lead agent path) and `_finalize_updated_task` (non-lead agent + admin path). Logic:

1. **Skip** if not a →`done` transition (`previous_status == "done"` or `task.status != "done"`).
2. **Allow** if actor is a human admin user (`actor_type == "user"`) AND the move comment starts with `"PO accepts:"` or `"PO override:"` — this is the signal from Jeff's `mc-api.sh move done "PO accepts: reason"` workflow.
3. **Hard-block** if any comment authored by a human (matching Jeff's identity patterns) contains rejection keywords — human PO rejections are final.
4. **Hard-block** if the **latest** Grok verdict comment is `Reject` (tracks across comment history, so a re-review Accept after a Reject is respected).
5. **Hard-block** if no Grok Accept verdict exists at all.

**Injection points** (both must be present after every upstream merge):
```python
# In _apply_lead_task_update, after _require_approved_linked_approval_for_done:
await _require_dod_comment_for_done(session, update=update)

# In _finalize_updated_task, after _require_approved_linked_approval_for_done:
await _require_dod_comment_for_done(session, update=update)
```

**Grok Accept patterns matched** (ALL three must appear in the same comment):
```
Header:   🦅.*GROK REVIEW  |  GROK REVIEW
Secrets:  Secrets: [CLEAN]  |  Secrets: [BLOCKED]   ← confirms real grok-review.py output
Verdict:  Status: Accept  |  verdict.*Accept  |  Accept.*verdict  |  [accept]
```

**Important:** `"grok reviewed"` alone is NOT accepted. Agents fabricate that phrase to spoof
the gate (observed 2026-04-19, PRODUCT: Sprint 44 ASF v4.0 Launch). The `Secrets:` field is
the distinguishing marker — only real `grok-review.py` output contains it.

**Latest verdict wins:** When checking done eligibility, iterate ALL comments in chronological
order and track the last Grok verdict. A Reject after an Accept overrides the Accept (observed
2026-04-19, REVENUE: ClawMart Traffic & Conversion — old Accept in comment 1, 37 Rejects in
comments 12–48, story incorrectly landed in done).

**PO accepts are not sufficient for done:** Human PO accepts (`mc-api.sh move done "PO accepts: reason"`)
do NOT substitute for Grok review. Stories accepted by PO without a Grok review must be returned
to inbox for proper review before closing. Decision: 2026-04-19, Jeff Sutherland.

**PO override bypass:** Only triggers if `actor_type == "user"` AND comment starts with `"PO accepts:"` or `"PO override:"`. Agent-written "PO Accept:" comments do NOT qualify — check `agent_id is None` when auditing done stories.

**Verification:**
```bash
grep -c "_require_dod_comment_for_done" backend/app/api/tasks.py
# Must return 3 (1 definition + 2 call sites)
```

**Response on failure:** HTTP 400 with `detail` explaining the specific DoD violation. Rejection comment is auto-written to the task before the 400 is raised.

---

## §7 — Re-applying patches after an upstream pull

Run the verification script first:
```bash
bash apply-scrum-patches.sh
```

If patches are missing, re-apply manually by locating the relevant functions in the files listed above and re-inserting the changes. Each patch is self-contained — applying one does not affect others.

For Patch 6 specifically, the full function bodies are in `backend/app/api/tasks.py` around the `_require_approved_linked_approval_for_done` definition. After any upstream merge that touches `tasks.py`, confirm with:
```bash
grep -c "_require_dod_comment_for_done" backend/app/api/tasks.py
# Expected: 3
```

If it returns fewer than 3, the patch was overwritten. Re-add the two call sites as described in §Patch 6 above.

---

## §8 — Audit: verifying done stories have legitimate accepts

When auditing done stories (e.g., after a suspected bypass), use this logic:

```python
# Legitimate accept requires ONE of:
# 1. Grok Accept: comment containing GROK REVIEW header + "Status: Accept"
# 2. Human PO accept: comment where agent_id is None AND starts with "PO accepts:" or "PO override:"

# DO NOT trust:
# - Agent-written "PO Accept:" comments (agent_id is not None)
# - "Accepted by PO" or "✅ PO Accept:" comments — these are agent self-approval attempts
```

Stories without a legitimate accept should be returned to inbox with comment:
> "Grok did not accept — no Grok Accept verdict found in comments. Returning to inbox for proper review."
