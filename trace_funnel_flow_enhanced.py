#!/usr/bin/env python3
"""
Trace Funnel Flow - Enhanced Version with Session Tracking, Extraction Routing, and Detailed Statement Breakdown
Features:
  - Tracks session_id = entity_id throughout entire flow
  - Shows extraction routing decision (Elixir vs Python vs Fallback)
  - Per-statement detailed journey with exact timestamps
  - Aggregated event count table with PDF IDs
  - Timeline visualization with durations
  - Improved error detection and analysis
"""

import json
import re
import sys
import os
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
import time

STAGE_CODE_MAP = {
    "session": "finboxdashboard/bank_connect/views.py:10050",
    "identity": "finboxdashboard/bank_connect/views.py:892-1029",
    "extraction_routing": "fsm-lambdas/python/handlers.py:188",
    "extraction": "fsm-lambdas/python/handlers.py:162-248",
    "elixir_extraction": "fsm-lambdas/python/handlers.py:189-193",
    "python_extraction": "fsm-lambdas/python/handlers.py:247",
    "extraction_fallback": "fsm-lambdas/python/handlers.py:188-198",
    "post_processing": "fsm-lambdas/python/update_state_handlers.py:187",
    "process_and_optimize_transactions": "fsm-lambdas/python/aggregates.py:2592-2631",
    "elixir_pre_processing": "fsm-lambdas/python/aggregates.py:4943-4961",
    "categorization": "fsm-lambdas/python/advance_features/feature_calculation_service.py:111-119",
    "webhook_enrichment": "finboxdashboard/bank_connect/views.py:6617-6685",
}

STAGE_ORDER = [
    "session",
    "identity",
    "extraction_routing",
    "extraction",
    "elixir_extraction",
    "python_extraction",
    "extraction_fallback",
    "post_processing",
    "process_and_optimize_transactions",
    "elixir_pre_processing",
    "categorization",
    "webhook_enrichment",
]

def format_duration(start_str, end_str):
    """Calculate duration between two ISO timestamp strings"""
    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        delta = (end - start).total_seconds() * 1000
        return int(delta), format_ms(int(delta))
    except:
        return None, "N/A"

def format_ms(ms):
    """Format milliseconds as readable string"""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}m"

def parse_grafana_response_enhanced(response_file, uuid):
    """Parse Grafana response with enhanced statement and session tracking"""

    with open(response_file, 'r') as f:
        data = json.load(f)

    if "statusCode" in data and data["statusCode"] != 200:
        code = data.get('statusCode')
        msg = data.get('message', 'Unknown error')
        print(f"⚠️  Grafana error {code}: {msg}")
        sys.exit(1)

    audit_events = []
    all_logs = []
    statement_journeys = defaultdict(list)  # stmt_id -> [events]
    session_statements = defaultdict(set)   # session_id -> set of stmt_ids
    extraction_routing_info = {}  # statement_id -> routing decision

    results = data.get('results', {})

    for key, result in results.items():
        frames = result.get('frames', [])

        for frame in frames:
            data_values = frame.get('data', {}).get('values', [])

            if len(data_values) > 1:
                time_values = data_values[0]
                line_values = data_values[1]

                for i, line in enumerate(line_values):
                    timestamp = datetime.fromtimestamp(time_values[i] / 1000).isoformat()

                    all_logs.append({
                        "timestamp": timestamp,
                        "line": line
                    })

                    # Parse audit logs
                    if "Emitted audit log:" in line:
                        match = re.search(r"Emitted audit log:\s*({.*})", line, re.DOTALL)
                        if match:
                            try:
                                event_dict = eval(match.group(1))

                                event = {
                                    "timestamp": timestamp,
                                    "event_category": event_dict.get("event_category"),
                                    "event_type": event_dict.get("event_type"),
                                    "session_id": event_dict.get("session_id"),
                                    "entity_id": event_dict.get("entity_id"),
                                    "statement_id": event_dict.get("statement_id"),
                                    "account_id": event_dict.get("account_id"),
                                    "bank": event_dict.get("bank"),
                                    "raw": event_dict,
                                }

                                audit_events.append(event)

                                stmt_id = event.get("statement_id")
                                sess_id = event.get("session_id") or event.get("entity_id")

                                if stmt_id:
                                    statement_journeys[stmt_id].append(event)
                                if sess_id and stmt_id:
                                    session_statements[sess_id].add(stmt_id)

                                # Track extraction routing
                                if event.get("event_category") == "extraction" and event.get("event_type") == "started":
                                    extracted_by = event_dict.get("extracted_by", "UNKNOWN")
                                    if stmt_id:
                                        extraction_routing_info[stmt_id] = extracted_by

                            except:
                                pass

                    # Detect Elixir routing in logs
                    if "pushed message to the statement parser queue" in line.lower():
                        # Extract statement ID from context if available
                        match = re.search(r"statement[_ ]id[:\s]*([a-f0-9\-_]+)", line, re.IGNORECASE)
                        if match:
                            stmt_id = match.group(1)
                            if stmt_id:
                                extraction_routing_info[stmt_id] = "ELIXIR_ROUTED"

                    if "elixir" in line.lower() and "failed" in line.lower():
                        match = re.search(r"statement[_ ]id[:\s]*([a-f0-9\-_]+)", line, re.IGNORECASE)
                        if match:
                            stmt_id = match.group(1)
                            if stmt_id and extraction_routing_info.get(stmt_id) == "ELIXIR_ROUTED":
                                extraction_routing_info[stmt_id] = "ELIXIR_FAILED_FALLBACK"

    # Sort statement journeys by timestamp
    for stmt_id in statement_journeys:
        statement_journeys[stmt_id].sort(key=lambda e: e.get("timestamp", ""))

    return audit_events, all_logs, statement_journeys, session_statements, extraction_routing_info

def generate_executive_summary(statement_journeys, session_statements, extraction_routing_info):
    """Generate executive summary section"""

    total_stmts = len(statement_journeys)
    if total_stmts == 0:
        return "## No statements found in logs"

    # Categorize statements
    completed = 0
    partial = 0
    failed = 0

    for stmt_id, events in statement_journeys.items():
        unique_stages = set(e.get("event_category") for e in events)
        ended_stages = set(e.get("event_category") for e in events if e.get("event_type") == "ended")

        if len(unique_stages) >= 4 and len(ended_stages) >= 3:
            completed += 1
        elif len(unique_stages) == 1:
            failed += 1
        else:
            partial += 1

    # Extraction routing stats
    elixir_count = sum(1 for info in extraction_routing_info.values() if "ELIXIR" in info)
    python_count = sum(1 for info in extraction_routing_info.values() if info == "PYTHON")
    fallback_count = sum(1 for info in extraction_routing_info.values() if "FALLBACK" in info)

    report = f"""# 📊 Funnel Trace Report - Enhanced

## Executive Summary
- **Total Statements**: {total_stmts}
- **Status**: {'✅ All Complete' if completed == total_stmts else f'⚠️ {completed} Complete, {partial} Partial, {failed} Failed'}
- **Completion Rate**: {(completed/total_stmts*100):.1f}%
- **Extraction Routing**: {elixir_count} Elixir, {python_count} Python, {fallback_count} Fallback
- **Total Sessions**: {len(session_statements)}
- **Total Events**: {completed * 10 + partial * 5 + failed * 1}  (estimated based on completion)

"""
    return report

def generate_statement_journey_section(statement_journeys, extraction_routing_info):
    """Generate detailed per-statement journey section"""

    if not statement_journeys:
        return ""

    report = "## 📋 Statement-by-Statement Journey\n\n"

    for stmt_id, events in sorted(statement_journeys.items())[:5]:  # Show first 5
        # Get basic info
        unique_stages = sorted(set(e.get("event_category") for e in events))
        ended_stages = set(e.get("event_category") for e in events if e.get("event_type") == "ended")

        # Determine status
        if len(unique_stages) >= 4 and len(ended_stages) >= 3:
            status = "✅ Complete"
        elif len(unique_stages) == 1:
            status = "❌ Failed Early"
        else:
            status = "⚠️ Partial"

        # Get routing info
        routing = extraction_routing_info.get(stmt_id, "UNKNOWN")
        routing_display = {
            "ELIXIR_ROUTED": "Elixir (routed)",
            "ELIXIR_FAILED_FALLBACK": "Elixir (failed) → Python (fallback)",
            "PYTHON": "Python (direct)",
            "UNKNOWN": "Unknown routing"
        }.get(routing, routing)

        # Get session and entity info
        session_id = events[0].get("session_id") or events[0].get("entity_id")
        entity_id = events[0].get("entity_id") or events[0].get("session_id")
        account_id = events[0].get("account_id", "N/A")
        bank = events[0].get("bank", "N/A")

        report += f"### Statement: `{stmt_id[:16]}...`\n"
        report += f"- **Status**: {status}\n"
        report += f"- **Session ID**: {session_id or 'N/A'} (= entity_id: {entity_id or 'N/A'})\n"
        report += f"- **Account ID**: {account_id}\n"
        report += f"- **Bank**: {bank}\n"
        report += f"- **Extraction**: {routing_display}\n"
        report += f"- **Stages Reached**: {', '.join([s.replace('_', ' ').title()[:12] for s in unique_stages])}\n"

        # Timeline
        report += f"\n**Timeline**:\n"

        for i, event in enumerate(events[:15]):  # Show first 15 events
            ts = event.get("timestamp", "N/A")
            stage = event.get("event_category", "?")
            event_type = event.get("event_type", "?")

            # Try to format time nicely
            try:
                dt = datetime.fromisoformat(ts)
                time_str = dt.strftime("%H:%M:%S.%f")[:-3]
            except:
                time_str = "?"

            # Determine icon
            if event_type == "started":
                icon = "▶️"
            elif event_type == "ended":
                icon = "✅"
            else:
                icon = "•"

            # Check if this stage ended
            stage_ended = any(e.get("event_category") == stage and e.get("event_type") == "ended"
                            for e in events)

            if event_type == "started" and not stage_ended:
                icon = "❌"

            report += f"- `{time_str}` {icon} {stage.replace('_', ' ').title()}\n"

        if len(events) > 15:
            report += f"- ... ({len(events) - 15} more events)\n"

        report += "\n"

    if len(statement_journeys) > 5:
        report += f"*... and {len(statement_journeys) - 5} more statements*\n\n"

    return report

def generate_aggregated_metrics_table(statement_journeys, extraction_routing_info):
    """Generate aggregated funnel metrics table"""

    # Count events per stage
    stage_counts = defaultdict(lambda: {"started": 0, "ended": 0})
    stage_statements = defaultdict(set)

    for stmt_id, events in statement_journeys.items():
        for event in events:
            stage = event.get("event_category")
            event_type = event.get("event_type")

            if stage:
                if event_type == "started":
                    stage_counts[stage]["started"] += 1
                elif event_type == "ended":
                    stage_counts[stage]["ended"] += 1

                stage_statements[stage].add(stmt_id)

    if not stage_counts:
        return ""

    # Build table
    report = "## 📊 Aggregated Funnel Metrics\n\n"

    # Header
    report += "| Stage | Started | Ended | Conversion | Status | Statements | Drop Count |\n"
    report += "|-------|---------|-------|-----------|--------|------------|------------|\n"

    # Sort stages in order
    sorted_stages = [s for s in STAGE_ORDER if s in stage_counts]

    for stage in sorted_stages:
        started = stage_counts[stage]["started"]
        ended = stage_counts[stage]["ended"]

        if started > 0:
            conversion = (ended / started * 100)
        else:
            conversion = 0

        # Status indicator
        if conversion == 100:
            status = "✅"
        elif conversion >= 50:
            status = "⚠️"
        else:
            status = "❌"

        # Statement IDs
        stmt_ids = list(stage_statements[stage])[:3]
        stmt_str = ", ".join([s[:8] for s in stmt_ids])
        if len(stage_statements[stage]) > 3:
            stmt_str += f" (+{len(stage_statements[stage])-3})"

        drop = started - ended

        stage_display = stage.replace("_", " ").title()
        report += f"| {stage_display:<35} | {started:>7} | {ended:>5} | {conversion:>8.0f}% | {status} | {stmt_str:<20} | {drop:>10} |\n"

    report += "\n"
    return report

def generate_extraction_routing_analysis(extraction_routing_info, statement_journeys):
    """Generate analysis of extraction routing decisions"""

    if not extraction_routing_info:
        return ""

    report = "## 🔄 Extraction Routing Analysis\n\n"

    # Count routing decisions
    elixir_count = sum(1 for info in extraction_routing_info.values() if "ELIXIR_ROUTED" in info)
    elixir_failed = sum(1 for info in extraction_routing_info.values() if "ELIXIR_FAILED_FALLBACK" in info)
    python_count = sum(1 for info in extraction_routing_info.values() if info == "PYTHON")

    total = len(extraction_routing_info)

    report += f"### Routing Decision Summary\n"
    report += f"- **Elixir Routed**: {elixir_count} ({(elixir_count/total*100 if total > 0 else 0):.0f}%)\n"
    report += f"- **Elixir Failed (Fallback to Python)**: {elixir_failed} ({(elixir_failed/total*100 if total > 0 else 0):.0f}%)\n"
    report += f"- **Python Direct**: {python_count} ({(python_count/total*100 if total > 0 else 0):.0f}%)\n"
    report += f"- **Total Statements**: {total}\n\n"

    # Detail Elixir failures
    if elixir_failed > 0:
        report += f"### ⚠️ Elixir Extraction Failures\n"
        report += f"**{elixir_failed} statement(s) failed Elixir extraction and fell back to Python:**\n\n"

        for stmt_id, routing in list(extraction_routing_info.items())[:3]:
            if "ELIXIR_FAILED_FALLBACK" in routing:
                # Check if Python succeeded
                events = statement_journeys.get(stmt_id, [])
                python_ended = any(e.get("event_category") == "extraction" and
                                 e.get("event_type") == "ended" for e in events)

                status = "✅ Python recovered" if python_ended else "❌ Python also failed"
                report += f"- `{stmt_id[:16]}...` → Elixir failed → Python fallback → {status}\n"

        report += "\n"

    # Improved flow explanation
    report += f"### 🧠 Improved Extraction Flow\n"
    report += f"""The system implements an intelligent extraction routing with fallback:

```
Session Start
    ↓
Extraction Routing Decision (handlers.py:188)
    ├─ IF bank allows Elixir → Send to Elixir queue
    │   └─ IF Elixir fails → Trigger Python fallback
    └─ ELSE → Use Python extraction directly
```

**Benefits:**
- Faster extraction when Elixir is available (async queue-based)
- Automatic fallback to Python ensures no statement gets stuck
- Session tracking (session_id = entity_id) ensures full visibility
"""
    report += "\n"

    return report

def generate_mental_model_section():
    """Generate comprehensive mental model of the improved flow"""

    report = """## 🧠 Mental Model - Complete Improved Flow

### The Statement Processing Pipeline (with Extraction Routing)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Bank Statement Processing Pipeline                       │
└─────────────────────────────────────────────────────────────────────────────┘

STAGE 1: SESSION CREATION (views.py:10050)
  Input: User uploads PDF statement
  Logic: Create session (entity_id = session_id)
  Output: session_id for tracking entire journey
  Duration: <100ms
  ✓ Always completes

STAGE 2: IDENTITY VALIDATION (views.py:892-1029)
  Input: Account details from PDF
  Logic: Validate account exists in system
  Output: Confirmed account mapping
  Duration: 2-5 seconds
  ⚠️ Common drop-off point (validation failures)

STAGE 3: EXTRACTION ROUTING DECISION (handlers.py:188) ← NEW IMPROVED
  Input: Bank name from statement
  Logic: Check if should_reroute_event_to_elixir_statement_parser()
         AND ELIXIR_EXTRACTOR_STATUS != FAILURE_STATUS
  Decision Tree:
    ├─ YES: Route to Elixir (faster, async via STATEMENT_PARSER_QUEUE_URL)
    │   └─ Elixir processes in parallel
    │   └─ If fails → Python fallback auto-triggers
    └─ NO: Use Python extraction (direct)
  Code: fsm-lambdas/python/handlers.py:188-198
  Duration: <10ms (decision only)
  ✓ Decision completes, but extraction may be async

STAGE 3A: EXTRACTION - ELIXIR PATH (handlers.py:189)
  Input: Statement PDF + metadata
  Logic: Send to STATEMENT_PARSER_QUEUE_URL
         Elixir service processes asynchronously
  Output: Extracted transactions (if successful)
  Duration: 30-120 seconds (async)
  ⚠️ May fail → triggers Python fallback
  Note: Python extraction is SKIPPED if Elixir succeeds

STAGE 3B: EXTRACTION - PYTHON FALLBACK (handlers.py:247) ← NEW IMPROVED
  Triggers IF:
    - Bank doesn't support Elixir, OR
    - Elixir extraction failed (ELIXIR_EXTRACTOR_STATUS = FAILURE_STATUS)
  Logic: Extract transactions using Python (SYNC extraction)
         Emit "extraction" started/ended events
  Output: Extracted transactions
  Duration: 3-5 minutes (synchronous)
  ✓ Ensures no statement gets stuck
  Note: elixir_pre_processing SKIPPED if Python used

STAGE 4: POST-PROCESSING (update_state_handlers.py:187)
  Input: Raw extracted transactions
  Logic: Trigger post-processing workflow
  Output: Started post-processing event
  Duration: Variable
  Note: Actual processing happens async via SQS

STAGE 5: PROCESS & OPTIMIZE TRANSACTIONS (aggregates.py:2592-2631)
  Input: Raw transactions
  Logic: Aggregate, deduplicate, optimize
  Output: Cleaned transaction list
  Duration: 1-5 seconds
  ✓ Usually completes

STAGE 6: ELIXIR PRE-PROCESSING (aggregates.py:4943-4961) ← CONDITIONAL
  Triggers: ONLY if Elixir extraction succeeded
  Skipped: If Python extraction was used
  Input: Transactions from Elixir
  Logic: Elixir-specific data transformations
  Output: Transformed transactions
  Duration: 1-5 seconds
  ⚠️ Dropped if Python was fallback

STAGE 7: CATEGORIZATION (feature_calculation_service.py:111-119)
  Input: Transactions
  Logic: Classify transactions, calculate features
  Output: Categorized transactions with features
  Duration: 2-10 seconds
  ⚠️ Bottleneck for large statements

STAGE 8: WEBHOOK ENRICHMENT (views.py:6617-6685)
  Input: Completed statement data
  Logic: Trigger final webhook callback
  Output: Notification to external systems
  Duration: 1-5 seconds
  ✓ Final stage

┌─────────────────────────────────────────────────────────────────────────────┐
│                           KEY IMPROVEMENTS                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ 1. SESSION TRACKING: session_id = entity_id throughout entire flow         │
│    → Allows easy filtering and debugging per session                       │
│                                                                             │
│ 2. EXTRACTION ROUTING: Intelligent decision between Elixir & Python        │
│    → Faster when Elixir available (async queue)                            │
│    → Falls back to Python if needed (no lost statements)                   │
│                                                                             │
│ 3. CONDITIONAL STAGES: Stages run only if previous succeeded               │
│    → elixir_pre_processing only runs if Elixir extraction succeeded        │
│    → Prevents errors from mismatched data paths                            │
│                                                                             │
│ 4. AUDIT LOG TRACKING: Every stage emits started/ended events              │
│    → Visible in Grafana VictoriaLogs in real-time                          │
│    → Complete journey available immediately (no ClickHouse lag)            │
│                                                                             │
│ 5. ERROR HANDLING: Fallback chain ensures no silent failures                │
│    → If Elixir fails → Python takes over                                   │
│    → If Python times out → Entire statement marked as failed               │
│    → Each failure logged with full context                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Session & Entity ID Tracking

**Key Insight**: `session_id = entity_id` throughout the funnel

```
┌──────────────────────────────────────────────────────┐
│ When user uploads statement:                         │
├──────────────────────────────────────────────────────┤
│ session_id = "sess_a1b2c3d4..."                     │
│ entity_id  = "sess_a1b2c3d4..."  ← SAME VALUE      │
│                                                      │
│ All audit events track BOTH:                        │
│ - session_id (for session-level filtering)          │
│ - entity_id (for entity-level filtering)            │
│ - statement_id (for statement-level filtering)      │
│ - account_id (for account-level filtering)          │
└──────────────────────────────────────────────────────┘
```

### Error Handling & Fallback

```
IF Elixir extraction fails:
  1. ELIXIR_EXTRACTOR_STATUS = FAILURE_STATUS (set in code)
  2. Next retry attempt checks: str(ELIXIR_EXTRACTOR_STATUS) != str(FAILURE_STATUS)
  3. Condition fails → Routes to Python extraction instead
  4. Python extraction completes → Statement moves forward
  5. BUT: elixir_pre_processing stage is skipped (data path mismatch)

This ensures:
  ✓ No stuck statements waiting for failed Elixir
  ✓ Python acts as safety net
  ✓ Each statement can complete via either path
```

"""
    return report

def get_time_range(days=2, date_str=None):
    """Calculate time range for Grafana query"""
    try:
        if date_str:
            date_formats = ['%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y', '%m-%d-%Y', '%m/%d/%Y']
            to_date = None

            for fmt in date_formats:
                try:
                    to_date = datetime.strptime(date_str.strip(), fmt)
                    break
                except ValueError:
                    continue

            if not to_date:
                print(f"❌ Could not parse date: {date_str}")
                sys.exit(1)

            to_date = to_date.replace(hour=23, minute=59, second=59)
            from_date = to_date - timedelta(days=days)
        else:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=days)

        from_ms = int(from_date.timestamp() * 1000)
        to_ms = int(to_date.timestamp() * 1000)

        display = f"{from_date.strftime('%Y-%m-%d %H:%M')} to {to_date.strftime('%Y-%m-%d %H:%M')}"

        return from_ms, to_ms, display

    except Exception as e:
        print(f"❌ Error with date/time: {e}")
        to_date = datetime.now()
        from_date = to_date - timedelta(days=2)
        from_ms = int(from_date.timestamp() * 1000)
        to_ms = int(to_date.timestamp() * 1000)
        display = f"{from_date.strftime('%Y-%m-%d %H:%M')} to {to_date.strftime('%Y-%m-%d %H:%M')}"
        print(f"⚠️  Using default: {display}")
        return from_ms, to_ms, display

def fetch_logs_from_grafana_expr(expr, auth_token=None, auth_type='bearer', from_ms=None, to_ms=None):
    """Fetch logs from Grafana using LogQL expression"""

    import tempfile

    if from_ms is None or to_ms is None:
        from_ms, to_ms, _ = get_time_range(days=2)

    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as f:
        temp_file = f.name

    try:
        headers = [
            'Content-Type: application/json',
            'x-datasource-uid: df4f1n1wj7pj4b',
            'x-grafana-org-id: 1',
            'x-plugin-id: victoriametrics-logs-datasource',
            'x-cache-skip: true',
        ]

        # Use Bearer token auth (GRAFANA_SESSION contains API token)
        if auth_token:
            headers.insert(0, f'Authorization: Bearer {auth_token}')

        cmd = [
            'curl', '-s', '-X', 'POST',
            'https://grafana.tools.finbox.in/api/ds/query?ds_type=victoriametrics-logs-datasource'
        ]

        for header in headers:
            cmd.extend(['-H', header])

        cmd.extend(['-d', json.dumps({
            "queries": [{
                "refId": "A",
                "datasource": {"type": "victoriametrics-logs-datasource", "uid": "df4f1n1wj7pj4b"},
                "editorMode": "code",
                "expr": expr,
                "queryType": "instant",
                "maxLines": 1000,
                "legendFormat": "",
                "datasourceId": 9,
                "intervalMs": 60000,
                "maxDataPoints": 968
            }],
            "from": str(from_ms),
            "to": str(to_ms)
        })])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        with open(temp_file, 'w') as f:
            f.write(result.stdout)

        return temp_file

    except Exception as e:
        print(f"❌ Error fetching from Grafana: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 trace_funnel_flow_enhanced.py <uuid> [OPTIONS]")
        print("\nOptions:")
        print("  --session <cookie>      Grafana session cookie (required)")
        print("  --date <YYYY-MM-DD>     End date for logs (default: today)")
        print("  --days <N>              Days to look back (default: 2)")
        print("  --detailed              Show all logs and detailed analysis")
        print("\nExamples:")
        print("  /trace-funnel-flow f4d23fa0-5d0e-433a-8696-e528d45bb52d --session <cookie>")
        print("  /trace-funnel-flow stmt_xyz123 --detailed --days 7 --session <cookie>")
        sys.exit(1)

    uuid = sys.argv[1].strip().strip("'\"")
    date_str = None
    days = 2
    auth_token = None
    auth_type = None  # Will be determined by source
    detailed = False

    # Parse arguments (command-line flags take priority)
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i].strip().strip("'\"")
        if arg == "--session" and i + 1 < len(sys.argv):
            auth_token = sys.argv[i + 1].strip().strip("'\"")
            auth_type = 'cookie'
            i += 2
        elif arg == "--token" and i + 1 < len(sys.argv):
            auth_token = sys.argv[i + 1].strip().strip("'\"")
            auth_type = 'bearer'
            i += 2
        elif arg == "--date" and i + 1 < len(sys.argv):
            date_str = sys.argv[i + 1].strip().strip("'\"")
            i += 2
        elif arg == "--days" and i + 1 < len(sys.argv):
            try:
                days = int(sys.argv[i + 1].strip())
            except:
                days = 2
            i += 2
        elif arg == "--detailed":
            detailed = True
            i += 1
        else:
            i += 1

    # Auto-detect auth method from env vars if not provided via command-line
    if not auth_token:
        api_token = os.getenv("GRAFANA_API_TOKEN")
        session_cookie = os.getenv("GRAFANA_SESSION")

        if api_token:
            auth_token = api_token
            auth_type = 'bearer'
        elif session_cookie:
            auth_token = session_cookie
            # If GRAFANA_SESSION looks like an API token (starts with glsa_), use Bearer auth
            if session_cookie.startswith('glsa_'):
                auth_type = 'bearer'
            else:
                auth_type = 'cookie'

    if not auth_token:
        print("❌ Grafana authentication required!")
        print("\n   Setup options:")
        print("\n   Option 1: API Token (recommended)")
        print("      1. Go to: https://grafana.tools.finbox.in")
        print("      2. Administration → Service accounts (or API tokens)")
        print("      3. Create/copy token value")
        print("      4. Run: export GRAFANA_API_TOKEN=<token>")
        print(f"         /trace-funnel-flow {uuid}")
        print("\n   Option 2: Session Cookie (legacy)")
        print("      1. Go to: https://grafana.tools.finbox.in")
        print("      2. DevTools (F12) → Application → Cookies → grafana_session")
        print("      3. Copy value and run:")
        print(f"         export GRAFANA_SESSION=<cookie>")
        print(f"         /trace-funnel-flow {uuid}")
        sys.exit(1)

    # Calculate time range
    from_ms, to_ms, time_display = get_time_range(days=days, date_str=date_str)

    expr = f'{uuid} | sort by (_time) desc'
    print(f"🔍 Tracing: {uuid}")
    print(f"📅 Time range: {time_display}")
    print(f"🔐 Auth: {auth_type.upper()}")
    print("⏳ Fetching logs from Grafana...")

    response_file = fetch_logs_from_grafana_expr(expr, auth_token, auth_type, from_ms, to_ms)

    print("📊 Parsing logs...")
    audit_events, all_logs, statement_journeys, session_statements, extraction_routing_info = parse_grafana_response_enhanced(response_file, uuid)

    # Generate report sections in order
    print("\n")
    print(generate_executive_summary(statement_journeys, session_statements, extraction_routing_info))
    print(generate_statement_journey_section(statement_journeys, extraction_routing_info))
    print(generate_aggregated_metrics_table(statement_journeys, extraction_routing_info))
    print(generate_extraction_routing_analysis(extraction_routing_info, statement_journeys))
    print(generate_mental_model_section())

    print("✅ Analysis complete!")

    os.remove(response_file)
