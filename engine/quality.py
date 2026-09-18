#!/usr/bin/env python3
"""
quality.py - code quality scoring + technical issue detection.

Ported from old derin_rapor_olusturucu.py:262 kalite_puanla + 321 teknik_sorunlari_bul
but adapted to new scan.json shape (scan.py output).

Produces quality.json:
  {
    "by_file": { "rel/path.py": {scores, issues[]} },
    "by_subsystem": { "sub": {avg_scores, total_issues} },
    "summary": {total_files, avg_total}
  }

Scores per file (0-10 each, Total 0-40):
  Aktiflik    - import + class density
  Gereklilik  - line count / functional density
  Kod Kalitesi- decorator + method density
  Butunluk    - class/method/function/import presence

Issues per file:
  - Asiri buyuk dosya (>1000 satir, kritik if >1500)
  - Fazla bagimlilik (>20 imports)
  - Sinif tabanli yapi eksik (>5 fonksiyon ama 0 sinif)
  - Dekorator kullanimi eksik (>5 metod ama 0 decorator)
"""

import json
import ast
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set


def score_file(fdata: dict) -> dict:
    if not fdata:
        return {"Aktiflik": 0, "Gereklilik": 0, "Kod Kalitesi": 0, "Butunluk": 0, "Toplam": 0}

    lines = fdata.get("lines", 0)
    classes = fdata.get("classes", [])
    functions = fdata.get("functions", [])
    imports = fdata.get("imports", [])

    # Aktiflik: import + class count
    import_score = min(len(imports) * 1.5, 5)
    class_score = min(len(classes) * 2, 5)
    aktiflik = min(import_score + class_score, 10)

    # Gereklilik: line count
    if lines > 500:
        gereklilik = 10
    elif lines > 200:
        gereklilik = 8
    elif lines > 50:
        gereklilik = 6
    elif lines > 10:
        gereklilik = 4
    else:
        gereklilik = 2

    # Kod Kalitesi: decorator + method presence
    kalite = 5
    for c in classes:
        if c.get("methods"):
            kalite += 1
        for m in c.get("methods", []):
            if m.get("decorators"):
                kalite += 0.5
    kalite = min(kalite, 10)

    # Butunluk: class/method/function/import presence
    butunluk = 0
    if classes:
        butunluk += 4
    if any(c.get("methods") for c in classes):
        butunluk += 3
    if functions:
        butunluk += 2
    if imports:
        butunluk += 1
    butunluk = min(butunluk, 10)

    return {
        "Aktiflik": round(aktiflik, 1),
        "Gereklilik": gereklilik,
        "Kod Kalitesi": round(kalite, 1),
        "Butunluk": butunluk,
        "Toplam": round(aktiflik + gereklilik + kalite + butunluk, 1),
    }


def _collect_issues_for_file(rel: str, fdata: dict, source_code: str) -> List[Dict[str, Any]]:
    """Collect all model-free issues for a single file."""
    if not fdata:
        return []
    
    lines = fdata.get("lines", 0)
    classes = fdata.get("classes", [])
    functions = fdata.get("functions", [])
    imports = fdata.get("imports", [])
    issues = []

    if lines > 1000:
        issues.append({
            "type": "buyuk_dosya",
            "severity": "kritik" if lines > 1500 else "orta",
            "kritik": lines > 1500,
            "detail": "%d satir - tek dosyada cok fazla sorumluluk (SRP ihlali)" % lines,
            "cozum": "Dosyayi birden fazla module bolun.",
            "file": rel,
        })

    if len(imports) > 20:
        issues.append({
            "type": "fazla_bagimlilik",
            "severity": "dusuk",
            "kritik": False,
            "detail": "%d import - fazla dis bagimlilik" % len(imports),
            "cozum": "Gereksiz importlari temizleyin, ortak bagimliliklari toplayin.",
            "file": rel,
        })

    if not classes and len(functions) > 5:
        issues.append({
            "type": "sinif_eksik",
            "severity": "dusuk",
            "kritik": False,
            "detail": "Sadece %d fonksiyon, 0 sinif - OOP icin sinif dusunulebilir" % len(functions),
            "cozum": "Ilgili fonksiyonlari bir sinif altinda toplamayi degerlendirin.",
            "file": rel,
        })

    total_methods = sum(len(c.get("methods", [])) for c in classes)
    total_decorators = sum(len(m.get("decorators", [])) for c in classes for m in c.get("methods", []))
    if total_methods > 5 and total_decorators == 0:
        issues.append({
            "type": "decorator_eksik",
            "severity": "dusuk",
            "kritik": False,
            "detail": "%d metod var ama 0 decorator" % total_methods,
            "cozum": "@staticmethod/@classmethod/@property ve ozel decoratorler dusunun.",
            "file": rel,
        })

    # Extra: parse error is also an issue (already in scan, but surface here too)
    if fdata.get("parse_error"):
        issues.append({
            "type": "parse_hatasi",
            "severity": "kritik",
            "kritik": True,
            "detail": "Dosya AST ile parse edilemiyor (SyntaxError)",
            "cozum": "Syntax hatasini duzeltin.",
            "file": rel,
        })

    # Source code needed for AST-based analyses
    source_code = fdata.get("source_code", "")
    if not source_code:
        return issues

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return issues  # parse error already reported

    # NEW: Unreachable code
    try:
        tree = ast.parse(source_code)
        issues.extend(detect_unreachable_code(ast.parse(fdata.get("source_code", ""))))
    except Exception:
        pass

    # NEW: Unused variables
    try:
        issues.extend(detect_unused_variables(ast.parse(fdata.get("source_code", ""))))
    except Exception:
        pass

    # NEW: Security patterns
    try:
        issues.extend(detect_security_patterns(ast.parse(fdata.get("source_code", ""))))
    except Exception:
        pass

    # NEW: Cyclomatic complexity
    try:
        tree = ast.parse(fdata.get("source_code", ""))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = cyclomatic_complexity(node)
                if cc > 20:
                    issues.append({
                        "type": "yuksek_ciklik",
                        "severity": "orta" if cc < 30 else "yuksek",
                        "kritik": cc > 30,
                        "detail": f"Fonksiyon '{node.name}' cok karmaşık (CC={cc})",
                        "cozum": "Fonksiyonu daha küçük parçalara bölün.",
                        "line": node.lineno,
                    })
    except Exception:
        pass

    # NEW: Type hint coverage
    try:
        tree = ast.parse(fdata.get("source_code", ""))
        coverage, missing_hints = type_hint_coverage(tree)
        if coverage < 50 and missing_hints:
            for mh in missing_hints[:10]:  # limit to 10
                issues.append(mh)
            if len(missing_hints) > 10:
                issues.append({
                    "type": "missing_type_hint",
                    "severity": "dusuk",
                    "kritik": False,
                    "detail": f"... ve {len(missing_hints) - 10} fonksiyon daha tür ipucu eksik",
                    "cozum": "Fonksiyon imzalarına tip ipuçları ekleyin.",
                })
    except Exception:
        pass

    return issues


def run_quality(scan: dict) -> dict:
    files = scan.get("files", {})
    by_file = {}
    by_subsystem = {}
    all_scores = []

    for rel, fdata in files.items():
        scores = score_file(fdata)
        issues = _collect_issues_for_file(rel, fdata, fdata.get("source_code", ""))
        by_file[rel] = {"scores": scores, "issues": issues}
        all_scores.append(scores["Toplam"])

        sub = rel.split("/")[0] if "/" in rel else "_root"
        entry = by_subsystem.setdefault(sub, {"files": 0, "total": 0, "issues": 0, "kritik": 0})
        entry["files"] += 1
        entry["total"] += scores["Toplam"]
        entry["issues"] += len(issues)
        entry["kritik"] += sum(1 for i in issues if i.get("kritik"))

    # averages
    for sub, entry in by_subsystem.items():
        entry["avg_toplam"] = round(entry["total"] / entry["files"], 1) if entry["files"] else 0

    cat_names = ["Aktiflik", "Gereklilik", "Kod Kalitesi", "Butunluk"]
    score_breakdown = {
        c: round(sum(v["scores"][c] for v in by_file.values()) / len(by_file), 1)
        if by_file else 0
        for c in cat_names
    }

    issue_type_counts = {}
    all_issues = []
    for rel, v in by_file.items():
        for i in v["issues"]:
            t = i.get("type", "bilinmeyen")
            issue_type_counts[t] = issue_type_counts.get(t, 0) + 1
            i = dict(i)
            i.setdefault("file", rel)
            all_issues.append(i)

    top_actions = _prioritize_actions(all_issues)

    summary = {
        "total_files": len(files),
        "total_issues": sum(len(v["issues"]) for v in by_file.values()),
        "kritik_issues": sum(1 for v in by_file.values() for i in v["issues"] if i.get("kritik")),
        "avg_toplam": round(sum(all_scores) / len(all_scores), 1) if all_scores else 0,
        "score_breakdown": score_breakdown,
        "issue_type_counts": dict(sorted(issue_type_counts.items(), key=lambda kv: -kv[1])),
        "top_actions": top_actions,
    }

    return {"by_file": by_file, "by_subsystem": by_subsystem, "summary": summary}


# issue tipi -> iyilesen skor boyutu + onarim oncelik agirligi
_AFFECTS = {
    "buyuk_dosya": ("Gereklilik/Butunluk", 7),
    "fazla_bagimlilik": ("Aktiflik", 3),
    "sinif_eksik": ("Butunluk", 5),
    "decorator_eksik": ("Kod Kalitesi", 2),
    "parse_hatasi": ("Butunluk (tum skorlar)", 10),
    "yuksek_ciklik": ("Kod Kalitesi", 8),
    "missing_type_hint": ("Kod Kalitesi", 3),
    "unreachable_code": ("Kod Kalitesi", 4),
    "unused_variable": ("Kod Kalitesi", 2),
}
_SEV_RANK = {"dusuk": 1, "orta": 2, "yuksek": 3, "kritik": 4}


def _prioritize_actions(issues: list) -> list:
    def key(i):
        kritik = 1000 if i.get("kritik") else 0
        sev = _SEV_RANK.get(str(i.get("severity", "")), 0) * 20
        imp = _AFFECTS.get(i.get("type"), ("Kod Kalitesi", 1))[1]
        return kritik + sev + imp

    srt = sorted(issues, key=key, reverse=True)
    actions = []
    for i in srt[:20]:
        affects = _AFFECTS.get(i.get("type"), ("Kod Kalitesi", 1))[0]
        actions.append({
            "file": i.get("file", ""),
            "line": i.get("line"),
            "type": i.get("type", "?"),
            "severity": i.get("severity", "dusuk"),
            "kritik": bool(i.get("kritik")),
            "detail": i.get("detail", ""),
            "cozum": i.get("cozum", ""),
            "iyilestirilen_skor": affects,
        })
    return actions


# ============================================================
# MODEL-FREE ANALYSES (AST-based, no LLM required)
# ============================================================

# Not (P1, 2026-09-16): eval_exec buradan ÇIKARILDI — regex `\b(eval|exec)\s*\(`
# niteliksizdi: Qt'nin dialog.exec()/menu.exec() ve PyTorch model.eval() çağrılarını
# da "kritik güvenlik riski" diye işaretliyordu (EvaGUI'de 51 false-positive; projede
# gerçek eval/exec çağrısı sıfırdı). Kural artık AST tabanlı: detect_security_patterns()
# içinde yalnız gerçek builtin Name-call'ları (eval(...)/exec(...)) yakalar.
SECURITY_PATTERNS = {
    "shell_injection": r"subprocess\.(run|Popen|call).*shell\s*=\s*True",
    "pickle_load": r"pickle\.(load|loads)\(",
    "yaml_unsafe_load": r"yaml\.load\((?!.*Loader=)",
    "sql_injection": r"execute\s*\(\s*[\"'].*%.*\)",
    "path_traversal": r"\.\./",
    "hardcoded_secret": r"(password|secret|token|key)\s*=\s*[\"']",
}


def detect_unreachable_code(tree: ast.AST) -> List[Dict[str, Any]]:
    """Detect code after return/raise/return in functions."""
    issues = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Find statements after return/raise in the same block
            for i, stmt in enumerate(node.body):
                if isinstance(stmt, (ast.Return, ast.Raise)):
                    # Check if there are statements after this return/raise in the same block
                    if i + 1 < len(node.body):
                        for j in range(i + 1, len(node.body)):
                            stmt_after = node.body[j]
                            if not isinstance(stmt_after, (ast.Pass, ast.Expr)) or \
                               (isinstance(stmt_after, ast.Expr) and not isinstance(stmt_after.value, ast.Constant)):
                                issues.append({
                                    "type": "unreachable_code",
                                    "severity": "orta",
                                    "kritik": False,
                                    "detail": f"'{ast.unparse(stmt).strip()}' sonrası erişilemez kod var",
                                    "cozum": "Erişilemez kodu silin veya kontrol akışını düzeltin.",
                                    "line": stmt_after.lineno if hasattr(stmt_after, 'lineno') else 0,
                                })
    return issues


def detect_unused_variables(tree: ast.AST) -> List[Dict[str, Any]]:
    """Detect unused variables (assigned but never read)."""
    issues = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Track assigned vs used variables in this function scope
            assigned: Dict[str, int] = {}  # name -> line
            used: Set[str] = set()
            
            for node_in_func in ast.walk(node):
                if isinstance(node_in_func, ast.Name):
                    if isinstance(node_in_func.ctx, ast.Store):
                        assigned[node_in_func.id] = node_in_func.lineno
                    elif isinstance(node_in_func.ctx, ast.Load):
                        used.add(node_in_func.id)
            
            for var_name, line_no in assigned.items():
                if var_name not in used and not var_name.startswith("_"):
                    issues.append({
                        "type": "unused_variable",
                        "severity": "dusuk",
                        "kritik": False,
                        "detail": f"Atanan ama kullanılmayan değişken: '{var_name}' (satır {line_no})",
                        "cozum": "Kullanılmayan değişkeni silin veya kullanın.",
                        "line": line_no,
                    })
    return issues


def type_hint_coverage(tree: ast.AST) -> Tuple[float, List[Dict[str, Any]]]:
    """Calculate type hint coverage percentage."""
    missing_hints = []
    total_funcs = 0
    hinted_funcs = 0
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total_funcs += 1
            has_return = node.returns is not None
            has_args_hints = any(arg.annotation for arg in node.args.args)
            has_kwonly_hints = any(arg.annotation for arg in node.args.kwonlyargs)
            if node.args.vararg and node.args.vararg.annotation:
                pass  # counts as hinted
            if node.args.kwarg and node.args.kwarg.annotation:
                pass
            
            if has_return or has_args_hints or has_kwonly_hints:
                hinted_funcs += 1
            else:
                missing_hints.append({
                    "type": "missing_type_hint",
                    "severity": "dusuk",
                    "kritik": False,
                    "detail": f"Fonksiyon '{node.name}' tür ipucu eksik",
                    "cozum": "Fonksiyon imzasına tip ipuçları ekleyin.",
                })
    
    coverage = (hinted_funcs / total_funcs * 100) if total_funcs > 0 else 100.0
    return coverage, missing_hints


def detect_security_patterns(tree: ast.AST) -> List[Dict[str, Any]]:
    """Detect security anti-patterns in code."""
    issues = []
    source_code = ast.unparse(tree) if hasattr(ast, 'unparse') else ""
    
    for pattern_name, pattern in SECURITY_PATTERNS.items():
        matches = list(re.finditer(pattern, source_code))
        for match in matches:
            line_no = source_code[:match.start()].count('\n') + 1
            issues.append({
                "type": f"security_{pattern_name}",
                "severity": "yuksek" if pattern_name in ("eval_exec", "shell_injection", "pickle_load", "sql_injection") else "orta",
                "kritik": pattern_name in ("eval_exec", "shell_injection", "pickle_load", "sql_injection"),
                "detail": f"Güvenlik riski: {pattern_name} tespit edildi",
                "cozum": f"{pattern_name} kullanımını gözden geçirin, güvenli alternatif kullanın.",
            })

    # eval_exec — AST tabanlı tarama (P1 REV, 2026-09-16; kullanıcı onaylı).
    # Yalnız gerçek eval(...)/exec(...) Name-call'ları; nitelikli çağrılar
    # (dialog.exec(), model.eval()) ve docstring/string içi metinler kapsam dışı.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            issues.append({
                "type": "security_eval_exec",
                "severity": "yuksek",
                "kritik": True,
                "detail": f"Güvenlik riski: eval_exec tespit edildi ('{node.func.id}()' çağrısı)",
                "cozum": f"eval/exec yerine güvenli alternatif kullanın (örn. ast.literal_eval, açık dağıtım). Satır {node.lineno}.",
                "line": node.lineno,
            })
    return issues


def cyclomatic_complexity(node: ast.AST) -> int:
    """Calculate McCabe cyclomatic complexity for a function."""
    complexity = 1  # Base complexity
    for node in ast.walk(node):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler, ast.Try,
                             ast.With, ast.Assert, ast.BoolOp, ast.IfExp)):
            if isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            else:
                complexity += 1
    return complexity
