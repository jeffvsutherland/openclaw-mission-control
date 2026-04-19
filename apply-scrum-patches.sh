#!/bin/bash
# apply-scrum-patches.sh — Verify (and optionally apply) Scrum protocol patches
# Run after every MC upstream pull (git pull origin master)
#
# Usage: bash apply-scrum-patches.sh [--apply]
#   Without --apply: Check-only mode (verify patches are present)
#   With --apply:    Attempt to apply missing patches
#
# See: docs/MC-Scrum-Protocol-WhitePaper.md for full rationale
set -euo pipefail
cd "$(dirname "$0")"

MISSING=0
APPLY="${1:-}"

echo "🔍 Checking Scrum protocol patches..."
echo ""

# ── Patch 1: Story Points ──────────────────────────────────────
echo "Patch 1: Story Points (velocity measurement)"
grep -q "story_points" backend/app/models/tasks.py && echo "  ✅ Model" || { echo "  ❌ MISSING Model"; MISSING=$((MISSING+1)); }
grep -q "story_points" backend/app/schemas/tasks.py && echo "  ✅ Schema" || { echo "  ❌ MISSING Schema"; MISSING=$((MISSING+1)); }

# ── Patch 2: Agent Self-Assignment ─────────────────────────────
echo "Patch 2: Agent Self-Assignment (self-organization)"
grep -q "is_self_assign" backend/app/api/tasks.py && echo "  ✅ Applied" || { echo "  ❌ MISSING"; MISSING=$((MISSING+1)); }

# ── Patch 3: require_approval_for_done = False ──────────────────
echo "Patch 3: require_approval_for_done = False (flow efficiency)"
grep -q 'default=False' backend/app/models/boards.py && echo "  ✅ Model" || { echo "  ❌ MISSING Model"; MISSING=$((MISSING+1)); }

# ── Patch 4: "task" → "story" terminology ───────────────────────
echo "Patch 4: task → story (correct mental model)"
grep -q 'Edit story' 'frontend/src/app/boards/[boardId]/page.tsx' 2>/dev/null && echo "  ✅ Applied" || { echo "  ❌ MISSING"; MISSING=$((MISSING+1)); }

# ── Patch 5: Compose hardening ──────────────────────────────────
echo "Patch 5: Compose hardening (operational reliability)"
grep -q "asf-network" compose.yml && echo "  ✅ Applied" || { echo "  ❌ MISSING"; MISSING=$((MISSING+1)); }

# ── Patch 6: Server-Side DoD Enforcement ────────────────────────
echo "Patch 6: Server-Side DoD Enforcement (prevent agent bypass of Grok review)"
DOD_COUNT=$(grep -c "_require_dod_comment_for_done" backend/app/api/tasks.py 2>/dev/null || echo 0)
if [ "$DOD_COUNT" -ge 3 ]; then
    echo "  ✅ Applied (definition + 2 call sites found)"
else
    echo "  ❌ MISSING or incomplete ($DOD_COUNT/3 occurrences) — see docs/MC-Scrum-Protocol-WhitePaper.md §Patch 6"
    MISSING=$((MISSING+1))
fi

# ── Custom module compatibility ──────────────────────────────────
echo ""
echo "Custom module compatibility:"
if grep -q "^from app.api.rate_limit_analytics" backend/app/main.py 2>/dev/null; then
    echo "  ⚠️  rate_limit_analytics: ENABLED — may crash if upstream deps changed"
elif grep -q "rate_limit_analytics" backend/app/main.py 2>/dev/null; then
    echo "  ✅ rate_limit_analytics: disabled (incompatible with upstream deps)"
else
    echo "  ✅ rate_limit_analytics: not present"
fi

# ── Summary ─────────────────────────────────────────────────────
echo ""
test "$MISSING" -eq 0 && echo "✅ All 6 Scrum protocol patches verified." || echo "❌ $MISSING patch(es) missing! See docs/MC-Scrum-Protocol-WhitePaper.md §7"
exit "$MISSING"
