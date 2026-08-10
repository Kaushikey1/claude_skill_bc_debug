# Setup Guide: Trace Funnel Flow Skill

This guide helps your team set up and use the **`/trace-funnel-flow`** skill in Claude Code.

---

## 📋 Prerequisites

- ✅ Claude Code CLI installed (claude.ai/code or IDE extension)
- ✅ Access to Grafana: https://grafana.tools.finbox.in
- ✅ Access to bank-connect repository

---

## 🚀 Step-by-Step Setup

### Step 1: Pull the Latest Repository

The skill is already in the repo at `.claude/skills/trace-funnel-flow/`. Just pull the latest code:

```bash
cd ~/kaushikeyGupta/bank_connect
git pull origin main
```

### Step 2: Get Grafana Session Cookie

**This is the ONLY thing you need to do once.**

1. Open **Grafana**: https://grafana.tools.finbox.in
2. Open **DevTools** (F12 or Cmd+Option+I)
3. Go to **Application** tab → **Cookies**
4. Filter for `grafana_session`
5. Copy the **value** (it looks like: `2cea150f40f6bad3a9a8a974d962a8a7`)

### Step 3: (Optional) Set Environment Variable

You can either:

**Option A: Set once per session** (recommended for daily use)
```bash
export GRAFANA_SESSION=<paste_your_cookie_here>
```

**Option B: Pass every time** (if you don't want to set env var)
```bash
/trace-funnel-flow <uuid> --session <paste_your_cookie_here>
```

---

## 🎯 Quick Start: Using the Skill

### Get a UUID
First, find a UUID from your data (statement_id, session_id, entity_id, etc.)

**Example UUIDs:**
- `f4d23fa0-5d0e-433a-8696-e528d45bb52d` (statement)
- `7e2d4393-0399-47f5-a7ea-e7d270a907f3` (session)

### Mode 1: Trace by Statement ID (Default)

```bash
/trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d --session 2cea150f40f6bad3a9a8a974d962a8a7
```

**Output:**
```
# Funnel Trace Report: f4d23fa0-5d0e-433a-8696-e528d45bb52d

## 📊 Summary
- Status: ✓ Complete
- Stages Found: 1/1 completed
- Conversion Rate: 100.0%
- Audit Events: 2

## 🔗 Event Sequence

### 1. ✓ IDENTITY
- Started: 2026-08-05T19:15:47.380000
- Ended: 2026-08-05T19:15:48.059000
- Code: finboxdashboard/bank_connect/views.py:892-1029
```

### Mode 2: Trace by Session ID

```bash
/trace-funnel-flow 7e2d4393-0399-47f5-a7ea-e7d270a907f3 --type session --session <your-cookie>
```

**Output shows all stages in the session** (identity → extraction → categorization → webhook_enrichment, etc.)

### Mode 3: Custom LogQL Query

```bash
/trace-funnel-flow any --type expr --expr '7e2d4393-0399-47f5-a7ea-e7d270a907f3 | sort by (_time) desc' --session <your-cookie>
```

---

## 📊 What the Output Tells You

### ✓ Complete Funnel
```
Status: ✓ Complete
Stages Found: 6/6 completed
Conversion Rate: 100.0%
```
→ This UUID successfully went through all 6 stages

### ❌ Drop-off Detected
```
Status: ❌ Drop-off detected
Stages Found: 3/6 completed
Conversion Rate: 50.0%
```
→ This UUID only reached 3 stages, then dropped off. Look at which stage is missing the "ended" event.

### Stage Details
```
### 3. ✓ EXTRACTION
- Started: 2026-08-05T19:15:46.497000
- Ended: 2026-08-05T19:16:12.665000
- Code: fsm-lambdas/python/handlers.py:156-241
```
→ Click on the code location to debug the stage

---

## 🔄 Troubleshooting

### "Unauthorized" Error

**Problem**: Session cookie expired  
**Solution**:
1. Get a **fresh** Grafana session cookie (from Step 2 above)
2. Update your `GRAFANA_SESSION` environment variable or pass `--session` again

### "No Audit Events Found"

**Problem**: UUID doesn't exist or is from > 24 hours ago  
**Solutions**:
- Check the UUID is correct
- Try searching by session ID instead of statement ID
- Verify the UUID is from the last 24 hours

### Confused About Results?

**Problem**: Not sure which stage failed  
**Solution**: Look for these patterns:
- ✓ means **started AND ended** (stage completed)
- ⏳ means **only started** (dropped off here)
- ❌ means **never even started** (previous stage must have failed)

---

## 📚 Real-World Examples

### Example 1: Debug Why a Statement Isn't Processing

```bash
# You notice statement f4d23fa0-5d0e-433a-8696-e528d45bb52d is stuck
/trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d --session <cookie>

# Report shows:
# ✓ IDENTITY - completed
# ⏳ EXTRACTION - started but never ended
# ❌ All other stages - never started

# → The extraction stage is stuck/failed
# → Open: fsm-lambdas/python/handlers.py:156-241
# → Look for errors in that range with this statement_id in Grafana
```

### Example 2: Check a User's Full Journey

```bash
# You want to trace user session 7e2d4393-0399-47f5-a7ea-e7d270a907f3
/trace-funnel-flow 7e2d4393-0399-47f5-a7ea-e7d270a907f3 --type session --session <cookie>

# Report shows all 6 stages with timings
# → You can see which stage is slowest
# → You can see which stage dropped off (if any)
```

### Example 3: Check Entity Processing

```bash
# You have entity_id abc123def456
/trace-funnel-flow abc123def456 --session <cookie>

# Shows the funnel progression for this entity
```

---

## 🎓 Understanding the Funnel Stages

**The 12 stages in order:**

1. **session** - User session created
2. **identity** - Account identity validated
3. **extraction** - Statement PDF parsed (Python or Elixir)
4. **initiate_processing** - Processing queued
5. **post_processing** - Initial processing started
6. **process_and_optimize_transactions** - Transaction optimization
7. **elixir_pre_processing** - (Only if Elixir extraction was used)
8. **categorization** - Transactions categorized
9. **post_processing** - Final cleanup
10. **xlsx_report_v16** - Report generated
11. **aggregate_xlsx_report_v3** - Report aggregated
12. **webhook_enrichment** - Webhook sent

**If a stage shows ❌ or ⏳**, that's where it dropped off. Check that stage's code location in the report.

---

## 💡 Tips for Your Team

### 1. **Share Your Grafana Session Regularly**
Since session cookies expire after ~1-2 hours, team members need fresh cookies.

**Best Practice:**
```bash
# Morning routine: get fresh cookie and export it
# Then share it with team Slack or docs
export GRAFANA_SESSION=$(curl -s https://grafana.tools.finbox.in/api/auth/login -X POST ... | jq -r '.sessionCookie')
```

### 2. **Create a Team Shortcut**
Save this to `~/.zshrc` or `~/.bashrc`:
```bash
alias trace-funnel="python3 ~/kaushikeyGupta/bank_connect/.claude/scripts/trace_funnel_flow.py"

# Then use:
trace-funnel <uuid> --session <cookie>
```

### 3. **Debug Workflow**
When someone reports "my statement is stuck":
1. Get their UUID
2. Run `/trace-funnel-flow <uuid> --session <cookie>`
3. Check which stage has ❌ or ⏳
4. Open the code location from the report
5. Search Grafana for error logs at that stage

### 4. **Keep Track of Common Issues**
Create a team doc like:
- "Statement stuck at extraction?" → Check fsm-lambdas/handlers.py
- "Identity failing?" → Check finboxdashboard/views.py
- "Webhook not sent?" → Check finboxdashboard/views.py:6617

---

## 📞 Support

If you hit issues:
1. Check the **Troubleshooting** section above
2. Verify your Grafana session is **fresh** (not expired)
3. Confirm the UUID **exists** and is from **last 24 hours**
4. Share the error message with the team

---

## ✅ Checklist: Team Setup

- [ ] All team members have Claude Code installed
- [ ] All team members can access Grafana: https://grafana.tools.finbox.in
- [ ] Each person got their own fresh session cookie
- [ ] Each person tested the skill once: `/trace-funnel-flow <test-uuid> --session <cookie>`
- [ ] Team has a shared doc of common debugging workflows
- [ ] Team understands the 12 funnel stages and what each does

---

## 🚀 You're Ready!

Your team can now trace any funnel issue end-to-end. Start with:

```bash
/trace-funnel-flow <uuid> --session <fresh-cookie>
```

Questions? Refer back to this guide or ask the team! 🎯
