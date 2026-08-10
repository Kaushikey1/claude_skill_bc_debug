# Trace Funnel Flow Skill 🚀

**Instantly trace any statement/session through the entire bank-connect pipeline and find drop-off points.**

---

## 📖 Documentation

Pick the guide that fits your needs:

### 👥 **For Your Team** (Start Here!)
📄 **[TEAM_ONBOARDING.md](TEAM_ONBOARDING.md)** — Share this with everyone  
- 5-minute setup guide
- Explains what the skill does
- Shows how to read the output
- Real-world debugging examples

### ⚡ **Quick & Dirty**
📄 **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** — Copy-paste commands  
- One-minute cheat sheet
- Common issues & fixes
- Commands to copy/paste
- Keyboard reference card

### 🎓 **Full Setup & Usage**
📄 **[SETUP.md](SETUP.md)** — Detailed walkthrough  
- Step-by-step setup
- All three usage modes
- Troubleshooting guide
- Team best practices

### 📚 **Complete Documentation**
📄 **[SKILL.md](SKILL.md)** — Comprehensive reference  
- Architecture details
- Funnel stages (in order)
- Grafana integration
- Performance metrics

---

## 🚀 Quick Start (30 seconds)

```bash
# 1. Get Grafana session cookie:
#    → https://grafana.tools.finbox.in
#    → DevTools → Application → Cookies → grafana_session
#    → Copy the value

# 2. Run the skill:
/trace-funnel-flow <uuid> --session <your-cookie>

# 3. Read the report and find where it dropped off ✅
```

---

## 📊 What You Get

```
# Funnel Trace Report: f4d23fa0-5d0e-433a-8696-e528d45bb52d

## 📊 Summary
- Status: ✓ Complete
- Stages Found: 6/6 completed
- Conversion Rate: 100.0%
- Audit Events: 29

## 🔗 Event Sequence

### 1. ✓ IDENTITY
- Started: 2026-08-05T19:15:47.380000
- Ended: 2026-08-05T19:15:48.059000
- Code: finboxdashboard/bank_connect/views.py:892-1029

### 2. ✓ EXTRACTION
- Started: 2026-08-05T19:15:46.497000
- Ended: 2026-08-05T19:16:12.665000
- Code: fsm-lambdas/python/handlers.py:156-241

# ... 10 more stages ...
```

✅ = Stage completed (started AND ended)  
⏳ = Stage stuck (started but never ended)  
❌ = Stage never started  

---

## 💡 Three Ways to Use

### 1. Trace by Statement ID (Default)
```bash
/trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d --session <cookie>
```

### 2. Trace by Session ID
```bash
/trace-funnel-flow 7e2d4393-0399-47f5-a7ea-e7d270a907f3 --type session --session <cookie>
```

### 3. Custom LogQL Query
```bash
/trace-funnel-flow any --type expr --expr '<your-logql>' --session <cookie>
```

---

## 🎯 Use Cases

**Debugging a Stuck Statement**
→ `/trace-funnel-flow <id> --session <cookie>`  
→ Find which stage has ⏳  
→ Open the code location  
→ Debug that stage  

**Understanding a User's Journey**
→ `/trace-funnel-flow <session-id> --type session --session <cookie>`  
→ See all 12 stages they went through  
→ See timings for each stage  

**Checking Population Health**
→ Create a custom query with LogQL  
→ Filter by bank, time range, etc.  
→ Count success rate per stage  

---

## 🔧 How It Works

1. **Fetches logs** from Grafana VictoriaLogs using your session cookie
2. **Parses audit logs** for "Emitted audit log:" entries
3. **Reconstructs the funnel** by matching start/end events per stage
4. **Maps to code** using the verified stage→file table
5. **Generates a report** with timeline, durations, and code locations

**No complex setup.** Just a UUID and a session cookie.

---

## 📋 The 12 Funnel Stages

| # | Stage | What It Does | Code Location |
|---|-------|-------------|----------------|
| 1 | **session** | Creates session | finboxdashboard/views.py:10050 |
| 2 | **identity** | Validates account | finboxdashboard/views.py:892-1029 |
| 3 | **extraction** | Parses PDF | fsm-lambdas/handlers.py:156-241 |
| 4 | **initiate_processing** | Queues job | - |
| 5 | **post_processing** | Starts optimization | fsm-lambdas/update_state.py:187 |
| 6 | **process_and_optimize_transactions** | Aggregates data | fsm-lambdas/aggregates.py:2592-2631 |
| 7 | **elixir_pre_processing** | (Conditional) | - |
| 8 | **categorization** | Tags transactions | fsm-lambdas/feature_calc.py:111-119 |
| 9 | **post_processing** | Final cleanup | fsm-lambdas/feature_calc.py:135 |
| 10 | **xlsx_report_v16** | Generates report | Report service |
| 11 | **aggregate_xlsx_report_v3** | Aggregates report | Aggregation service |
| 12 | **webhook_enrichment** | Sends webhook | finboxdashboard/views.py:6617-6685 |

If any stage shows ⏳, that's where it failed.

---

## ⚠️ Important

**Session cookies expire every 1-2 hours.** When you get "Unauthorized":
1. Go to https://grafana.tools.finbox.in
2. Get a fresh cookie (DevTools → Application → Cookies)
3. Update your env var: `export GRAFANA_SESSION=<new-cookie>`

---

## 🎓 Recommended Reading Order

1. **If you have 5 minutes:** [TEAM_ONBOARDING.md](TEAM_ONBOARDING.md)
2. **If you have 2 minutes:** [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
3. **If you have 10 minutes:** [SETUP.md](SETUP.md)
4. **If you need deep dive:** [SKILL.md](SKILL.md)

---

## 🔗 Files

```
.claude/skills/trace-funnel-flow/
├── README.md                 ← You are here
├── TEAM_ONBOARDING.md       ← Share with team
├── QUICK_REFERENCE.md       ← Quick cheat sheet
├── SETUP.md                 ← Detailed setup
├── SKILL.md                 ← Complete docs
└── SKILL.md                 ← Skill definition
```

```
.claude/scripts/
└── trace_funnel_flow.py     ← The actual script
```

---

## ✅ Checklist: Team Adoption

- [ ] Read TEAM_ONBOARDING.md
- [ ] Got Grafana session cookie
- [ ] Tested the skill once
- [ ] Shared with team
- [ ] Team members set up their cookies
- [ ] Team documented common debugging patterns

---

## 🚀 Let's Go!

```bash
/trace-funnel-flow <uuid> --session <cookie>
```

Then read the report and find where it dropped off. That's your debugging target. 🎯
