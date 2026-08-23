import re
from datetime import datetime
from difflib import SequenceMatcher
import pandas as pd
from schemas.employee import TARGET_SCHEMA

TARGET_FIELDS = [
    "employee_id", "name", "email",
    "date_of_birth", "department", "joining_date"
]

ALIASES = {
    "employee_id": ["employee id", "employee code", "emp id", "emp code", "staff id", "staff code", "employee number"],
    "name": ["name", "employee name", "full name", "staff name", "employee full name"],
    "email": ["email", "email id", "email address", "mail", "mail id", "work email", "official email"],
    "date_of_birth": ["dob", "date of birth", "birth date", "birthdate", "birthday"],
    "department": ["department", "dept", "department name", "business unit"],
    "joining_date": ["joining date", "date joined", "join date", "doj", "date of joining", "start date"],
}

def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()

def similarity(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()

def infer_mappings_rules(columns, auto_threshold=0.90):
    results = []
    for col in columns:
        scores = []
        ncol = norm(col)
        for target in TARGET_FIELDS:
            score = similarity(col, target)
            for alias in ALIASES[target]:
                score = max(score, similarity(col, alias))
                if ncol == norm(alias):
                    score = 1.0
            scores.append((target, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        best, best_score = scores[0]
        second, second_score = scores[1]
        margin = best_score - second_score
        if best_score >= auto_threshold and margin >= 0.08:
            decision = "auto"
        elif best_score >= 0.70:
            decision = "review"
        else:
            decision = "unmapped"
        results.append({
            "source": str(col),
            "target": best if decision != "unmapped" else None,
            "confidence": round(best_score, 2),
            "runner_up": second,
            "runner_up_confidence": round(second_score, 2),
            "reason": "Deterministic semantic/alias match",
            "decision": decision,
        })
    return results

def merge_llm_results(rule_results, llm_results, auto_threshold=0.90):
    if not llm_results:
        return rule_results
    by_source = {x["source"]: x for x in llm_results.get("mappings", [])}
    merged = []
    for item in rule_results:
        llm = by_source.get(item["source"])
        if llm:
            item = {**item, **llm}
            # Keep conservative escalation policy.
            if float(item.get("confidence", 0)) >= auto_threshold and item.get("target"):
                item["decision"] = "auto"
            else:
                item["decision"] = "review" if item.get("target") else "unmapped"
        merged.append(item)
    return merged

def clean_value(field, value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    if not value:
        return None
    if field == "email":
        return value.lower()
    if field in ("name", "department"):
        return re.sub(r"\s+", " ", value)
    if field in ("date_of_birth", "joining_date"):
        for date_format in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, date_format).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return value
    return value

def validate_record(record, missing_fields=None):
    errors = []
    missing_fields = set(missing_fields or [])
    for field, definition in TARGET_SCHEMA.items():
        value = record.get(field)
        if field in missing_fields and not value:
            errors.append(f"Missing source column: {field}")
        elif not value:
            errors.append(f"Missing {field}")
        elif value and definition.get("type") == "email":
            if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", value):
                errors.append("Invalid email")
        elif value and definition.get("type") == "date":
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                errors.append(f"Invalid {field}")
    return errors

def build_records(df, mapping, missing_fields=None):
    usable = [m for m in mapping if m.get("target") and m.get("decision") in ("auto", "human_approved")]
    records = []
    for idx, row in df.iterrows():
        record = {field: None for field in TARGET_FIELDS}
        for m in usable:
            record[m["target"]] = clean_value(m["target"], row[m["source"]])
        errors = validate_record(record, missing_fields)
        records.append({
            "source_row": int(idx) + 2,
            "record": record,
            "errors": errors,
            "missing_fields": list(missing_fields or []),
            "status": "valid" if not errors else "review",
        })
    return records

def find_duplicates(records):
    seen = {}
    duplicates = []
    for i, item in enumerate(records):
        record = item["record"]
        key = record.get("employee_id") or record.get("email")
        if key:
            if key in seen:
                first_index = seen[key]
                first_record = records[first_index]["record"]
                different_fields = [
                    field for field in TARGET_FIELDS
                    if first_record.get(field) != record.get(field)
                ]
                duplicates.append((first_index, i, key, different_fields))
            else:
                seen[key] = i
    return duplicates

def find_duplicate_employee_ids(records, filter_rejected=True):
    """
    Detects duplicate employee IDs in records.
    Returns a dict with employee_id as key and list of record indices as value.
    Only includes IDs that appear more than once.
    """
    duplicates = {}
    for i, item in enumerate(records):
        if filter_rejected and item.get("status") == "rejected":
            continue
        emp_id = item["record"].get("employee_id")
        if emp_id:
            if emp_id not in duplicates:
                duplicates[emp_id] = []
            duplicates[emp_id].append(i)
    
    # Return only IDs with duplicates
    return {emp_id: indices for emp_id, indices in duplicates.items() if len(indices) > 1}
