import os
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

# Load environment variables for local development
# Streamlit Cloud uses .streamlit/secrets.toml instead
load_dotenv()

from agent.orchestrator import analyze_file, add_duplicate_escalations, timestamp
from agent.rules import TARGET_FIELDS, clean_value, validate_record, find_duplicate_employee_ids
from schemas.employee import TARGET_SCHEMA

st.set_page_config(page_title="NEXUS", page_icon="🔄", layout="wide")

# Support both local .env and Streamlit Cloud secrets
def get_env(key, default=None):
    """Get environment variable from secrets (Streamlit Cloud) or .env (local)"""
    try:
        # Try to get from Streamlit secrets (Streamlit Cloud)
        if key in st.secrets:
            return st.secrets[key]
    except (FileNotFoundError, KeyError):
        # Secrets file doesn't exist or key not found (local development)
        pass
    
    # Fall back to .env file (local development)
    return os.getenv(key, default)

DEFAULT_API = get_env("TARGET_API_URL", "http://localhost:8099")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

    :root {
        --ink: #172331;
        --muted: #637080;
        --line: #dbe3e8;
        --paper: #f7f9f8;
        --panel: #ffffff;
        --teal: #0d7c78;
        --teal-soft: #e2f2ef;
        --amber-soft: #fff3d8;
    }

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
        color: var(--ink);
    }

    .stApp {
        background:
            radial-gradient(circle at 88% 4%, rgba(13, 124, 120, 0.08), transparent 25rem),
            linear-gradient(135deg, var(--paper) 0%, #eef5f3 100%);
    }

    h1, h2, h3 {
        font-family: 'Space Grotesk', sans-serif;
        color: var(--ink);
        letter-spacing: 0;
    }

    h1 {
        font-size: 2.6rem !important;
        margin-bottom: 0.15rem !important;
    }

    [data-testid="stSidebar"] {
        background: #172b36;
    }

    [data-testid="stSidebar"] * {
        color: #edf5f3;
    }

    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea {
        color: #172331 !important;
        background: #ffffff !important;
        caret-color: #172331 !important;
    }

    [data-testid="stSidebar"] input::placeholder,
    [data-testid="stSidebar"] textarea::placeholder {
        color: #637080 !important;
        opacity: 1 !important;
    }

    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background: #ffffff !important;
    }

    [data-testid="stSidebar"] [data-baseweb="select"] * {
        color: #172331 !important;
    }

    [data-testid="stSidebar"] [data-testid="stExpander"] {
        border-color: rgba(237, 245, 243, 0.22);
        background: rgba(255, 255, 255, 0.06);
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--line);
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.78);
        box-shadow: 0 8px 24px rgba(23, 35, 49, 0.045);
        padding: 0.45rem 0.7rem;
    }

    [data-testid="stMetric"] {
        border-left: 3px solid var(--teal);
        background: var(--teal-soft);
        padding: 0.65rem 0.8rem;
        border-radius: 6px;
    }

    [data-testid="stMetricLabel"] {
        color: var(--muted);
    }

    .stButton > button {
        border-radius: 6px;
        border: 1px solid var(--teal);
        font-weight: 600;
    }

    [data-testid="stSidebar"] .stButton > button,
    [data-testid="stSidebar"] .stButton > button p,
    [data-testid="stSidebar"] .stButton > button span {
        color: #172331 !important;
        background: #ffffff !important;
    }

    .stButton > button[kind="primary"] {
        background: var(--teal);
        color: white;
    }

    [data-testid="stFileUploader"] {
        border: 1px dashed #91b8b3;
        border-radius: 8px;
        background: #f2faf8;
        padding: 0.35rem;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 7px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "migration" not in st.session_state:
    st.session_state.migration = {
        "files": [],
        "mappings": [],
        "records": [],
        "escalations": [],
        "audit": [],
        "push_status": {},
        "started": False,
    }

M = st.session_state.migration

def audit(message, *, action="info", record_id=None, before=None, after=None, reason=None):
    M["audit"].append({
        "timestamp": timestamp(),
        "action": action,
        "record_id": record_id,
        "message": message,
        "before": before,
        "after": after,
        "reason": reason,
    })

def audit_text(event):
    if isinstance(event, str):
        return event
    record = f" [{event['record_id']}]" if event.get("record_id") else ""
    return f"{event['timestamp']} — {event['message']}{record}"

def target_record(record):
    return {field: record.get(field) for field in TARGET_FIELDS}

def has_duplicate_key(record, records, excluded_item):
    key = record.get("employee_id") or record.get("email")
    if not key:
        return False
    return any(
        item is not excluded_item
        and (item["record"].get("employee_id") or item["record"].get("email")) == key
        for item in records
    )

def get_target_record(api_url, employee_id):
    try:
        response = requests.get(f"{api_url.rstrip('/')}/employees", timeout=10)
        if not response.ok:
            return None
        return next(
            (item for item in response.json() if item.get("employee_id") == employee_id),
            None,
        )
    except Exception:
        return None

def push_record(api_url, record, operation):
    employee_id = record["employee_id"]
    before = get_target_record(api_url, employee_id)
    after = target_record(record)
    try:
        response = requests.post(
            f"{api_url.rstrip('/')}/employees",
            json=record,
            timeout=10,
        )
        if response.ok:
            audit(
                f"{operation.title()} succeeded for {employee_id}",
                action=operation,
                record_id=employee_id,
                before=before,
                after=after,
                reason="Validated source record was written to the target API.",
            )
            return {"record": after, "before": before, "status": "success"}
        error = f"HTTP {response.status_code}: {response.text}"
    except Exception as exc:
        error = str(exc)

    audit(
        f"{operation.title()} failed for {employee_id}: {error}",
        action=f"{operation}_failed",
        record_id=employee_id,
        before=before,
        after=None,
        reason="The target API rejected the record or was unreachable.",
    )
    return {"record": after, "before": before, "status": f"failed: {error}"}

def rollback_record(api_url, employee_id, pushed_record, previous_record=None):
    before = get_target_record(api_url, employee_id) or pushed_record
    try:
        if previous_record:
            response = requests.put(
                f"{api_url.rstrip('/')}/employees/{employee_id}",
                json=previous_record,
                timeout=10,
            )
        else:
            response = requests.delete(
                f"{api_url.rstrip('/')}/employees/{employee_id}",
                timeout=10,
            )
        if response.ok:
            audit(
                f"Rollback succeeded for {employee_id}",
                action="rollback",
                record_id=employee_id,
                before=before,
                after=previous_record,
                reason=(
                    "Human requested restoration of the previous target record."
                    if previous_record
                    else "Human requested removal of the record written by this migration."
                ),
            )
            return True
        error = f"HTTP {response.status_code}: {response.text}"
    except Exception as exc:
        error = str(exc)
    audit(
        f"Rollback failed for {employee_id}: {error}",
        action="rollback_failed",
        record_id=employee_id,
        before=before,
        after=None,
        reason="The target API could not remove the record.",
    )
    return False

def load_file(uploaded):
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_excel(uploaded)
    df.columns = [str(c).strip() for c in df.columns]
    return df

def reset_migration():
    st.session_state.migration = {
        "files": [], "mappings": [], "records": [], "escalations": [],
        "audit": [], "push_status": {}, "started": False
    }

st.title("🔄 NEXUS")
st.caption("Intelligent data migration, supervised by design")

with st.sidebar:
    st.header("Migration")
    client_name = st.text_input("Client", "DarwinBox")
    entity = st.selectbox("Entity", ["Employees"])
    use_groq = st.toggle("Use Groq LLM", value=True)
    confidence_threshold = st.slider(
        "Auto-approval confidence",
        min_value=0.70,
        max_value=1.00,
        value=0.90,
        step=0.01,
        help="Mappings below this confidence are sent to human review.",
    )
    st.caption(f"Mappings below {confidence_threshold:.0%} require review")
    st.caption(f"Model: {get_env('GROQ_MODEL', 'openai/gpt-oss-20b')}")
    with st.expander("Rules"):
        st.caption("Target-schema validation rules")
        ruleset = [
            {
                "field": field,
                "type": definition["type"],
                "required": "Yes" if definition["required"] else "No",
                "rule": definition["description"],
            }
            for field, definition in TARGET_SCHEMA.items()
        ]
        st.dataframe(
            pd.DataFrame(ruleset),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Mappings below the confidence threshold require review. "
            "Duplicate employee_id or email values are shown as references."
        )
    st.divider()
    st.write("**Autonomy policy**")
    st.write("🟢 High-confidence + low-risk → automatic")
    st.write("🟡 Ambiguous/high-impact → human review")
    st.divider()
    
    with st.expander("ℹ️ Target API Configuration"):
        st.markdown("""
        **What is the Target API?**
        
        The Target API is where NEXUS pushes cleaned and validated employee records.
        
        **For Streamlit Cloud:**
        - Must be a publicly accessible URL (HTTPS preferred)
        - Examples:
          - `https://hr-api.company.com/employees`
          - `https://api.workday.com/v1/employees`
          - Your production/staging HR system endpoint
        
        **For Local Development:**
        - Can be `http://localhost:8099` (mock API)
        - Or a remote API URL
        
        **Important:**
        - Streamlit Cloud cannot reach `localhost` APIs
        - Use remote API URL or deploy your API alongside NEXUS
        - API must accept POST requests to create records
        - Configure via `.streamlit/secrets.toml` on Streamlit Cloud
        """)
    
    st.divider()
    if st.button("Reset migration"):
        reset_migration()
        st.rerun()

sections = [st.container(border=True) for _ in range(4)]

with sections[0]:
    st.subheader("Migration Setup")
    st.write("Upload multiple source files representing the same entity.")

    uploads = st.file_uploader(
        "CSV / Excel files",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    with st.expander("Target schema", expanded=True):
        st.json(TARGET_SCHEMA)

    if st.button("🚀 Start Migration", type="primary", disabled=not uploads):
        reset_migration()
        M = st.session_state.migration
        M["started"] = True
        audit(f"Migration started for {client_name} / {entity}")

        for uploaded in uploads:
            try:
                df = load_file(uploaded)
                M["files"].append({"name": uploaded.name, "df": df})
                audit(f"Loaded {uploaded.name}: {len(df)} rows × {len(df.columns)} columns")

                mapping, records, escalations = analyze_file(
                    df,
                    uploaded.name,
                    use_groq=use_groq,
                    confidence_threshold=confidence_threshold,
                )
                M["mappings"].extend(mapping)
                M["records"].extend(records)
                M["escalations"].extend(escalations)

                audit(f"Generated source-to-target mappings for {uploaded.name}")
                audit(f"Validated {len(records)} records from {uploaded.name}")
            except Exception as exc:
                audit(f"Failed to process {uploaded.name}: {exc}")
                st.error(f"Could not process {uploaded.name}: {exc}")

        M["escalations"] = add_duplicate_escalations(
            M["records"], M["escalations"]
        )
        audit(f"Migration analysis complete: {len(M['escalations'])} escalation(s)")

    if M["files"]:
        st.subheader("Loaded files")
        cols = st.columns(min(3, len(M["files"])))
        for i, item in enumerate(M["files"]):
            cols[i % len(cols)].metric(
                item["name"], f"{len(item['df'])} records"
            )
            with cols[i % len(cols)].expander("Preview"):
                st.dataframe(item["df"].head(5), use_container_width=True)

actionable_escalations = M["escalations"]

with sections[1]:
    st.subheader("🤖 Agent Activity")
    if not M["started"]:
        st.info("Start a migration to see the agent working.")
    else:
        metrics = st.columns(4)
        metrics[0].metric("Source files", len(M["files"]))
        metrics[1].metric("Records", len(M["records"]))
        metrics[2].metric("Escalations", len(actionable_escalations))
        metrics[3].metric("Audit events", len(M["audit"]))

        st.markdown("### Agent log")
        for event in M["audit"]:
            st.write("✓", audit_text(event))

        st.markdown("### Source → Target Mapping")
        if M["mappings"]:
            df_map = pd.DataFrame(M["mappings"])
            columns = [
                "file", "source", "target", "confidence",
                "runner_up", "runner_up_confidence", "decision", "reason"
            ]
            st.dataframe(df_map[columns], use_container_width=True)

with sections[2]:
    st.subheader("⚠ Human-in-the-loop Review Queue")

    if not M["escalations"]:
        st.success("No outstanding escalations. The agent handled everything autonomously.")
    else:
        st.warning(f"{len(M['escalations'])} case(s) require human attention.")

        remaining = []
        for idx, e in enumerate(M["escalations"]):
            if e["type"] == "validation":
                e["item"]["errors"] = validate_record(
                    e["item"]["record"],
                    e["item"].get("missing_fields"),
                )
                e["message"] = "; ".join(e["item"]["errors"])
            with st.container(border=True):
                st.markdown(
                    f"### {e['type'].title()} — {e['file']} / row {e['row']}"
                )
                st.write(e["message"])

                if e["type"] == "mapping":
                    item = e["item"]
                    st.write(
                        f"**Agent suggestion:** `{item.get('target')}` "
                        f"({float(item.get('confidence', 0))*100:.0f}%)"
                    )
                    st.write(f"**Alternative:** `{item.get('runner_up')}`")

                    options = [x for x in TARGET_FIELDS]
                    default = options.index(item["target"]) if item.get("target") in options else 0
                    selected = st.selectbox(
                        "Target field",
                        options,
                        index=default,
                        key=f"mapping_target_{idx}"
                    )
                    if st.button("Approve mapping", key=f"approve_map_{idx}"):
                        for m in M["mappings"]:
                            if m["file"] == e["file"] and m["source"] == item["source"]:
                                m["target"] = selected
                                m["decision"] = "human_approved"
                                m["confidence"] = 1.0
                        M["escalations"].remove(e)
                        audit(f"Human approved mapping {item['source']} → {selected}")
                        st.rerun()

                elif e["type"] == "validation":
                    item = e["item"]
                    record = item["record"]
                    st.write("**Validation errors:**", ", ".join(item["errors"]))
                    st.json(record)

                    placeholders = {
                        "employee_id": "e.g. 301",
                        "name": "e.g. Neha Kapoor",
                        "email": "e.g. neha@example.com",
                        "date_of_birth": "YYYY-MM-DD, e.g. 1996-08-15",
                        "department": "e.g. Marketing",
                        "joining_date": "YYYY-MM-DD, e.g. 2002-02-02",
                    }
                    error_fields = []
                    for error in item["errors"]:
                        field = error.rsplit(" ", 1)[-1]
                        if field in TARGET_FIELDS and field not in error_fields:
                            error_fields.append(field)
                    entered_values = {}
                    for field in error_fields:
                        current = "" if record.get(field) is None else str(record.get(field))
                        entered_values[field] = st.text_input(
                            f"Fill or correct {field}",
                            current,
                            placeholder=placeholders[field],
                            key=f"validation_value_{idx}_{field}"
                        ).strip()

                    c1, c2 = st.columns(2)
                    if c1.button("Approve correction", key=f"correct_{idx}"):
                        for field, entered_value in entered_values.items():
                            record[field] = clean_value(field, entered_value)
                        item["errors"] = validate_record(
                            record,
                            item.get("missing_fields"),
                        )
                        if not item["errors"]:
                            item["status"] = "valid"
                            M["escalations"].remove(e)
                            audit(
                                f"Human corrected {', '.join(error_fields)} "
                                f"for {e['file']} row {e['row']}"
                            )
                            st.rerun()
                        else:
                            st.error("Record is still invalid: " + ", ".join(item["errors"]))
                    if c2.button("Reject record", key=f"reject_{idx}"):
                        item["status"] = "rejected"
                        M["escalations"].remove(e)
                        audit(f"Human rejected {e['file']} row {e['row']}")
                        st.rerun()

                elif e["type"] == "duplicate":
                    duplicate = e["item"]
                    original = e["duplicate_of"]
                    if e.get("different_fields"):
                        st.caption(
                            "The identifier matches, but these details conflict: "
                            + ", ".join(e["different_fields"])
                        )
                    else:
                        st.caption("All target fields match; choose which source row to retain.")
                    st.write("**Earlier record**")
                    st.json(original["record"])
                    st.write("**Later record**")
                    st.json(duplicate["record"])
                    st.markdown("#### Keep both records")
                    st.caption(
                        "Change the later record's employee ID if both records are required."
                    )
                    previous_id = str(duplicate["record"].get("employee_id") or "")
                    replacement_id = st.text_input(
                        "New employee ID for later record",
                        previous_id,
                        key=f"duplicate_employee_id_{idx}",
                    ).strip()
                    if st.button("Save ID and allow both", key=f"save_duplicate_id_{idx}"):
                        updated_record = {**duplicate["record"], "employee_id": replacement_id}
                        errors = validate_record(
                            updated_record,
                            duplicate.get("missing_fields"),
                        )
                        if errors:
                            st.error("The updated record is invalid: " + "; ".join(errors))
                        elif has_duplicate_key(updated_record, M["records"], duplicate):
                            st.error("That employee ID is already used by another record.")
                        else:
                            duplicate["record"] = updated_record
                            duplicate["errors"] = []
                            duplicate["status"] = "valid"
                            M["escalations"].remove(e)
                            audit(
                                f"Human changed employee ID {previous_id} -> {replacement_id} and approved both records",
                                action="duplicate_resolved",
                                record_id=replacement_id,
                                before={"employee_id": previous_id},
                                after={"employee_id": replacement_id},
                                reason="Both source records were required, so the conflicting record received a unique employee ID.",
                            )
                            st.rerun()
                    c1, c2 = st.columns(2)
                    if c1.button("Push earlier record", key=f"keeporiginal_{idx}"):
                        duplicate["status"] = "rejected"
                        M["escalations"].remove(e)
                        audit(
                            f"Human retained earlier record and rejected duplicate: {e['file']} row {e['row']}",
                            action="duplicate_rejected",
                            record_id=duplicate["record"].get("employee_id"),
                            before=duplicate["record"],
                            reason="The earlier record was selected because the duplicate key had conflicting or repeated details.",
                        )
                        st.rerun()
                    if c2.button("Push later record", key=f"keeplatest_{idx}"):
                        original["status"] = "rejected"
                        M["escalations"].remove(e)
                        audit(
                            f"Human retained later record and rejected earlier record: {e['file']} row {e['row']}",
                            action="duplicate_rejected",
                            record_id=original["record"].get("employee_id"),
                            before=original["record"],
                            reason="The later record was selected by a human to resolve the duplicate key conflict.",
                        )
                        st.rerun()

with sections[3]:
    st.subheader("🚀 Push to Target")
    
    # API URL input with validation help
    api_url = st.text_input(
        "Target API URL",
        value=DEFAULT_API,
        placeholder="https://your-api.com/employees or http://localhost:8099"
    )
    
    # Validate API URL format
    if api_url and not api_url.startswith(("http://", "https://")):
        st.error("❌ API URL must start with http:// or https://")
        api_url = None
    
    # Check if API is reachable
    if api_url and st.button("🔍 Test API Connection"):
        try:
            response = requests.head(api_url, timeout=5)
            st.success(f"✅ API is reachable (HTTP {response.status_code})")
        except requests.exceptions.ConnectionError:
            st.error(f"❌ Cannot reach API at {api_url}")
            st.info("**For Streamlit Cloud:** Ensure your API is publicly accessible (not localhost)")
        except Exception as exc:
            st.warning(f"⚠️ Connection check failed: {exc}")

    for item in M["records"]:
        if item["status"] != "rejected":
            item["errors"] = validate_record(
                item["record"],
                item.get("missing_fields"),
            )
            item["status"] = "valid" if not item["errors"] else "review"

    valid = [
        item for item in M["records"]
        if item["status"] == "valid" and not item["errors"]
    ]
    rejected = sum(1 for item in M["records"] if item["status"] == "rejected")
    pre_push_rows = [
        {
            "employee_id": item["record"].get("employee_id"),
            "status": (
                "Rejected"
                if item["status"] == "rejected"
                else "Ready" if not item["errors"] else "Needs user input"
            ),
            "missing or invalid fields": ", ".join(
                error.rsplit(" ", 1)[-1] for error in item["errors"]
            ),
        }
        for item in M["records"]
    ]
    pre_push_ready = bool(M["records"]) and not actionable_escalations and (
        len(valid) + rejected == len(M["records"])
    )

    st.markdown("### Pre-record target status")
    if pre_push_rows:
        st.dataframe(pd.DataFrame(pre_push_rows), hide_index=True, use_container_width=True)
    if not pre_push_ready:
        st.warning("Enter values for every missing or invalid field in the review queue before pushing.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", len(M["records"]))
    c2.metric("Ready", len(valid))
    c3.metric("Review", len(actionable_escalations))
    c4.metric("Rejected", rejected)

    if actionable_escalations:
        st.info("Resolve all escalations before pushing to the target.")
    else:
        if st.button(
            "📤 Push Ready Records",
            type="primary",
            disabled=not pre_push_ready or not api_url,
        ):
            progress = st.progress(0)
            for n, item in enumerate(valid, start=1):
                record = item["record"]
                emp_id = record["employee_id"]
                M["push_status"][emp_id] = push_record(api_url, record, "push")
                progress.progress(n / len(valid))

    for emp_id, result in list(M["push_status"].items()):
        if isinstance(result, str):
            source_item = next(
                (
                    item for item in M["records"]
                    if item["record"].get("employee_id") == emp_id
                ),
                None,
            )
            M["push_status"][emp_id] = {
                "record": {
                    field: source_item["record"].get(field)
                    for field in TARGET_FIELDS
                } if source_item else {field: None for field in TARGET_FIELDS},
                "status": result,
            }

    if M["push_status"]:
        st.markdown("### Per-record target status")
        rows = [
            {
                **{field: result["record"].get(field) for field in TARGET_FIELDS},
                "status": result["status"],
            }
            for result in M["push_status"].values()
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        failed = [
            key for key, result in M["push_status"].items()
            if str(result["status"]).startswith("failed")
        ]
        if failed:
            st.warning(f"{len(failed)} record(s) failed. Retry or edit is available.")
            for emp_id in failed:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Retry {emp_id}", key=f"retry_{emp_id}"):
                        item = next(
                            (x for x in M["records"] if x["record"].get("employee_id") == emp_id),
                            None
                        )
                        if item:
                            M["push_status"][emp_id] = push_record(
                                api_url, item["record"], "retry"
                            )
                            st.rerun()
                with col2:
                    if st.button(f"Edit & Push {emp_id}", key=f"edit_{emp_id}"):
                        st.session_state[f"editing_{emp_id}"] = True
                        st.rerun()

                if st.session_state.get(f"editing_{emp_id}"):
                    st.markdown(f"#### Edit record: {emp_id}")
                    item = next(
                        (x for x in M["records"] if x["record"].get("employee_id") == emp_id),
                        None
                    )
                    if item:
                        edited_record = item["record"].copy()
                        placeholders = {
                            "employee_id": "e.g. 301",
                            "name": "e.g. Neha Kapoor",
                            "email": "e.g. neha@example.com",
                            "date_of_birth": "YYYY-MM-DD, e.g. 1996-08-15",
                            "department": "e.g. Marketing",
                            "joining_date": "YYYY-MM-DD, e.g. 2002-02-02",
                        }
                        edit_cols = st.columns(2)
                        for i, field in enumerate(TARGET_FIELDS):
                            col = edit_cols[i % 2]
                            current_value = "" if edited_record.get(field) is None else str(edited_record.get(field))
                            edited_record[field] = col.text_input(
                                f"{field}",
                                current_value,
                                placeholder=placeholders.get(field, ""),
                                key=f"edit_field_{emp_id}_{field}"
                            ).strip()

                        ec1, ec2, ec3 = st.columns(3)
                        with ec1:
                            if st.button(f"Push updated record", key=f"push_edited_{emp_id}"):
                                for field in TARGET_FIELDS:
                                    edited_record[field] = clean_value(field, edited_record[field])
                                errors = validate_record(edited_record, item.get("missing_fields"))
                                if errors:
                                    st.error("Record is still invalid: " + "; ".join(errors))
                                else:
                                    item["record"] = edited_record
                                    M["push_status"][emp_id] = push_record(
                                        api_url, edited_record, "retry"
                                    )
                                    st.session_state[f"editing_{emp_id}"] = False
                                    audit(
                                        f"Human edited and re-pushed {emp_id}",
                                        action="edit_and_retry",
                                        record_id=emp_id,
                                        before=M["push_status"][emp_id].get("record"),
                                        after=edited_record,
                                        reason="Record failed on initial push; human corrected data and re-submitted.",
                                    )
                                    st.rerun()
                        with ec2:
                            if st.button(f"Cancel", key=f"cancel_edit_{emp_id}"):
                                st.session_state[f"editing_{emp_id}"] = False
                                st.rerun()

        successful = [
            key for key, result in M["push_status"].items()
            if result["status"] == "success"
        ]
        if successful and st.button("Rollback successful pushes", type="secondary"):
            for emp_id in successful:
                rollback_record(
                    api_url,
                    emp_id,
                    M["push_status"][emp_id]["record"],
                        M["push_status"][emp_id].get("before"),
                )
                M["push_status"][emp_id]["status"] = "rolled back"
            st.rerun()

    st.markdown("### Audit Trail")
    if M["audit"]:
        for event in M["audit"]:
            st.write(audit_text(event))
        audit_rows = [
            {
                "time": event.get("timestamp"),
                "action": event.get("action"),
                "record": event.get("record_id"),
                "reason": event.get("reason"),
                "before": event.get("before"),
                "after": event.get("after"),
            }
            for event in M["audit"]
            if isinstance(event, dict) and (
                event.get("before") is not None or event.get("after") is not None
            )
        ]
        if audit_rows:
            st.markdown("#### Change details")
            st.dataframe(pd.DataFrame(audit_rows), hide_index=True, use_container_width=True)
    else:
        st.info("No audit events yet.")
