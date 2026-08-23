from html import escape
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from schemas.employee import Employee

app = FastAPI(title="NEXUS Mock Target API")
STORE = {}

@app.get("/")
def root():
    return {
        "service": "NEXUS Mock Target API",
        "status": "ok",
        "employee_count": len(STORE),
        "employees_url": "/employees",
        "health_url": "/health",
        "docs_url": "/docs",
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/employees")
def create_employee(employee: Employee):
    # Intentional demo failure to show retry behavior.
    if employee.employee_id.endswith("999"):
        raise HTTPException(status_code=500, detail="Simulated target API failure for retry demo")
    if employee.employee_id in STORE:
        raise HTTPException(
            status_code=409,
            detail="Employee ID already exists; refusing to overwrite target record",
        )
    STORE[employee.employee_id] = employee.model_dump(mode="json")
    return {"success": True, "employee_id": employee.employee_id}

@app.put("/employees/{employee_id}")
def update_employee(employee_id: str, employee: Employee):
    if employee_id != employee.employee_id:
        raise HTTPException(status_code=400, detail="Employee ID cannot be changed during update")
    if employee_id not in STORE:
        raise HTTPException(status_code=404, detail="Employee not found")
    STORE[employee_id] = employee.model_dump(mode="json")
    return {"success": True, "employee_id": employee_id}

@app.delete("/employees/{employee_id}")
def delete_employee(employee_id: str):
    if employee_id not in STORE:
        raise HTTPException(status_code=404, detail="Employee not found")
    del STORE[employee_id]
    return {"success": True, "employee_id": employee_id}

@app.get("/employees")
def list_employees(request: Request):
    employees = list(STORE.values())
    if "text/html" not in request.headers.get("accept", ""):
        return employees

    fields = list(Employee.model_fields)
    header_cells = "".join(f"<th>{escape(field)}</th>" for field in fields)
    rows = "".join(
        "<tr>" + "".join(
            f"<td>{escape(str(employee.get(field) or ''))}</td>"
            for field in fields
        ) + "</tr>"
        for employee in employees
    )
    if not rows:
        rows = f'<tr><td colspan="{len(fields)}">No employees stored</td></tr>'
    json_block = escape(json.dumps(employees, indent=2, default=str))

    return HTMLResponse(
        "<html><head><title>Employees</title>"
        "<style>body{font-family:Arial,sans-serif;margin:2rem;color:#202124}"
        "table{border-collapse:collapse;width:100%;max-width:1200px}"
        "th,td{border:1px solid #d0d7de;padding:10px;text-align:left}"
        "th{background:#eef2f6}tr:nth-child(even){background:#f8fafc}"
        "pre{background:#f6f8fa;border:1px solid #d0d7de;padding:1rem;"
        "overflow:auto;border-radius:4px}"
        "</style></head><body><h1>Employees</h1>"
        "<h2>JSON</h2><pre>" + json_block + "</pre>"
        "<h2>Table</h2>"
        f"<table><thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{rows}</tbody></table></body></html>"
    )
