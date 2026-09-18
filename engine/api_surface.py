#!/usr/bin/env python3
"""
api_surface.py - public API summary grouped by subsystem.

Consumes scan.json and produces api.json: for each subsystem, the files with
their classes (name, signature, line) and functions (name, signature, line).
"""


def run_api(scan: dict) -> dict:
    files = scan["files"]
    subsystems = scan["stats"]["subsystems"]

    api = {s: {"files": {}, "stats": {"files": 0, "classes": 0, "functions": 0}} for s in subsystems}
    api["_root"] = {"files": {}, "stats": {"files": 0, "classes": 0, "functions": 0}}

    for rel, data in files.items():
        sub = rel.split("/")[0] if "/" in rel else "_root"
        if sub not in api:
            api[sub] = {"files": {}, "stats": {"files": 0, "classes": 0, "functions": 0}}
        entry = {"classes": [], "functions": [], "doc": data.get("doc", "")}
        for c in data.get("classes", []):
            entry["classes"].append({
                "name": c["name"],
                "line": c["lineno"],
                "end_line": c["end_lineno"],
                "methods": [{"name": m["name"], "sig": m["sig"], "line": m["lineno"]} for m in c["methods"]],
            })
        for fn in data.get("functions", []):
            entry["functions"].append({
                "name": fn["name"],
                "sig": fn["sig"],
                "line": fn["lineno"],
            })
        api[sub]["files"][rel] = entry
        api[sub]["stats"]["files"] += 1
        api[sub]["stats"]["classes"] += len(entry["classes"])
        api[sub]["stats"]["functions"] += len(entry["functions"])

    return api


if __name__ == "__main__":
    import json
    import sys
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(json.dumps(run_api(data), indent=2))
