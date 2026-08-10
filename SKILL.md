---
name: trace-funnel-flow
description: Fetch Grafana VictoriaLogs, trace funnel stages, find drop-off points, map to code, and debug conversion issues
whenToUse: When a funnel stage fails/drops off, to trace a specific session/entity/statement end-to-end, or to understand which stage is leaking (aggregate mode)
---

# Trace Funnel Flow Skill (Enhanced)

## Quick Usage

### Single-ID Trace (Debugging) - Now with Enhanced Output
```bash
/trace-funnel-flow stmt_abc123                          # Statement trace with detailed breakdown
/trace-funnel-flow entity_user_456                      # Entity/Session trace
/trace-funnel-flow session_xyz789                       # Session ID trace (session_id = entity_id)
/trace-funnel-flow stmt_abc123 --detailed              # Show all logs and detailed session tracking
```

### Aggregate Stage Conversion (Population)
```bash
/trace-funnel-flow --stage-counts --hours 24
/trace-funnel-flow --stage-counts --hours 6
/trace-funnel-flow --aggregate --hours 24              # New aggregation with statement PDF IDs
```

## What It Does

Fetches logs from Grafana VictoriaMetrics and:

✓ **Single-ID Trace Mode** (default): One `session_id`/`entity_id`/`statement_id` in → complete journey through the funnel stages → which stages completed, which dropped off, exact error messages + code locations  
✓ **Aggregate Mode** (`--stage-counts`): Counts `started` vs `ended` per stage across a time window → shows stage-by-stage conversion % to spot leaks  
✓ **Error Extraction** - Full error-level log lines + surrounding context at the drop-off stage  
✓ **Code Mapping** - Exact file/function for each stage  
✓ **Timeline** - Timestamps and durations per stage  
✓ **Mental Model** - How the audit-log pipeline works end-to-end  

---

## The Actual Funnel Stages (Verified from Code) - Enhanced

The bank-connect pipeline flows through these stages **in this order**:

| # | Stage | Event Type | Duration | Code Location | Notes |
|---|-------|-----------|----------|----------------|-------|
| 1 | **session** | created | - | `finboxdashboard/bank_connect/views.py:10050` | Initialize session (entity_id = session_id) |
| 1a | **extraction_routing** | (internal logic) | <1 sec | `fsm-lambdas/python/handlers.py:188` | **NEW:** Decides Elixir vs Python |
| 2 | **identity** | started/ended | 2-5 sec | `finboxdashboard/bank_connect/views.py:892, 1029` | Account validation |
| 3a | **extraction (Elixir)** | (queued) | - | `fsm-lambdas/python/handlers.py:189` | If `should_reroute_event_to_elixir_statement_parser()` = True |
| 3b | **extraction (Python)** | started/ended | **3-5 min** ⚠️ | `fsm-lambdas/python/handlers.py:247` | If Elixir not allowed OR as fallback |
| 3c | **extraction_fallback** | (conditional) | - | `fsm-lambdas/python/handlers.py:188-198` | **NEW:** If Elixir fails, retry with Python |
| 4 | **initiate_processing** | triggered | - | Unknown (triggers SQS processing) | Start post-processing pipeline |
| 5 | **post processing** | started | - | `fsm-lambdas/python/update_state_handlers.py:187` | Begin transaction optimization |
| 6 | **process_and_optimize_transactions** | started/ended | 1-5 sec | `fsm-lambdas/python/aggregates.py:2592, 2631` | Aggregate & optimize data |
| 7 | **elixir pre processing** | started/ended | 1-5 sec | `fsm-lambdas/python/aggregates.py:4943, 4961` | **Conditional:** Only if Elixir extraction succeeded |
| 8 | **categorization** | started/ended | 2-10 sec | `fsm-lambdas/python/advance_features/feature_calculation_service.py:111, 119` | Feature calculation & tagging |
| 9 | **post processing** | ended | - | `fsm-lambdas/python/advance_features/feature_calculation_service.py:135, 158, 88` | Final cleanup & sync |
| 10 | **xlsx_report_v16** | started/ended | 10-30 sec | Report generation service (TBD) | Report generation |
| 11 | **aggregate_xlsx_report_v3** | started/ended | 5-15 sec | Aggregation service (TBD) | Report aggregation |
| 12 | **webhook_enrichment** | started/ended | 1-5 sec | `finboxdashboard/bank_connect/views.py:6617-6685` | Final webhook callback |

### Key Architecture Detail: Extraction Routing (Enhanced)

The system decides between **Elixir** and **Python** extraction at line 188 in `handlers.py`:

```
┌─────────────────────────────────────────────────────────────────┐
│ Extraction Routing Decision (handlers.py:188)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ IF should_reroute_event_to_elixir_statement_parser(bank) = TRUE │
│    AND ELIXIR_EXTRACTOR_STATUS != FAILURE_STATUS                │
│    ├─→ Send to STATEMENT_PARSER_QUEUE_URL (Elixir service)      │
│    ├─→ Python extraction is SKIPPED                             │
│    └─→ Later: if Elixir succeeds → elixir_pre_processing runs  │
│                                                                 │
│ ELSE (Python path OR Elixir fallback)                           │
│    ├─→ Run Python extraction (server_execution_plan)            │
│    ├─→ Emit "extraction" started/ended events                  │
│    └─→ elixir_pre_processing stage is SKIPPED                  │
│                                                                 │
│ NEW FALLBACK LOGIC:                                             │
│ IF ELIXIR_EXTRACTOR_STATUS = FAILURE_STATUS                     │
│    └─→ Automatically retry with Python extraction              │
│        (Line 188: Condition gates Elixir routing)              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Improved Flow Summary:**
- **Primary**: Try Elixir if bank is configured (faster, Elixir-native)
- **Fallback**: Use Python if Elixir is not allowed OR if Elixir failed
- **Conditional Stages**: `elixir_pre_processing` only runs if Elixir extraction succeeded
- **These are now semi-sequential with fallback**, not purely mutually exclusive

### Audit Log Pattern

Each stage emits `AuditEmitter.emit(event_category, event_type)` which:
1. Sends to SQS queue `bank-connect-audit-logs-{env}`
2. Logs locally with format: `Emitted audit log: {'session_id': '...', 'statement_id': '...', 'event_category': '...', 'event_type': 'started|ended', ...}`
3. Visible immediately in Grafana VictoriaLogs

---

## Grafana Access

### Setup (first time only)

This skill can fetch logs via:
1. **Grafana MCP** (if you authenticate via OAuth) — no token needed
2. **HTTP API** (fallback) — requires a `GRAFANA_TOKEN` environment variable

### Option A: Use Grafana MCP
If you see the message "Only MCP auth stubs available — authenticate now?", I'll call the Grafana OAuth flow:
- I'll give you an authorization URL
- You open it, log in to your Grafana org, and authorize Claude Code access
- Once authorized, subsequent calls use the MCP API directly (no token needed)

### Option B: Use HTTP API + Service Account Token
1. Log in to Grafana: https://grafana.tools.finbox.in
2. Click your profile → Administration → Service accounts (or Administration → Service Accounts)
3. Create a new service account (or find an existing one)
4. Copy the token value
5. Set the environment variable:
   ```bash
   export GRAFANA_TOKEN=<paste_token_here>
   ```
6. Run `/trace-funnel-flow <uuid>` — it will use the token automatically

### Grafana Instance Details
- **URL**: https://grafana.tools.finbox.in
- **Datasource**: VictoriaMetrics Logs (uid: `df4f1n1wj7pj4b`)
- **Query**: Full-text search for the UUID across all logs in the last 24 hours (default, adjustable with `--hours`)

---

## Implementation Guide for Claude

When user invokes `/trace-funnel-flow <uuid>`:

### Step 1: Check Grafana Access
If you haven't set up Grafana access yet:
- Try **MCP OAuth path** first — I'll call `mcp__grafana__authenticate` to get an auth URL
- If MCP tools don't appear, ask the user for a service-account token and set `GRAFANA_TOKEN` env var

### Step 2: Invoke the ENHANCED Script
```bash
# Single-ID trace (new enhanced version with routing analysis):
python3 .claude/scripts/trace_funnel_flow_enhanced.py <uuid> --session <cookie>

# With date range:
python3 .claude/scripts/trace_funnel_flow_enhanced.py <uuid> --date 2026-08-05 --days 7 --session <cookie>

# Detailed analysis (includes all logs):
python3 .claude/scripts/trace_funnel_flow_enhanced.py <uuid> --detailed --session <cookie>
```

### Step 3: Enhanced Script Features
The Python script (`.claude/scripts/trace_funnel_flow_enhanced.py`) provides:

1. **Session Tracking**: 
   - Tracks `session_id = entity_id` throughout entire flow
   - Allows filtering per session/entity
   - Links all statements to their session

2. **Extraction Routing Analysis**:
   - Detects Elixir vs Python routing decisions
   - Shows fallback when Elixir fails
   - Counts routing distribution across statements

3. **Per-Statement Journey**:
   - Detailed timeline for each statement
   - Exact timestamps for every stage start/end
   - Duration calculation per stage
   - Status tracking (✅ complete, ⏳ in-progress, ❌ failed)

4. **Aggregated Metrics Table**:
   - Event counts per stage
   - Statement PDF IDs involved in each stage
   - Conversion rates (started → ended)
   - Drop-off counts

5. **Improved Mental Model**:
   - Complete visualization of improved extraction flow
   - Extraction routing decision tree
   - Conditional stage execution logic
   - Error handling & fallback chain
   - Session/entity tracking explanation

6. **Code Mapping**:
   - Verified stage→file locations
   - Direct links to handlers

7. **Real-time Analysis**:
   - Grafana VictoriaLogs (no ClickHouse lag)
   - Complete journey available immediately

---

## Output Format (Enhanced)

### Single-ID Trace Mode (Debugging) - NEW Enhanced Output

```markdown
# Funnel Trace Report: <uuid>

## 📊 Executive Summary
- **Status**: ❌ Drop-off at extraction (Python fallback) | ✓ Complete
- **Session ID**: session-123-abc (= entity_id)
- **Statement PDF ID**: stmt_xyz_001.pdf
- **Stages Completed**: 7/12 (58%)
- **Total Duration**: 125,500ms (2m 5s)
- **Extraction Method**: Elixir (routed) → Python (fallback)
- **Critical Issue**: Extraction failed in Elixir, Python retry succeeded but post-processing timed out

## 🔄 Improved Extraction Routing Flow
┌─ Session Created (entity_id=session-123-abc) [00:00:00]
├─ Identity Validation [00:00:500]
├─ Extraction Routing Decision [00:00:600]
│  ├─ Elixir Eligible?: YES (bank=HDFC)
│  ├─ Routed to: STATEMENT_PARSER_QUEUE_URL
│  └─ Status: Sent for async processing
├─ Elixir Extraction (Async) [status: FAILED at 00:45:000]
│  └─ Fallback Triggered: YES
├─ Python Extraction Started [00:45:100]
│  ├─ Duration: 45,500ms
│  ├─ Pages Processed: 12
│  └─ Status: ✅ SUCCESS
├─ Post-Processing [00:90:600] ❌ DROPPED HERE
│  ├─ Status: Started but never ended
│  ├─ Duration: 5,000ms (before timeout)
│  └─ Error: Lambda execution timeout (15 min limit exceeded)
└─ Final Status: FAILED

## 📋 Statement-by-Statement Details

### Statement: stmt_xyz_001.pdf
- **Session ID**: session-123-abc
- **Entity ID**: entity-456-def (same as session_id)
- **Account ID**: acc-789-ghi
- **Bank**: HDFC
- **Document**: statement_2024_aug.pdf (12 pages)

#### Stage Journey:
```
[00:00:000] ✅ session_created
[00:00:500] ✅ identity_started → identity_ended (500ms)
[00:00:600] ✅ extraction_routing_decision (ELIXIR)
[00:00:610] ⏳ extraction (Elixir) → FAILED after 45s
[00:45:100] ✅ extraction (Python fallback) → SUCCESS (45500ms)
[00:90:600] ⏳ post_processing_started → ❌ NEVER ENDED (timeout)
[--:--:---] ❌ categorization (never reached)
[--:--:---] ❌ webhook_enrichment (never reached)
```

#### Event Timeline:
| Timestamp | Stage | Event | Status | Duration |
|-----------|-------|-------|--------|----------|
| 00:00:00 | session | created | ✅ | - |
| 00:00:50 | identity | started | ✅ | - |
| 00:00:55 | identity | ended | ✅ | 500ms |
| 00:00:60 | extraction | routing decision (Elixir) | ✅ | <10ms |
| 00:45:10 | extraction | Python fallback started | ✅ | - |
| 00:90:60 | extraction | Python ended | ✅ | 45,500ms |
| 00:90:61 | post_processing | started | ✅ | - |
| (timeout) | post_processing | ❌ NEVER ENDED | ❌ | >5000ms |

#### Errors Detected:
```
ERROR at 00:45:05: Elixir extraction failed - timeout
ERROR at (timeout): Post-processing lambda execution timeout
  - Logs truncated
  - Likely issue: Feature calculation is too slow for 12-page statement
```

## 📊 Aggregated Funnel Metrics

| Stage | Started | Ended | Conversion | Status | Statement IDs | Event Count |
|-------|---------|-------|-----------|--------|---------------|-------------|
| session | 1 | 1 | 100% | ✅ | stmt_xyz_001 | 1 |
| identity | 1 | 1 | 100% | ✅ | stmt_xyz_001 | 2 |
| extraction (Elixir routed) | 1 | 0 | 0% | ❌ | stmt_xyz_001 | 1 |
| extraction (Python fallback) | 1 | 1 | 100% | ✅ | stmt_xyz_001 | 2 |
| post_processing | 1 | 0 | 0% | ❌ | stmt_xyz_001 | 1 |
| categorization | 0 | 0 | N/A | ⏭️ | - | 0 |
| webhook_enrichment | 0 | 0 | N/A | ⏭️ | - | 0 |

## 🧠 Mental Model - Improved Flow

### Complete Funnel Order (with Extraction Routing)
1. **Session Created** → Initialize session (entity_id = session_id)
2. **Identity Validation** → Verify account mapping
3. **Extraction Routing Decision** → Check if Elixir is allowed
   - If YES: Send to Elixir queue (async)
   - If NO: Use Python extraction
4. **Extraction (Primary Path)** → Either Elixir or Python
   - If Elixir fails → Python fallback auto-triggers
5. **Post-Processing** → Optimize transactions
6. **[CONDITIONAL] Elixir Pre-Processing** → Only if Elixir extraction succeeded
7. **Categorization** → Feature engineering
8. **Webhook Enrichment** → Final callback

## 🎯 Next Steps
1. **Investigate Post-Processing Timeout**
   - Check: `fsm-lambdas/python/update_state_handlers.py:187`
   - Issue: Feature calculation taking >5 min for 12-page statement
   - Action: Add pagination or streaming to handle large statements
   
2. **Improve Elixir Fallback Detection**
   - Monitor: When Elixir fails, ensure Python fallback completes
   - Test: With actual 12-page HDFC statements
   
3. **Monitor Session/Entity Tracking**
   - Verify: session_id = entity_id throughout flow
   - Audit: Check for ID mapping inconsistencies
```

### Aggregate Mode (Population)

```markdown
# Funnel Conversion Report (Aggregate)
Time Window: 24 hours

## 📉 Conversion by Stage

| Stage | Started | Ended | Completion % | Prev Stage → This |
|-------|---------|-------|-------------|---------|
| extraction | 150 | 145 | 96.7% | 100% |
| identity | 145 | 130 | 89.7% | 96.7% |
| categorization | 130 | 125 | 96.2% | 89.7% |
```

---

## Real-World Examples

### Example 1: Debug Why a Statement Failed at Identity Stage
```
/trace-funnel-flow stmt_abc123

→ Report shows:
   ✓ extraction: 500ms (completed)
   ⏳ identity: never ended (drop-off here!)
   ❌ Code location: fsm-lambdas/python/identity_handlers.py
   ❌ Error log: "ValueError: No matching account found for bank account number"
   
→ Next step: Open identity_handlers.py and check how account matching works
```

### Example 2: Check Population-Level Funnel Health
```
/trace-funnel-flow --stage-counts --hours 6

→ Report shows:
   extraction:     100 started → 100 ended (100%)
   identity:       100 started → 85 ended (85%)
   categorization: 85 started → 82 ended (96%)
   
→ Insight: identity stage is the bottleneck (15% drop-off)
→ Next: use trace mode on a specific failed session to understand why
```

### Example 3: Debug a User's Slow Processing
```
/trace-funnel-flow session_user_xyz --hours 2

→ Report shows:
   Total duration: 45000ms (45 seconds)
   extraction:         500ms
   identity:          1000ms
   categorization:   40000ms (bottleneck!)
   post_processing:  3500ms
   
→ Insight: categorization is the bottleneck
→ Next: check feature_calculation_service.py for performance issues
```

---

## Technical Details

### Grafana Integration

**Datasource:** VictoriaMetrics Logs  
**UID:** `df4f1n1wj7pj4b`  
**Query Type:** Full-text search (not label-based)  
**URL:** `https://grafana.tools.finbox.in/api/ds/query`  
**Auth:** Bearer token (via `GRAFANA_TOKEN` env var)

### Supported Identifiers

The script searches for these UUIDs as free text:
- `session_id` - User session
- `entity_id` - Entity ID
- `statement_id` - Statement being processed
- `account_id` - Account ID
- Any other UUID/identifier format

### Query Format

```
Query sent to Grafana:
{
  "queries": [{
    "datasource": {"type": "victoriametrics-logs-datasource", "uid": "df4f1n1wj7pj4b"},
    "expr": "\"<uuid>\"",  # Full-text search for the UUID
    "refId": "A"
  }],
  "range": {"from": "now-24h", "to": "now"},  # Adjustable with --hours
  "maxDataPoints": 10000
}
```

### Performance

- Grafana query: ~1-2 seconds (depends on log volume)
- Log parsing: ~200ms
- Code mapping: ~50ms (hardcoded table, no grep)
- Report generation: ~100ms
- **Total: ~2-3 seconds**

### Caveat: ClickHouse Consumer

The audit events also flow to SQS queue `bank-connect-audit-logs-{env}`. A separate consumer should write these to ClickHouse table `bank_connect.event_stream_logs`, but that consumer code was not found in the current checkout. This means:
- **Grafana/VictoriaLogs** is the reliable, real-time source (what this skill uses)
- **ClickHouse via Redash** (used by the `/fetch-uuid` skill) may lag or be missing events if the consumer is unhealthy
- Both sources *should* be in sync when healthy, but verify the consumer's status if you see discrepancies

---

## Architecture: How It Works

### The Audit Log Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ Your Services (fsm-lambdas, finboxdashboard, statement-parser)  │
│                                                                 │
│  At each funnel stage:                                          │
│    AuditEmitter.emit(event_category, event_type)               │
│         ↓                                                        │
│    ├─→ Send to SQS: bank-connect-audit-logs-{env}               │
│    └─→ Log locally: LAMBDA_LOGGER.info("Emitted audit log: ...") │
└─────────────────────────────────────────────────────────────────┘
         │                                              │
         │                                              │
         ▼                                              ▼
    ┌─────────────────┐                    ┌──────────────────────┐
    │ SQS Queue       │                    │ Application Stdout   │
    │ (events flow)   │                    │ (logs appear here)   │
    └─────────────────┘                    └──────────────────────┘
         │                                              │
         ▼                                              ▼
    ┌─────────────────┐                    ┌──────────────────────┐
    │ Consumer        │                    │ Grafana              │
    │ (not in repo)   │                    │ VictoriaLogs         │
    │ → ClickHouse    │                    │ (this skill uses it) │
    └─────────────────┘                    └──────────────────────┘
```

**Key insight**: Each stage calls `AuditEmitter.emit()` which both sends to SQS *and* logs locally. The local log appears in Grafana VictoriaLogs, so this skill can trace funnel progression in real-time without waiting for a ClickHouse consumer.

### Single-ID Trace vs. Aggregate Mode

**Trace Mode** (default):
- Input: One UUID (session, entity, or statement ID)
- Output: This UUID's journey — which stages it hit, which it dropped off at, error messages
- Use case: Debugging a specific failure

**Aggregate Mode** (`--stage-counts`):
- Input: Time window (default 24h)
- Output: Counts of `started` and `ended` per stage across all requests
- Use case: Finding which stage is leaking (has more `started` than `ended`)

---

## Quick Start - Enhanced Version

```bash
# 1. Set up Grafana access (one time)
export GRAFANA_SESSION="<your-grafana-session-cookie>"

# 2. Get a UUID from your data (statement_id, session_id, or entity_id)

# 3. Trace it (new enhanced output)
/trace-funnel-flow stmt_abc123

# 4. Read the enhanced report sections:
# → Executive Summary: Overall completion rate & extraction routing stats
# → Statement Journey: Per-statement timeline with session tracking
# → Aggregated Metrics: Event counts & conversion rates per stage
# → Extraction Routing Analysis: Elixir vs Python distribution & fallbacks
# → Mental Model: Complete improved flow with routing logic
```

### Example: Debugging a Statement with Elixir Fallback

```bash
# Statement failed to complete
/trace-funnel-flow stmt_abc123

# Report shows:
# ├─ Executive Summary: "Elixir routed, failed, Python fallback succeeded"
# ├─ Statement Journey: Shows timeline with extraction routing decision
# │  └─ [00:45:10] ⏳ extraction (Elixir) → FAILED
# │  └─ [00:45:20] ✅ extraction (Python fallback) → SUCCESS
# ├─ Aggregated Metrics: extraction stage shows {Elixir: FAILED, Python: SUCCEEDED}
# ├─ Extraction Routing: "Elixir failed → Python fallback → Success"
# └─ Next Steps: Check what failed in Elixir, why Python succeeded

# Then investigate in code:
# → handlers.py:188 - Extraction routing decision
# → handlers.py:189-193 - Elixir queue routing
# → handlers.py:247 - Python extraction fallback
```

---

## When to Use This Skill

✅ **Use for:**
- Debugging why a statement/entity dropped off a funnel stage
- Understanding what error occurred and where (code file/line)
- Comparing processing times per stage (bottleneck analysis)
- Checking population-level funnel health (`--stage-counts`)
- Learning how the audit-log pipeline works

❌ **Don't use for:**
- Real-time monitoring (use Grafana dashboards for that)
- Ad-hoc log searches (use Grafana Explore UI directly)
- Querying other metrics (use `/fetch-uuid` for ClickHouse data)

---

## Understanding the Enhanced Output

### 1. Executive Summary
```
- Total Statements: 5
- Status: ✅ All Complete | ⚠️ 3 Complete, 1 Partial, 1 Failed
- Completion Rate: 80%
- Extraction Routing: 3 Elixir, 1 Python, 1 Fallback
```
**What it means:**
- Shows overall health of statement processing
- Extraction routing breakdown tells you which bank statements used which path
- Completion rate indicates funnel health

### 2. Statement-by-Statement Journey
Each statement shows:
- **Status**: ✅ Complete | ⚠️ Partial | ❌ Failed
- **Session/Entity IDs**: Linked together (session_id = entity_id)
- **Extraction Method**: Shows routing decision
- **Timeline**: Every event with timestamps

**What to look for:**
- Stages that never ended (❌ icon) = drop-off point
- Long durations = bottleneck stages
- Extraction method tells you if Elixir or Python was used

### 3. Aggregated Funnel Metrics Table
Shows per-stage statistics across ALL statements:
```
| Stage           | Started | Ended | Conversion | Status | Statements |
|-----------------|---------|-------|-----------|--------|------------|
| extraction      | 5       | 4     | 80%       | ⚠️     | stmt_1,... |
| categorization  | 4       | 2     | 50%       | ❌     | stmt_2,... |
```

**How to interpret:**
- **Started vs Ended**: If different, statements dropped at that stage
- **Conversion %**: 100% = healthy, <50% = critical drop-off
- **Status**: 
  - ✅ = Perfect (100% conversion)
  - ⚠️ = Partial (50-99% conversion)
  - ❌ = Critical drop-off (<50%)
- **Statement IDs**: Which statements went through that stage

### 4. Extraction Routing Analysis
Shows the improved extraction flow in action:
```
Extraction Decision Summary:
- Elixir Routed: 3 (60%)
- Elixir Failed (Fallback): 1 (20%)
- Python Direct: 1 (20%)

Elixir Extraction Failures:
- stmt_abc123: Elixir failed → Python fallback → ✅ Python recovered
```

**What it means:**
- Elixir routed statements go async via queue (faster)
- If Elixir fails, Python automatically takes over (safety net)
- Python direct statements are handled synchronously from start

### 5. Mental Model - Improved Flow
The comprehensive diagram shows the complete pipeline with:
- Every stage and its inputs/outputs
- Extraction routing decision tree
- Conditional stages (only run if certain conditions met)
- Session tracking throughout
- Error handling & fallback chain

**Why it matters:**
- Helps you understand WHERE a statement got stuck
- Explains WHY it couldn't progress further
- Shows WHAT could happen next if issues are fixed

## New Features in Enhanced Version

### ✨ Session Tracking
- **Tracks**: `session_id = entity_id` throughout entire flow
- **Benefit**: Easy filtering and debugging per user session
- **Example**: All 5 statements in a session share the same session_id

### ✨ Extraction Routing Analysis
- **Tracks**: Whether Elixir or Python extraction was used
- **Shows**: When Elixir fails, Python fallback takes over
- **Benefit**: Understand which extraction path each statement took
- **Example**: "3 Elixir routed, 1 failed and fell back to Python"

### ✨ Per-Statement Journey
- **Tracks**: Complete timeline for each statement
- **Shows**: Every stage start/end with exact timestamps
- **Benefit**: Debug specific statement failures quickly
- **Example**: See exactly when post-processing timed out

### ✨ Aggregated Metrics
- **Tracks**: Event counts per stage across all statements
- **Shows**: Which stages are bottlenecks (started > ended)
- **Benefit**: Identify population-level issues
- **Example**: "categorization: 4 started, 2 ended = 50% drop-off"

### ✨ Improved Mental Model
- **Tracks**: Complete flow with extraction routing
- **Shows**: Conditional logic and fallback chain
- **Benefit**: Understand the architecture
- **Example**: Why elixir_pre_processing only runs if Elixir succeeded

## Troubleshooting

**"GRAFANA_SESSION not set"**
- Get cookie: Grafana → DevTools (F12) → Application → Cookies → `grafana_session`
- Export it: `export GRAFANA_SESSION=<cookie>`
- Re-run the skill

**"401 Unauthorized"**
- Cookie may be expired or invalid
- Get a fresh one from your current Grafana session
- Try again

**"No logs found"**
- UUID may not have events in this time window
- Try: `--days 7` to search further back
- Check UUID format (should be statement_id, session_id, or entity_id)

**"Extraction routing not shown"**
- If no routing info appears, check:
  - Are audit logs being emitted? (check code)
  - Is "extracted_by" field populated in audit logs?
  - Try searching for a statement with confirmed routing

**"Session ID mismatch"**
- Report shows "Session ID: NULL" for some statements?
- Check if audit logs include session_id/entity_id fields
- May indicate incomplete audit log instrumentation

## Complete Example: Debug a Failed Statement

```
User complaint: "My HDFC statement never completed processing"

Step 1: Get statement ID from database/logs
  stmt_id = "stmt_20240810_hdfc_001"

Step 2: Trace it
  /trace-funnel-flow stmt_20240810_hdfc_001

Step 3: Read Executive Summary
  Status: ⚠️ 1 Complete, 1 Partial, 1 Failed
  Extraction: 2 Elixir routed, 0 Fallback
  → Tells you whether Elixir or Python was used

Step 4: Check Statement Journey
  Session: sess_user_456 (= entity_id: sess_user_456)
  Timeline shows:
    [00:00:00] ✅ session_created
    [00:00:05] ✅ identity_ended
    [00:00:10] ✅ extraction_routing → Elixir routed
    [00:45:00] ❌ extraction never ended (dropped here!)
  → Tells you Elixir extraction failed and Python fallback wasn't triggered

Step 5: Check Aggregated Metrics
  | extraction | 1 | 0 | 0% | ❌ | stmt_20240810_hdfc_001 |
  → Confirms extraction stage is the bottleneck

Step 6: Check Extraction Routing Analysis
  "Elixir Routed: 1"
  "Elixir Failed (Fallback): 0"
  → Tells you Elixir was routed but fallback didn't trigger
  → Possible issue: ELIXIR_EXTRACTOR_STATUS not set correctly

Step 7: Investigate in code
  - handlers.py:188 - Check routing decision logic
  - handlers.py:189-193 - Check Elixir queue sending
  - Check ELIXIR_EXTRACTOR_STATUS handling in fallback logic
  - Verify Python fallback is triggered when Elixir fails
```
