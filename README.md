# NEXUS

### Supervised-Autonomy Agent for Client Data Migration & Integration

NEXUS is an AI-powered data migration agent designed to ingest multiple client data files with different schemas, intelligently map and clean the data, validate records, detect conflicts, and push clean records into a target system.

The core design principle is **supervised autonomy**:

> **Automate what is safe and high-confidence. Escalate what is ambiguous, conflicting, or requires human judgment.**

The agent uses deterministic rules for validation, cleaning, duplicate detection, API handling, and retries, while using Groq-based LLM inference specifically for semantic field mapping. Human reviewers are brought into the workflow only when the agent cannot make a sufficiently confident or safe decision.

---

## What NEXUS Does

NEXUS addresses a common client migration problem where different source systems contain the same type of entity but use different:

* Column names
* Data formats
* Date formats
* Field conventions
* Data quality standards
* Duplicate records

For example:

```text
Legacy System                    Target System

emp_id             ───────────→ employee_id
employee_name      ───────────→ name
mail               ───────────→ email
dob                ───────────→ date_of_birth
department         ───────────→ department
```

The agent can infer these relationships without requiring the user to manually configure every mapping.

---

## Key Features

### 1. Multi-file ingestion

Supports CSV and Excel files representing the same entity with different schemas.

### 2. Intelligent field mapping

Uses a combination of:

* Deterministic aliases/rules
* Semantic similarity
* Groq LLM inference

Mappings are automatically approved only when they meet the confidence boundary:

**≥90% confidence + ≥8% margin over the runner-up**

Ambiguous mappings are sent to the human review queue.

### 3. Automated data cleaning

Safe transformations are performed automatically, including:

* Email normalization
* Whitespace cleanup
* Date format reconciliation
* Schema/type normalization

### 4. Data validation

The agent validates:

* Required fields
* Email formats
* Date formats
* Field types
* Target schema requirements

### 5. Duplicate detection

Detects both:

* Exact duplicates
* Conflicting duplicates

Conflicting records are escalated instead of automatically deciding which record is authoritative.

### 6. Human-in-the-loop review

The review queue allows users to:

* Approve ambiguous mappings
* Correct invalid fields
* Resolve duplicates
* Edit failed records
* Retry failed pushes

### 7. Target API integration

The current prototype includes a FastAPI mock target system that intentionally simulates failures such as:

* HTTP 409 duplicate conflicts
* HTTP 500 transient failures

This allows the complete recovery workflow to be demonstrated locally.

### 8. Audit trail

Every important action is recorded, including:

* Timestamp
* Action performed
* Record ID
* Reason
* Before state
* After state
* Human approval/correction

---

# Architecture

```text
                  CSV / Excel Files
                         │
                         ▼
                  ┌─────────────┐
                  │ File Parser │
                  └──────┬──────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ Agent Orchestrator   │
              └──────────┬──────────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      Rule-based Mapping      Groq Semantic
      & Validation            Inference
             │                       │
             └───────────┬───────────┘
                         ▼
                  Mapping Merge
                         │
                         ▼
               Clean & Validate
                         │
                         ▼
                Duplicate Detection
                         │
                         ▼
              ┌─────────────────────┐
              │ Escalation Queue    │
              └──────────┬──────────┘
                         │
                    Human Review
                         │
                         ▼
                Target API / Push
                         │
                         ▼
                   Audit Trail
```

The architecture intentionally separates LLM-based semantic interpretation from deterministic execution logic.

---

# Autonomy vs Human Escalation

NEXUS does not try to use the LLM for every decision.

### Agent handles automatically

| Scenario                     | Decision            |
| ---------------------------- | ------------------- |
| Exact field alias            | Auto                |
| High-confidence mapping ≥90% | Auto                |
| ≥8% confidence gap           | Auto                |
| Lowercase email              | Auto                |
| Whitespace cleanup           | Auto                |
| Unambiguous date conversion  | Auto                |
| Schema validation            | Auto                |
| Duplicate detection          | Auto                |
| HTTP 500 / timeout           | Retry automatically |

### Agent escalates

| Scenario                    | Decision            |
| --------------------------- | ------------------- |
| Mapping confidence 70–89%   | Human review        |
| Confidence gap <8%          | Human review        |
| Missing required field      | Human review        |
| Invalid/unparseable date    | Human review        |
| Malformed email             | Human review        |
| Conflicting duplicate       | Human review        |
| HTTP 409 duplicate key      | Human review + edit |
| Business-rule/API rejection | Human review        |

The decision boundary is intentionally conservative because a wrong field mapping can affect every migrated record, while conflicts often require business context that the model does not have.

---

# Technology Stack

| Layer             | Technology              |
| ----------------- | ----------------------- |
| Language          | Python                  |
| UI                | Streamlit               |
| LLM               | Groq API                |
| Model             | `openai/gpt-oss-20b`    |
| Data Processing   | Pandas                  |
| Schema Validation | Pydantic                |
| Excel Processing  | OpenPyXL                |
| Target API        | FastAPI                 |
| API Server        | Uvicorn                 |
| Configuration     | `.env`                  |
| AI Architecture   | Rule-based + LLM hybrid |
| Persistence       | In-memory prototype     |
| Sample Data       | CSV + Excel             |

The current implementation deliberately keeps the LLM isolated to semantic mapping while deterministic Python logic handles validation, cleaning, dates, duplicates, API calls, and retries.

---

# Project Structure

```text
nexus/
│
├── app.py
├── requirements.txt
├── .env.example
│
├── agent/
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── groq_client.py
│   └── rules.py
│
├── api/
│   ├── __init__.py
│   └── mock_target_api.py
│
├── schemas/
│   ├── __init__.py
│   └── employee.py
│
├── sample_data/
│   ├── employees_legacy.csv
│   ├── employees_hr.xlsx
│   └── employees_ambiguous.csv
│
├── APPROACH.md
├── SETUP.md
└── README.md
```

### Important files

**`app.py`**
Streamlit application, migration UI, escalation queue, editing workflow and audit display.

**`agent/orchestrator.py`**
Coordinates the migration workflow.

**`agent/rules.py`**
Contains deterministic mapping, validation and cleaning logic.

**`agent/groq_client.py`**
Handles Groq LLM integration for semantic field mapping.

**`api/mock_target_api.py`**
FastAPI mock target system with simulated success and failure responses.

**`schemas/employee.py`**
Defines the target employee schema.

---

# Local Setup

## Prerequisites

* Python 3.9+
* pip
* Groq API key

Python 3.10+ is recommended based on the tested setup.

## 1. Clone the repository

```bash
git clone <repository-url>
cd nexus
```

## 2. Create a virtual environment

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure environment variables

Copy the example environment file.

### Windows

```powershell
Copy-Item .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Configure:

```ini
GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=openai/gpt-oss-20b
TARGET_API_URL=http://localhost:8099
```

---

# Running the Application

NEXUS requires two processes.

## Terminal 1 — Mock Target API

```bash
uvicorn api.mock_target_api:app --reload --port 8099
```

The mock API will run on:

```text
http://localhost:8099
```

## Terminal 2 — Streamlit UI

```bash
streamlit run app.py
```

The UI will be available at:

```text
http://localhost:8501
```

Detailed platform-specific setup is available in `SETUP.md`.

---

# Demo Walkthrough

Three sample files are included:

```text
sample_data/employees_legacy.csv
sample_data/employees_hr.xlsx
sample_data/employees_ambiguous.csv
```

### Step 1 — Upload

Upload all three files through the Streamlit interface.

### Step 2 — Start Migration

Click:

**🚀 Start Migration**

The agent will:

1. Parse the files
2. Infer field mappings
3. Validate records
4. Detect duplicates
5. Create escalation items

### Step 3 — Review Mappings

Example:

```text
emp_id          → employee_id       1.00    AUTO
employee_name   → name              0.95    AUTO
mail            → email             0.95    AUTO
dob             → date_of_birth     1.00    AUTO
Staff Ref       → employee_id      ~0.72    REVIEW
```

### Step 4 — Resolve Escalations

The demo intentionally contains cases such as:

```text
Staff Ref
31/02/1994
Conflicting duplicate employee ID
```

The human reviewer can approve, correct, reject or resolve these cases.

### Step 5 — Push Records

Click:

**📤 Push Ready Records**

Successful records are pushed to the mock target API.

### Step 6 — Handle Failures

If the target API returns a transient error:

```text
HTTP 500
```

the agent retries automatically.

For a duplicate-key conflict:

```text
HTTP 409
```

the agent escalates and allows the user to edit the record before retrying.

### Step 7 — Review Audit Trail

The audit trail shows the sequence of:

```text
Load → Map → Validate → Review → Push → Edit → Retry
```

along with before/after values and reasons for changes.

---

# Design Principles

### 1. LLM where semantics matter

The LLM is used for interpreting relationships between differently named fields.

### 2. Deterministic logic where correctness matters

Validation, date handling, duplicates, API calls and retries are handled through deterministic code rather than relying on model output.

### 3. Conservative autonomy

The agent only acts autonomously when the confidence and risk thresholds are acceptable.

### 4. Human-in-the-loop

Ambiguous or high-impact decisions are explicitly surfaced rather than silently guessed.

### 5. Explainability

Every escalation explains why the agent stopped and what information the human needs to provide.

### 6. Recovery instead of failure

Failed records can be edited and retried without restarting the entire migration.

---

# What I Would Build Next

The current prototype uses a mock target API. The next stage would focus on production readiness:

### Production Integration

* Real HR-system connectors
* Workday / BambooHR / ADP integrations
* PostgreSQL-backed migration state
* Async processing using Celery
* Authentication and RBAC
* Secure secret management
* PII masking

### Intelligence

* Learn mappings from previous human approvals
* Organization-specific mapping memory
* Anomaly detection
* Cross-file reconciliation
* Schema versioning

### Observability

Track:

* Mapping accuracy
* Escalation rate
* Human correction rate
* Push success rate
* Retry rate
* Error categories

These metrics can then be used to continuously recalibrate the confidence thresholds.

---

# Current Prototype Scope

This repository demonstrates the complete migration workflow locally:

```text
Multi-file ingestion
        ↓
Semantic field mapping
        ↓
Data cleaning
        ↓
Validation
        ↓
Duplicate detection
        ↓
Human escalation
        ↓
Target API push
        ↓
Failure recovery
        ↓
Audit trail
```

The focus of the prototype is not production-scale infrastructure; it is demonstrating a **defensible agent architecture and a clear autonomy boundary**.

---

# Documentation

| Document           | Purpose                                              |
| ------------------ | ---------------------------------------------------- |
| `README.md`        | Project overview, architecture, tech stack and setup |
| `APPROACH.md`      | Autonomy vs escalation decisions and roadmap         |
| `SETUP.md`         | Detailed local setup and troubleshooting             |
| `QUICKSTART.md`    | Fast 5-minute demo guide                             |
| `DECISION_TREE.md` | Detailed escalation decision logic                   |
| `SUMMARY.md`       | Executive-level overview                             |

---

## Core Principle

> **NEXUS does not try to automate everything. It automates what it can confidently justify, and escalates what requires human judgment.**
