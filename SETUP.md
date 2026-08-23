# NEXUS — Local Run Instructions

## Prerequisites

* Python 3.9+ (3.10+ recommended/tested)
* pip
* Groq API key

The application uses Groq for semantic field mapping.

## 1. Create the Environment

### Windows

```powershell
cd <project-directory>

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### macOS / Linux

```bash
cd <project-directory>

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Configure Environment Variables

Copy the example environment file:

### Windows

```powershell
Copy-Item .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Update `.env`:

```ini
GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=openai/gpt-oss-20b
TARGET_API_URL=http://localhost:8099
```

A Groq API key can be created from the Groq Console.

## 3. Start the Mock Target API

Open **Terminal 1** in the project directory.

### Windows

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn api.mock_target_api:app --reload --port 8099
```

### macOS / Linux

```bash
source .venv/bin/activate
uvicorn api.mock_target_api:app --reload --port 8099
```

The API should be available at:

```text
http://localhost:8099
```

The mock API intentionally simulates scenarios such as HTTP 409 and HTTP 500 so that the retry and escalation workflows can be demonstrated.

## 4. Start the Streamlit Application

Open **Terminal 2** in the project directory.

Activate the virtual environment and run:

```bash
streamlit run app.py
```

The application will open at:

```text
http://localhost:8501
```

## 5. Run the Demo

Upload the sample files from:

```text
sample_data/
├── employees_legacy.csv
├── employees_hr.xlsx
└── employees_ambiguous.csv
```

Then:

1. Click **Start Migration**.
2. Review the field mappings and confidence scores.
3. Resolve the ambiguous `Staff Ref` mapping.
4. Correct the invalid date.
5. Resolve duplicate records if prompted.
6. Click **Push Ready Records**.
7. Review successful and failed API operations.
8. Use **Edit & Push** or retry for failed records.
9. Review the **Audit Trail**.

The sample data is intentionally designed to demonstrate both autonomous decisions and human escalation.

## 6. Expected Demonstration

The demo should show three important behaviours:

### Autonomous

```text
emp_id → employee_id
mail → email
dob → date_of_birth
USER@EXAMPLE.COM → user@example.com
```

These are high-confidence or deterministic transformations and require no human approval.

### Human Escalation

```text
Staff Ref → employee_id / name
31/02/1994 → invalid date
Same employee_id + different department → conflict
```

These cases require human judgment and are therefore placed in the review queue.

### Failure Recovery

The mock API can return:

```text
HTTP 500 → automatic retry
HTTP 409 → human review + edit & retry
```

This demonstrates that a failed record does not require restarting the complete migration.

## Troubleshooting

### Groq module missing

```bash
pip install groq>=0.30
```

### Port 8099 connection refused

Make sure the Mock Target API is running in Terminal 1:

```bash
uvicorn api.mock_target_api:app --reload --port 8099
```

### GROQ_API_KEY not found

Check that `.env` exists in the project root and contains:

```ini
GROQ_API_KEY=<your-key>
```

Restart Streamlit after changing `.env`.

### Target API returns 409

This is an intentional demo scenario. Use **Edit & Push** and change the employee ID to a unique value.

## Project Entry Points

```text
app.py                    → Streamlit application
agent/orchestrator.py     → Agent workflow
agent/rules.py            → Deterministic mapping/validation/cleaning
agent/groq_client.py      → Groq semantic mapping
api/mock_target_api.py    → Mock target system
schemas/employee.py       → Target schema
sample_data/              → Demo migration files
```

The architecture intentionally separates deterministic business logic from LLM-based semantic interpretation.
