from datetime import datetime
from .rules import TARGET_FIELDS, infer_mappings_rules, merge_llm_results, build_records, find_duplicates
from .groq_client import infer_mappings_with_groq

def analyze_file(df, filename, use_groq=True, confidence_threshold=0.90):
    rule_mapping = infer_mappings_rules(df.columns, confidence_threshold)
    llm_mapping = None
    if use_groq:
        try:
            from schemas.employee import TARGET_SCHEMA
            llm_mapping = infer_mappings_with_groq(df.columns, TARGET_SCHEMA)
        except Exception:
            llm_mapping = None
    mapping = merge_llm_results(rule_mapping, llm_mapping, confidence_threshold)
    for item in mapping:
        item["file"] = filename

    mapped_targets = {m["target"] for m in mapping if m.get("target")}
    missing_fields = [field for field in TARGET_FIELDS if field not in mapped_targets]
    records = build_records(df, mapping, missing_fields)
    for record in records:
        record["file"] = filename

    escalations = []
    for m in mapping:
        if m["decision"] in ("review", "unmapped"):
            escalations.append({
                "type": "mapping",
                "file": filename,
                "row": "-",
                "message": f"Ambiguous or unmapped source field: {m['source']}",
                "item": m,
            })

    for item in records:
        if item["status"] == "review":
            escalations.append({
                "type": "validation",
                "file": filename,
                "row": item["source_row"],
                "message": "; ".join(item["errors"]),
                "item": item,
            })

    return mapping, records, escalations

def add_duplicate_escalations(records, escalations):
    for a, b, key, different_fields in find_duplicates(records):
        escalations.append({
            "type": "duplicate",
            "file": records[b]["file"],
            "row": records[b]["source_row"],
            "message": (
                f"Conflicting duplicate using key: {key}. "
                f"Different fields: {', '.join(different_fields)}"
                if different_fields
                else f"Exact duplicate using key: {key}"
            ),
            "item": records[b],
            "duplicate_of": records[a],
            "different_fields": different_fields,
        })
    return escalations

def timestamp():
    return datetime.now().strftime("%H:%M:%S")
