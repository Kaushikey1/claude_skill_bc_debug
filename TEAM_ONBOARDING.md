# 👥 Team Onboarding: Trace Funnel Flow Skill

**Share this with your team.** It takes 5 minutes to set up.

---

## What Is This?

The **`/trace-funnel-flow`** skill lets you **instantly trace any statement/session** through the entire bank-connect pipeline and see:

✅ Which stages succeeded  
❌ Where it failed  
📍 The exact code location to check  
⏱️ How long each stage took  

**Example:**
```
/trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d --session <cookie>

→ Shows which of the 12 funnel stages this statement went through
→ Shows where it dropped off (if at all)
→ Links to the exact code file/line to debug
```

---

## ⚡ 5-Minute Setup

### 1️⃣ Get Your Grafana Session Cookie (2 min)

1. Open: https://grafana.tools.finbox.in
2. Press F12 (or Cmd+Option+I on Mac) to open DevTools
3. Click **Application** tab
4. Click **Cookies** on left
5. Find `grafana_session` and copy its value (looks like: `2cea150f40f6bad3a9a8a974d962a8a7`)
6. Keep this value handy

### 2️⃣ Try It Out (1 min)

```bash
# Run this in Claude Code:
/trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d --session <paste-your-cookie-here>

# You should see a report showing stages completed ✅
```

### 3️⃣ (Optional) Set Environment Variable (2 min)

Make it easier by setting once per session:
```bash
export GRAFANA_SESSION=<your-cookie>

# Then you can just run:
/trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d
```

**Done!** ✅

---

## 🎯 When to Use This

**Use when:**
- ❓ "Why isn't this statement processing?"
- ❓ "Where did this session drop off?"
- ❓ "Which stage is taking the longest?"
- ❓ "Is this entity stuck or just slow?"

**Don't use when:**
- Need real-time monitoring → use Grafana dashboards
- Need to query custom metrics → use Redash

---

## 📖 How to Read the Output

```
# Funnel Trace Report: f4d23fa0-5d0e-433a-8696-e528d45bb52d

## 📊 Summary
- Status: ✓ Complete              ← All stages completed successfully
- Stages Found: 6/6 completed     ← 6 out of 6 stages reached
- Conversion Rate: 100.0%         ← 100% conversion
- Audit Events: 29                ← Found 29 log events

## 🔗 Event Sequence

### 1. ✓ IDENTITY
- Started: 2026-08-05T19:15:47.380000
- Ended: 2026-08-05T19:15:48.059000
- Code: finboxdashboard/bank_connect/views.py:892-1029
                      ↑ Click here to see the code
```

---

## 🔴 Understanding Drop-offs

### Scenario 1: Drop-off at Identity

```
### 1. ✓ IDENTITY
- Started: 2026-08-05T19:15:47
- Ended: 2026-08-05T19:15:48    ← Identity completed

### 2. ⏳ EXTRACTION                ← STUCK HERE
- Started: 2026-08-05T19:15:50
                                  ← Never ended!

### 3. ❌ CATEGORIZATION
                                  ← Never even started
```

**What to do:**
1. The extraction stage is stuck/failed
2. Open the code location: `fsm-lambdas/python/handlers.py:156-241`
3. Look for errors in Grafana VictoriaLogs for this statement_id
4. Check if there are timeout/memory/API issues in that code

### Scenario 2: All Complete

```
### 1. ✓ IDENTITY
- Started: ...
- Ended: ...

### 2. ✓ EXTRACTION
- Started: ...
- Ended: ...

### 3. ✓ CATEGORIZATION
- Started: ...
- Ended: ...

# ... all stages have ✓
```

**What to do:**
- Everything succeeded! ✅
- If the user is still seeing issues, problem is elsewhere (not the pipeline)

---

## 🔑 The 12 Funnel Stages

Know these to quickly understand what each stage does:

| # | Stage | Does | If it fails |
|---|-------|------|-----------|
| 1 | **session** | Creates user session | User can't start |
| 2 | **identity** | Validates account | Account not found |
| 3 | **extraction** | Parses PDF statement | PDF corruption or timeout |
| 4 | **initiate_processing** | Queues the job | Job not queued |
| 5 | **post_processing** | Starts optimization | Can't optimize |
| 6 | **process_and_optimize_transactions** | Aggregates data | Data corruption |
| 7 | **elixir_pre_processing** | (Elixir-only) | Elixir parsing failed |
| 8 | **categorization** | Tags transactions | Can't categorize |
| 9 | **post_processing** | Final cleanup | Sync fails |
| 10 | **xlsx_report_v16** | Generates report | Report generation fails |
| 11 | **aggregate_xlsx_report_v3** | Aggregates report | Aggregation fails |
| 12 | **webhook_enrichment** | Sends webhook | Webhook call fails |

**If you see ⏳ at stage N, something is wrong in that stage's code.**

---

## 💡 Real-World Debugging Session

### Problem: "Statement X hasn't been processed in 30 min"

**Step 1: Get the UUID**
```
Statement ID: f4d23fa0-5d0e-433a-8696-e528d45bb52d
```

**Step 2: Run the skill**
```bash
/trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d --session <cookie>
```

**Step 3: Read the report**
```
### 3. ⏳ EXTRACTION
- Started: 2026-08-05T19:15:46.497000
                              ↑ Started 30+ min ago
- Ended: (empty)               ↑ But never ended!
- Code: fsm-lambdas/python/handlers.py:156-241
```

**Step 4: Debug**
1. Open: `fsm-lambdas/python/handlers.py:156-241`
2. Look for why extraction is taking so long or hanging
3. Check Grafana VictoriaLogs for errors at this stage
4. Check if there's a timeout/memory/API rate limit issue

---

## ⚠️ Important Notes

### Session Cookies Expire Every 1-2 Hours

If you get "Unauthorized" error:
1. Get a fresh cookie from Grafana (Step 1 of setup above)
2. Update your `GRAFANA_SESSION` env var

### Audit Logs Are Free-Text Searchable

The skill searches for your UUID anywhere in the logs, so:
- Works with: statement_id, session_id, entity_id, account_id, etc.
- Just paste the UUID and the skill finds it

### Old Logs (> 24 hours)

By default the skill searches the last 24 hours. For older logs, you can extend:
```bash
/trace-funnel-flow <uuid> --session <cookie> --hours 48
```

---

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| **"Unauthorized"** | Cookie expired → get fresh one from Grafana |
| **"No logs found"** | UUID wrong, too old (>24h), or not in logs |
| **"Only 1 stage"** | Try `--type session` if you have session_id instead |
| **Confusing output** | Refer to stage table above — see what each stage does |

---

## 📚 More Information

- **Full Setup Guide**: See `SETUP.md` in the repo
- **Quick Reference**: See `QUICK_REFERENCE.md` in the repo
- **Skill Documentation**: See `SKILL.md` in the repo
- **Python Script**: `.claude/scripts/trace_funnel_flow.py`

---

## ✅ Verification Checklist

After setup, confirm:
- [ ] I can access Grafana (https://grafana.tools.finbox.in)
- [ ] I got a fresh session cookie
- [ ] I ran the skill at least once
- [ ] I saw a report with stages listed
- [ ] I understand what ✓ and ⏳ mean

---

## 🎓 Next Steps

1. **Try it with your own UUIDs** from recent statements/sessions
2. **Share it with your team** — send them this guide
3. **Create debugging shortcuts** in your shell config:
   ```bash
   alias tf="/trace-funnel-flow"
   export GRAFANA_SESSION=<your-cookie>
   ```
4. **Use it when customers report issues** — trace → find stage → check code

---

## 🤝 Team Best Practices

**Rotate session cookies daily:**
```bash
# Put this in a team Slack bot or shared doc:
# "Fresh Grafana session for today: <cookie>"
# Team members update their env var once per day
```

**Share common debugging patterns:**
```
# Identity failing? Check: finboxdashboard/views.py:892-1029
# Extraction stuck? Check: fsm-lambdas/handlers.py:156-241
# Webhook not sent? Check: finboxdashboard/views.py:6617-6685
```

**Document weird cases:**
```
# Create a team runbook:
# "If extraction takes >5min, restart Lambda function X"
# "If identity fails, check DynamoDB for account Y"
```

---

## 🎉 You're Ready!

```bash
# Just run:
/trace-funnel-flow <any-uuid> --session <your-cookie>

# And you'll instantly see where that UUID's journey succeeded or failed
```

Questions? Refer to the guides above, or ask your team! 🚀
