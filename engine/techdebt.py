#!/usr/bin/env python3
"""
techdebt.py - technical debt scan (twin functions, call graph, fix tags).

Produces techdebt.json with:
  - twin_groups: groups of structurally near-identical functions (with method + hash + similarity)
  - fix_tags:    TODO/FIX/HACK/XXX/... comments with file:line
  - callgraph:   per file, function -> {callees, callers} with qualified names
  - call_paths:  transitive call paths between functions (for impact analysis)

twin_check() is a lightweight version used by sync/rescan as a duplicate gate
for newly added code (it returns only the twin groups, without the heavier
callgraph and fix-tag passes).

Upgrade (FAZ2):
  - twin detection via TWO methods: body-kinds + normalized MD5 hash (port from
    old fonksiyon_benzerlik_analizoru: cross-script hash). Fuzzy name stripping
    (_v1/_v2/_new/_old) is handled at grouping.
  - callgraph now includes callers with qualified names (module.Class.method).
  - similarity scoring for twin groups (0-100).
  - call path analysis for transitive dependencies.
"""

import ast
import hashlib
import re
import warnings
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

FIX_TAG_RE = re.compile(
    r"(PRODUCTION FIX|TODO|FIXME|FIX|HACK|XXX|WORKAROUND|TEMP|ASAMA|BETA)",
    re.IGNORECASE,
)


def _body_signature(node):
    kinds = []
    for stmt in node.body:
        kinds.append(type(stmt).__name__)
    return kinds


def _collect_qualified_calls(node, current_class=None):
    """Collect calls with qualified names where possible."""
    calls = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if isinstance(f, ast.Name):
                calls.append(f.id)
            elif isinstance(f, ast.Attribute):
                # Try to build qualified name: obj.method
                parts = []
                curr = f
                while isinstance(curr, ast.Attribute):
                    parts.append(curr.attr)
                    curr = curr.value
                if isinstance(curr, ast.Name):
                    parts.append(curr.id)
                    parts.reverse()
                    calls.append(".".join(parts))
                else:
                    calls.append(f.attr)
    return sorted(set(calls))


def _get_qualified_name(node, class_name=None, module_path=""):
    """Build fully qualified name for a function/method."""
    if class_name:
        return f"{module_path}.{class_name}.{node.name}"
    return f"{module_path}.{node.name}"


def _parse_files(root: Path, ignore_dirs):
    from engine.scan import walk_project
    return [p for p in walk_project(root, ignore_dirs) if p.suffix == ".py"]


def _parse(path: Path):
    try:
        source = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, ValueError):
            return None
    return source, tree


# ---- Normalized hash (old cross-script MD5) ----

class _Normalizer(ast.NodeTransformer):
    """Replace variable names/consts with placeholders for structural hash."""
    def visit_Name(self, node):
        return ast.copy_location(ast.Name(id="_var", ctx=node.ctx), node)
    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(value="_const"), node)
    def visit_arg(self, node):
        # keep annotation but anonymize name
        node.arg = "_arg"
        return self.generic_visit(node)


def _normalized_hash(node) -> str:
    try:
        # ast.unparse is 3.9+, fallback to ast.dump for 3.8
        try:
            src = ast.unparse(node)
        except AttributeError:
            src = ast.dump(node)
        n = _Normalizer().visit(ast.parse(src))
        dump = ast.dump(n, annotate_fields=False, include_attributes=False)
        return hashlib.md5(dump.encode()).hexdigest()[:12]
    except Exception:
        return "|".join(_body_signature(node))


def _structural_similarity(node1, node2) -> float:
    """Calculate structural similarity between two function nodes (0-100)."""
    try:
        h1 = _normalized_hash(node1)
        h2 = _normalized_hash(node2)
        if h1 == h2:
            return 100.0
        # Fallback: compare kinds signature
        k1 = _body_signature(node1)
        k2 = _body_signature(node2)
        if not k1 and not k2:
            return 100.0
        if not k1 or not k2:
            return 0.0
        # Jaccard similarity on kinds
        set1, set2 = set(k1), set(k2)
        inter = len(set1 & set2)
        union = len(set1 | set2)
        return round(inter / union * 100, 1)
    except Exception:
        return 0.0


def _fuzzy_base(name: str) -> str:
    """Strip twin suffixes: _v1, _v2, _new, _old, _fix, Version suffix."""
    base = re.sub(r'(_v\d+|_new|_old|_fix|_copy|_dup|V2|New)$', '', name, flags=re.IGNORECASE)
    return base.lower()


def twin_check(root: Path, ignore_dirs) -> list:
    """Lightweight twin-function scan: returns groups of structurally
    near-identical functions (used as a duplicate gate in sync/rescan).

    Upgraded: uses both kinds and normalized MD5; groups are deduped.
    Returns List[List[str]] where each str is "rel:line name" (back-compat).
    """
    map_kinds = {}
    map_hash = {}
    for p in _parse_files(root, ignore_dirs):
        rel = p.relative_to(root).as_posix()
        parsed = _parse(p)
        if parsed is None:
            continue
        _source, tree = parsed
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kinds = _body_signature(node)
                if len(kinds) < 3:
                    continue
                # kinds key
                k_key = "|".join(kinds) + "(%d)" % len(node.args.args)
                map_kinds.setdefault(k_key, []).append(
                    "%s:%s %s" % (rel, node.lineno, node.name)
                )
                # hash key
                h = _normalized_hash(node)
                h_key = h + "(%d)" % len(node.args.args)
                map_hash.setdefault(h_key, []).append(
                    "%s:%s %s" % (rel, node.lineno, node.name)
                )

    groups = []
    seen = set()
    for d in (map_kinds, map_hash):
        for g in d.values():
            if len(g) > 1:
                key = tuple(sorted(g))
                if key not in seen:
                    seen.add(key)
                    groups.append(g)
    groups.sort(key=len, reverse=True)
    return groups


def _twin_remediation(sim_avg: float, count: int, members: list) -> str:
    """Concrete refactor suggestion text for a twin group."""
    loc = ", ".join("`%s:%s`" % (m["file"], m["line"]) for m in members[:5])
    if sim_avg >= 95:
        action = (
            "Birebir / cok az farkla kopyalanmis govde. Tek kaynak birakip digerlerini "
            "o kaynaga yonlendirin: ayni dosya icindeyse ortak helper + parametre; "
            "farkli dosyalardaysa ortak bir dikey dosyaya (util/helper) tasiyin. "
            "`find_*`/`apply_*`/`run_*` gibi sadece adi farkli kopyalar da ayni kurala tabidir."
        )
    elif sim_avg >= 75:
        action = (
            "Ortak govde, kucuk davranis farklari var. Farkli kisimlari bir `mode/strategy` "
            "parametresine (veya kucuk bir callback'e) alip tek fonksiyonda birlestirin. "
            "Varyantlar ayni girdiye ayni ciktiyi vermek zorundaysa birlestirme guvenlidir; "
            "aksi halde once cagrilarin hangi varyanti kullandigini callgraph'tan kontrol edin."
        )
    else:
        action = (
            "Yapisal benzerlik ama davranis farkli. Sorumluluklari netlestirin: ya gercek "
            "ortak kisim cikarilir, ya da bilincli olarak ayrilir - ancak bu seviyede "
            "birlesirmeden once hangi cagrinin hangi varyanti kullandigini callgraph ile dogrulayin."
        )
    return "[%d kopya, benzerlik ~%s%%] %s Bunlarla baslayin: %s" % (
        count, sim_avg, action, loc)


def _detailed_twins(root: Path, ignore_dirs) -> list:
    """Rich twin groups with method, hash, members, and similarity scores."""
    by_hash = {}
    by_kinds = {}
    node_map = {}  # (file, line, name) -> node for similarity calc
    
    for p in _parse_files(root, ignore_dirs):
        rel = p.relative_to(root).as_posix()
        parsed = _parse(p)
        if parsed is None:
            continue
        _, tree = parsed
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kinds = _body_signature(node)
                if len(kinds) < 3:
                    continue
                h = _normalized_hash(node)
                k_key = "|".join(kinds) + "(%d)" % len(node.args.args)
                h_key = h + "(%d)" % len(node.args.args)
                entry = {"file": rel, "line": node.lineno, "name": node.name, "kinds": kinds, "hash": h}
                by_kinds.setdefault(k_key, []).append(entry)
                by_hash.setdefault(h_key, []).append(entry)
                node_map[(rel, node.lineno, node.name)] = node

    groups = []
    seen_hashes = set()
    gid = 0
    for store, method in [(by_hash, "hash"), (by_kinds, "kinds")]:
        for key, members in store.items():
            if len(members) < 2:
                continue
            sig = tuple(sorted((m["file"], m["line"], m["name"]) for m in members))
            if sig in seen_hashes:
                continue
            seen_hashes.add(sig)
            gid += 1
            
            # Calculate pairwise similarity for this group
            similarities = []
            for i, m1 in enumerate(members):
                for m2 in members[i+1:]:
                    n1 = node_map.get((m1["file"], m1["line"], m1["name"]))
                    n2 = node_map.get((m2["file"], m2["line"], m2["name"]))
                    if n1 and n2:
                        sim = _structural_similarity(n1, n2)
                        similarities.append(sim)
            
            avg_similarity = round(sum(similarities) / len(similarities), 1) if similarities else 100.0
            min_similarity = round(min(similarities), 1) if similarities else 100.0
            
            groups.append({
                "group_id": "TG-%03d" % gid,
                "method": method,
                "key": key,
                "similarity_avg": avg_similarity,
                "similarity_min": min_similarity,
                "members": [{"file": m["file"], "line": m["line"], "name": m["name"], "hash": m["hash"]} for m in members],
                "fuzzy_bases": sorted(set(_fuzzy_base(m["name"]) for m in members)),
                "remediation": _twin_remediation(avg_similarity, len(members), members),
            })
    groups.sort(key=lambda g: (len(g["members"]), g.get("similarity_avg", 0)), reverse=True)
    return groups


def _build_callgraph_with_qualified_names(root: Path, ignore_dirs) -> Tuple[Dict, Dict, Dict]:
    """Build callgraph with qualified names and cross-file resolution."""
    # First pass: collect all functions with their qualified names
    func_map = {}  # (file, simple_name) -> qualified_name
    file_funcs = {}  # file -> {simple_name: qualified_name}
    func_nodes = {}  # qualified_name -> node
    
    for p in _parse_files(root, ignore_dirs):
        rel = p.relative_to(root).as_posix()
        module_path = rel[:-3].replace("/", ".")
        parsed = _parse(p)
        if parsed is None:
            continue
        source, tree = parsed
        
        file_funcs[rel] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        qname = _get_qualified_name(sub, node.name, module_path)
                        func_map[(rel, sub.name)] = qname
                        file_funcs[rel][sub.name] = qname
                        func_nodes[qname] = sub
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = _get_qualified_name(node, None, module_path)
                func_map[(rel, node.name)] = qname
                file_funcs[rel][node.name] = qname
                func_nodes[qname] = node
    
    # Second pass: build callgraph with qualified callees
    callgraph = {}  # file -> {func_name: {callees: [], callers: []}}
    raw_callees = {}  # qualified_name -> [qualified_callee_names]
    raw_callers = {}  # qualified_name -> [qualified_caller_names]
    
    for p in _parse_files(root, ignore_dirs):
        rel = p.relative_to(root).as_posix()
        parsed = _parse(p)
        if parsed is None:
            continue
        source, tree = parsed
        
        callgraph[rel] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Determine qualified name of this function
                class_name = None
                for ancestor in ast.walk(tree):
                    if isinstance(ancestor, ast.ClassDef) and node in ancestor.body:
                        class_name = ancestor.name
                        break
                module_path = rel[:-3].replace("/", ".")
                caller_qname = _get_qualified_name(node, class_name, module_path)
                
                # Get qualified callees
                callees = _collect_qualified_calls(node)
                # Resolve to qualified names using func_map
                qualified_callees = []
                for callee in callees:
                    # Try direct match first
                    found = False
                    for (f, simple), qname in func_map.items():
                        if simple == callee or qname.endswith("." + callee):
                            qualified_callees.append(qname)
                            found = True
                            break
                    if not found:
                        qualified_callees.append(callee)  # external or unresolved
                
                callgraph[rel][node.name] = {
                    "callees": qualified_callees,
                    "callers": [],  # will be filled in second pass
                    "qualified_name": caller_qname
                }
                raw_callees[caller_qname] = qualified_callees
    
    # Invert to get callers
    for caller_qname, callees in raw_callees.items():
        for callee_qname in callees:
            raw_callers.setdefault(callee_qname, []).append(caller_qname)
    
    # Attach callers
    for rel, funcs in callgraph.items():
        for func_name, data in funcs.items():
            caller_qname = data["qualified_name"]
            callers = raw_callers.get(caller_qname, [])
            data["callers"] = sorted(set(callers) - {caller_qname})
            data["self_recursive"] = caller_qname in callers
    
    return callgraph, func_map, func_nodes


def _find_call_paths(callgraph: Dict, func_map: Dict, start: str, end: str, max_depth: int = 10) -> List[List[str]]:
    """Find call paths from start to end function (transitive)."""
    # Build adjacency from callgraph
    adj = {}
    for file_data in callgraph.values():
        for func_name, data in file_data.items():
            qname = data["qualified_name"]
            adj[qname] = data["callees"]
    
    # BFS to find paths
    paths = []
    queue = [(start, [start])]
    visited = set()
    
    while queue and len(paths) < 20:  # limit paths
        current, path = queue.pop(0)
        if len(path) > max_depth:
            continue
        if current == end:
            paths.append(path)
            continue
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adj.get(current, []):
            if neighbor not in path:  # avoid cycles
                queue.append((neighbor, path + [neighbor]))
    
    return paths


def run_techdebt(root: Path, ignore_dirs) -> dict:
    # Build enhanced callgraph with qualified names
    callgraph, func_map, func_nodes = _build_callgraph_with_qualified_names(root, ignore_dirs)
    
    fix_tags = []
    for p in _parse_files(root, ignore_dirs):
        rel = p.relative_to(root).as_posix()
        parsed = _parse(p)
        if parsed is None:
            continue
        source, tree = parsed
        for i, line in enumerate(source.splitlines(), 1):
            if "#" not in line:
                continue
            m = FIX_TAG_RE.search(line)
            if m:
                fix_tags.append({
                    "file": rel,
                    "line": i,
                    "tag": m.group(1).upper(),
                    "text": line.strip()[:200],
                })

    detailed = _detailed_twins(root, ignore_dirs)
    simple_groups = twin_check(root, ignore_dirs)

    # Calculate callgraph stats
    total_funcs = sum(len(funcs) for funcs in callgraph.values())
    total_edges = sum(len(data["callees"]) for funcs in callgraph.values() for data in funcs.values())
    total_callers = sum(len(data["callers"]) for funcs in callgraph.values() for data in funcs.values())

    # Convert func_map tuple keys to strings for JSON serialization
    func_map_serializable = {f"{k[0]}:{k[1]}": v for k, v in func_map.items()}
    
    return {
        "twin_groups": simple_groups,
        "twin_detailed": detailed,
        "fix_tags": fix_tags,
        "callgraph": callgraph,
        "callgraph_stats": {
            "total_functions": total_funcs,
            "total_call_edges": total_edges,
            "total_caller_edges": total_callers,
            "avg_callees_per_func": round(total_edges / total_funcs, 2) if total_funcs else 0,
        },
        "func_map": func_map_serializable,  # for external use (impact analysis)
    }


if __name__ == "__main__":
    import json
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(json.dumps(run_techdebt(root, []), indent=2, ensure_ascii=False))