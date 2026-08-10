# 🚀 Trace Funnel Flow - Quick Reference Card

## One-Minute Setup

```bash
# 1. Get fresh Grafana session cookie:
#    • Open https://grafana.tools.finbox.in
#    • DevTools → Application → Cookies → grafana_session → Copy value

# 2. Set it:
export GRAFANA_SESSION=<your-cookie-here>

# 3. Done! ✅
```

---

## Usage (Copy & Paste)

### Trace Statement/Entity
```bash
/trace-funnel-flow <statement-id> --session <cookie>

# Example:
/trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d --session 2cea150f40f6bad3a9a8a974d962a8a7
```

### Trace Session
```bash
/trace-funnel-flow <session-id> --type session --session <cookie>

# Example:
/trace-funnel-flow 7e2d4393-0399-47f5-a7ea-e7d270a907f3 --type session --session 2cea150f40f6bad3a9a8a974d962a8a7
```

### Custom Query
```bash
/trace-funnel-flow any --type expr --expr '<logql>' --session <cookie>
```

---

## What to Look For in Output

| Output | Meaning |
|--------|---------|
| **✓ STAGE_NAME** | Stage completed (started AND ended) |
| **⏳ STAGE_NAME** | Stage started but NEVER ENDED → **dropped off here** |
| **❌ STAGE_NAME** | Stage never even started |

---

## Read the Report

```
# Funnel Trace Report: f4d23fa0-5d0e-433a-8696-e528d45bb52d

## 📊 Summary
- Status: ✓ Complete          ← All stages completed
- Stages Found: 6/6 completed ← 6 out of 6 stages
- Conversion Rate: 100.0%     ← Everything worked
- Audit Events: 29            ← Found 29 log events

## 🔗 Event Sequence

### 1. ✓ IDENTITY
- Started: 2026-08-05T19:15:47.380000
- Ended: 2026-08-05T19:15:48.059000
- Code: finboxdashboard/bank_connect/views.py:892-1029  ← Click to debug
```

---

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| "Unauthorized" | Cookie expired → Get fresh one from Grafana |
| "No logs found" | UUID too old or wrong → Check UUID format |
| "Only 1 stage found" | Try `--type session` instead |
| Not sure what to check | Open the "Code" location → read that stage |

---

## The 12 Funnel Stages (In Order)

1. **session** → User session created
2. **identity** → Account validated
3. **extraction** → Statement parsed
4. **initiate_processing** → Processing queued
5. **post_processing** → Optimization started
6. **process_and_optimize_transactions** → Data optimized
7. **elixir_pre_processing** → (Elixir-only, conditional)
8. **categorization** → Transactions categorized
9. **post_processing** → Final cleanup
10. **xlsx_report_v16** → Report generated
11. **aggregate_xlsx_report_v3** → Report aggregated
12. **webhook_enrichment** → Webhook sent

**If any stage is ⏳, that's where it stopped.**

---

## Three-Step Debug Workflow

```
1. Get UUID from data
2. Run: /trace-funnel-flow <uuid> --session <cookie>
3. Look for ⏳ or ❌ in output
   → Open code location from report
   → Search Grafana for errors at that stage
```

---

## Set It Up Once, Use Forever

```bash
# In your ~/.zshrc or ~/.bashrc:
export GRAFANA_SESSION=<your-cookie>
alias tf="/trace-funnel-flow"

# Then just:
tf <uuid>
```

---

## Need Fresh Cookie?

```bash
# Cookies expire every 1-2 hours
# Get new one from: https://grafana.tools.finbox.in
# DevTools → Application → Cookies → grafana_session

export GRAFANA_SESSION=<new-cookie>
```

---

## More Help?

- 📖 Full setup: See `SETUP.md`
- 📚 Detailed guide: See `SKILL.md`
- 💻 Code: `.claude/scripts/trace_funnel_flow.py`
