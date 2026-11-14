"""
Brain starter: agent loop + tools + structured answer + basic citation check.
Runs on a MOCK database so you can build before Person 1's real DB exists.

Setup:
    pip install anthropic python-dotenv
    export ANTHROPIC_API_KEY=...
    python brain_starter.py "What is the fire rating of door D-214?"

When the real DB arrives: replace build_mock_db() with sqlite3.connect("building.db").
"""

import json
import os
import sqlite3
import sys

import anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY (and optional ANTHROPIC_WORKSPACE_ID) from .env

MODEL = os.environ.get("BRAIN_MODEL", "claude-sonnet-5-5")  # cheaper for dev; switch to opus for final runs
MAX_STEPS = 8

# ---------------------------------------------------------------------------
# 1. MOCK DATABASE (same tables as the team contract)
# ---------------------------------------------------------------------------

def build_mock_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE Sheet(id TEXT PRIMARY KEY, number TEXT, title TEXT, file TEXT, page INT);
    CREATE TABLE TextItem(id TEXT PRIMARY KEY, sheet_id TEXT, text TEXT, bbox TEXT);
    CREATE TABLE ScheduleRow(id TEXT PRIMARY KEY, table_name TEXT, key TEXT,
                             attrs_json TEXT, cell_bboxes_json TEXT, sheet_id TEXT);
    CREATE TABLE Element(id TEXT PRIMARY KEY, kind TEXT, tag TEXT, sheet_id TEXT, bbox TEXT, ifc_guid TEXT);
    """)
    db.executemany("INSERT INTO Sheet VALUES (?,?,?,?,?)", [
        ("S1", "A-101", "1. kerroksen pohjapiirustus / Floor plan L1", "A-101.pdf", 0),
        ("S2", "A-601", "Ovikaavio / Door schedule", "A-601.pdf", 0),
    ])
    db.executemany("INSERT INTO TextItem VALUES (?,?,?,?)", [
        ("T1", "S1", "D-214", json.dumps([812, 433, 840, 445])),
        ("T2", "S1", "PALO-OVI EI60", json.dumps([700, 900, 790, 912])),
    ])
    db.executemany("INSERT INTO ScheduleRow VALUES (?,?,?,?,?,?)", [
        ("R88", "Door schedule", "D-214",
         json.dumps({"type": "Steel door", "fire_rating": "EI60", "width_mm": "1000"}),
         json.dumps({"fire_rating": [410, 220, 455, 232], "width_mm": [460, 220, 500, 232]}),
         "S2"),
    ])
    db.executemany("INSERT INTO Element VALUES (?,?,?,?,?,?)", [
        ("E412", "door", "D-214", "S1", json.dumps([800, 420, 850, 460]), None),
    ])
    return db


DB = build_mock_db()

# ---------------------------------------------------------------------------
# 2. TOOLS: plain Python functions + JSON schemas the model sees
# ---------------------------------------------------------------------------

def tool_list_sheets() -> list:
    return [dict(r) for r in DB.execute("SELECT id, number, title FROM Sheet")]


def tool_search_text(query: str, limit: int = 10) -> list:
    # Placeholder: substring match. Replace with BM25 + embeddings + glossary later.
    q = f"%{query}%"
    rows = DB.execute(
        "SELECT 'TextItem:'||id AS evidence_id, sheet_id, text, bbox FROM TextItem WHERE text LIKE ? "
        "UNION ALL SELECT 'Sheet:'||id, id, title, NULL FROM Sheet WHERE title LIKE ? LIMIT ?",
        (q, q, limit)).fetchall()
    return [dict(r) for r in rows]


def tool_get_schedule_row(key: str) -> list:
    rows = DB.execute("SELECT * FROM ScheduleRow WHERE key = ?", (key,)).fetchall()
    out = []
    for r in rows:
        out.append({
            "evidence_id": f"ScheduleRow:{r['id']}",
            "table": r["table_name"], "key": r["key"], "sheet_id": r["sheet_id"],
            "attributes": json.loads(r["attrs_json"]),
            "cell_evidence_ids": {c: f"ScheduleRow:{r['id']}.cell:{c}"
                                  for c in json.loads(r["cell_bboxes_json"])},
        })
    return out


def tool_find_element(tag: str) -> list:
    rows = DB.execute("SELECT * FROM Element WHERE tag = ?", (tag,)).fetchall()
    return [{"evidence_id": f"Element:{r['id']}", **dict(r)} for r in rows]


TOOL_FUNCS = {
    "list_sheets": lambda a: tool_list_sheets(),
    "search_text": lambda a: tool_search_text(a["query"], a.get("limit", 10)),
    "get_schedule_row": lambda a: tool_get_schedule_row(a["key"]),
    "find_element": lambda a: tool_find_element(a["tag"]),
}

TOOLS = [
    {"name": "list_sheets",
     "description": "List all drawing sheets (id, sheet number, title). Use first to orient yourself.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "search_text",
     "description": ("Search all text on all drawings. Matches tags (e.g. 'D-214'), codes ('EI60') "
                     "and words. Drawings may be in Finnish, Swedish or English: try translations "
                     "(door = ovi = dörr). Returns evidence_ids with sheet and bbox."),
     "input_schema": {"type": "object",
                      "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                      "required": ["query"]}},
    {"name": "get_schedule_row",
     "description": ("Get rows from schedules/tables (door, window, room schedules) by their key/tag, "
                     "e.g. 'D-214'. Returns attributes and a cell-level evidence_id per attribute."),
     "input_schema": {"type": "object", "properties": {"key": {"type": "string"}},
                      "required": ["key"]}},
    {"name": "find_element",
     "description": "Find a tagged element (door, window, room) on plan drawings by its tag.",
     "input_schema": {"type": "object", "properties": {"tag": {"type": "string"}},
                      "required": ["tag"]}},
    {"name": "submit_answer",
     "description": ("Submit the FINAL answer. Every claim must list evidence_ids returned by tools. "
                     "If you could not find verifiable evidence, set answer to null and explain."),
     "input_schema": {
         "type": "object",
         "properties": {
             "answer": {"type": ["string", "null"]},
             "claims": {"type": "array", "items": {
                 "type": "object",
                 "properties": {"text": {"type": "string"},
                                "evidence": {"type": "array", "items": {"type": "string"}}},
                 "required": ["text", "evidence"]}},
             "confidence": {"type": "number", "description": "0..1, your honest estimate"},
         },
         "required": ["answer", "claims", "confidence"]}},
]

SYSTEM = """You answer questions about construction drawings and building models.
Rules:
- Always use tools to find information. Never answer from memory.
- Never guess numbers. Counts and measurements must come from tools.
- Every claim must cite evidence_ids exactly as returned by tools.
- Drawings may be in Finnish, Swedish or English; search with translations.
- If evidence is missing or contradictory, submit answer = null and say what you found.
- Finish by calling submit_answer exactly once."""

# ---------------------------------------------------------------------------
# 3. AGENT LOOP
# ---------------------------------------------------------------------------

def run_agent(question: str, client: anthropic.Anthropic) -> dict:
    messages = [{"role": "user", "content": question}]
    seen_evidence: set[str] = set()
    trace = []

    for step in range(MAX_STEPS):
        resp = client.messages.create(model=MODEL, max_tokens=2048, system=SYSTEM,
                                      tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            # Model replied with text instead of a tool: nudge it to submit.
            messages.append({"role": "user", "content": "Call submit_answer now."})
            continue

        results = []
        for tu in tool_uses:
            if tu.name == "submit_answer":
                return {"question": question, **tu.input, "trace": trace,
                        "seen_evidence": sorted(seen_evidence)}
            try:
                out = TOOL_FUNCS[tu.name](tu.input)
                collect_evidence_ids(out, seen_evidence)
                content = json.dumps(out, ensure_ascii=False)
            except Exception as e:  # return errors to the model instead of crashing
                content = f"ERROR: {e}"
            trace.append({"step": step, "tool": tu.name, "input": tu.input})
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})
        messages.append({"role": "user", "content": results})

    return {"question": question, "answer": None, "claims": [], "confidence": 0.0,
            "error": "max_steps reached", "trace": trace}


def collect_evidence_ids(obj, acc: set):
    """Record every evidence_id the tools actually returned (used by the verifier)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "evidence_id" and isinstance(v, str):
                acc.add(v)
            elif k == "cell_evidence_ids" and isinstance(v, dict):
                acc.update(v.values())
            else:
                collect_evidence_ids(v, acc)
    elif isinstance(obj, list):
        for x in obj:
            collect_evidence_ids(x, acc)

# ---------------------------------------------------------------------------
# 4. VERIFIER (v0: citation existence). Extend: value-in-evidence, recompute, VLM check.
# ---------------------------------------------------------------------------

def verify(result: dict) -> dict:
    seen = set(result.get("seen_evidence", []))
    problems = []
    for c in result.get("claims", []):
        if not c["evidence"]:
            problems.append(f"claim without evidence: {c['text']}")
        for ev in c["evidence"]:
            if ev not in seen:
                problems.append(f"cited evidence never returned by a tool: {ev}")
    if problems:
        result["confidence"] = min(result.get("confidence", 0), 0.2)
    result["verification"] = {"ok": not problems, "problems": problems}
    return result


def answer(question: str) -> dict:
    """The function Person 3's UI calls."""
    ws = os.environ.get("ANTHROPIC_WORKSPACE_ID")  # only needed for keys not scoped to a workspace
    client = anthropic.Anthropic(default_headers={"anthropic-workspace-id": ws} if ws else None)
    return verify(run_agent(question, client))


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What is the fire rating of door D-214?"
    print(json.dumps(answer(q), indent=2, ensure_ascii=False))