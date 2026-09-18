#!/usr/bin/env python3
"""
hybrid_analyzer.py - Hibrit Analiz Motoru (BAGIMSIZ / dependency-free)
=======================================================================
AST (hizli, deterministik) + istege bagli LLM (anlamsal, baglamsal).

Mimari:
1. AST/Static Analiz Once  -> engine.scan (DEVKIT core, saf AST)
2. (istege bagli) LLM Derin Analiz -> disaridan verilen duck-typed
   `llm_client` kullanilir. DEVKIT icinde LLM YOKTUR; ust katman (AI agent)
   kendi clientini verir. Client yoksa LLM adimi atlanir ve ISLETIM
   ImportError/AttributeError firlatmaz.
3. Sonuc Birles tirme -> sure, dosya sayisi, hatalar.

Not (fix): `core.*` ve `config.settings` bagimliliklari KALDIRILDI - o
moduller bu repoda yoktu ve modul import edilir edilmez cigar ediyordu
(bkz. REHBER.md). Bu surum yalnizca stdlib + engine.scan kullandigi icin
`import engine.hybrid_analyzer` her zaman guvenlidir.

Ornek (AI agent kullanimi):
    from engine.hybrid_analyzer import HybridAnalysisEngine, AnalysisMode
    eng = HybridAnalysisEngine(mode=AnalysisMode.AST_ONLY)
    sonuc = eng.analyze_project("H:/proje", ignore_list=[".git", "__pycache__"])

LLM client arayuzu (istege bagli):
    client.analyze_files(files: List[dict], types: List[str]) -> dict
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class AnalysisMode(Enum):
    AST_ONLY = "ast_only"
    LLM_ONLY = "llm_only"
    HYBRID = "hybrid"  # AST once, sonra LLM (client verilirse)


@dataclass
class AnalysisContext:
    """Analiz baglami - dosya, proje, amac bilgileri."""
    file_path: str
    rel_path: str
    source_code: str
    arch_map: Dict[str, Any] = field(default_factory=dict)
    project_context: Dict[str, Any] = field(default_factory=dict)
    focus_areas: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Birlesik analiz sonucu."""
    ast_results: Dict[str, Any] = field(default_factory=dict)
    llm_results: Dict[str, Any] = field(default_factory=dict)
    combined: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    mode: AnalysisMode = AnalysisMode.HYBRID
    processing_time: float = 0.0
    files_analyzed: int = 0
    errors: List[str] = field(default_factory=list)


class HybridAnalysisEngine:
    """Hibrit analiz orkestratoru. Varsayilan mod AST_ONLY'dir."""

    def __init__(self, llm_client=None, mode: AnalysisMode = AnalysisMode.HYBRID):
        self.llm_client = llm_client
        self.mode = mode
        self.max_llm_files = 40
        self.cancelled = False
        self._progress_callback: Optional[Callable] = None

    # ---- cagriyi esnek tutan yardimcilari ----

    def set_llm_client(self, client) -> None:
        self.llm_client = client

    def set_progress_callback(self, callback) -> None:
        self._progress_callback = callback

    def cancel(self) -> None:
        self.cancelled = True

    def _report_progress(self, current, total, message) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(current, total, message)
            except Exception:
                pass

    @staticmethod
    def _default_ignore() -> List[str]:
        return [
            "Python_Ortami", "__pycache__", "models", "libs", ".git", ".venv",
            "venv", "env", "node_modules", "dist", "build",
        ]

    # ---- istege bagli LLM arayuz kontrolu ----

    def _run_llm(self, selected: List[dict], analysis_types: List[str]) -> dict:
        client = self.llm_client
        if client is None:
            raise RuntimeError("llm_client yok.")
        if not hasattr(client, "analyze_files"):
            raise NotImplementedError(
                "llm_client 'analyze_files(files, types)' arayuzune sahip olmali. "
                "DEVKIT core icinde LLM yoktur.")
        return client.analyze_files(selected, list(analysis_types))

    # ---- ana pipeline ----

    def analyze_project(self,
                        scan_root: str,
                        ignore_list: Optional[List[str]] = None,
                        analysis_types: Optional[List[str]] = None,
                        progress_callback: Callable = None) -> Dict[str, Any]:
        """Tam analiz pipeline'i.

        Args:
            scan_root: Taranacak kok dizin.
            ignore_list: Yoksayilacak klasorler (engine.scan'in ignore_dirs'i).
            analysis_types: Ilgili analiz turleri (None = hepsi-ister).
        """
        from engine.scan import run_scan  # DEVKIT core (AST/static) - cached isleri dokunmaz

        t0 = time.time()
        self.cancelled = False
        if progress_callback is not None:
            self._progress_callback = progress_callback

        if analysis_types is None:
            analysis_types = [
                "architecture_map", "project_purpose", "tech_infrastructure",
                "dev_status", "errors_missing", "dead_code",
            ]

        self._report_progress(1, 4, "Faz 1: AST/Static tarama (engine.scan)...")
        ignore = sorted(set(self._default_ignore() + list(ignore_list or [])))
        scan = run_scan(Path(scan_root), ignore)  # data_dir=None -> disk cache kapali
        ast_map = self._build_ast_map(scan)

        if self.cancelled:
            return {"error": "Iptal edildi", "ast_results": ast_map}

        self._report_progress(2, 4, "Faz 2: AST haritasi tamam (%d dosya)" % ast_map["file_count"])

        llm_results: Dict[str, Any] = {}
        if self.mode in (AnalysisMode.LLM_ONLY, AnalysisMode.HYBRID):
            if self.llm_client is None:
                self._report_progress(3, 4, "LLM clienti yok - LLM adimi atlaniyor (AST_ONLY).")
            else:
                self._report_progress(3, 4, "Faz 3: LLM derin analiz...")
                try:
                    selected = self._select_files(ast_map)
                    llm_results = self._run_llm(selected, analysis_types)
                except NotImplementedError as e:
                    llm_results = {"warning": str(e)}
                except Exception as e:
                    llm_results = {"error": "%s: %s" % (type(e).__name__, e)}
        else:
            self._report_progress(3, 4, "Faz 3: atlandi (AST_ONLY).")

        self._report_progress(4, 4, "Faz 4: Sonuclar birles tiriliyor...")
        combined = self._combine(ast_map, llm_results)

        return {
            "ast_results": ast_map,
            "llm_results": llm_results,
            "combined": combined,
            "mode": self.mode.value,
            "processing_time": round(time.time() - t0, 3),
            "files_analyzed": ast_map["file_count"],
        }

    # ---- yapay, ucretsiz AST katmani ----

    @staticmethod
    def _build_ast_map(scan: dict) -> Dict[str, Any]:
        rows = []
        for rel, fd in (scan.get("files", {}) or {}).items():
            rows.append({
                "rel_path": rel,
                "lines": fd.get("lines", 0),
                "doc": fd.get("doc", ""),
                "classes": [c.get("name") for c in fd.get("classes", [])],
                "functions": [fn.get("name") for fn in fd.get("functions", [])],
                "imports": fd.get("imports", []),
                "parse_error": fd.get("parse_error", False),
            })
        return {
            "stats": scan.get("stats", {}),
            "file_count": len(rows),
            "rows": rows,
        }

    def _select_files(self, ast_map: dict, min_lines: int = 30, max_lines: int = 5000) -> List[dict]:
        """LLM'e gonderilecek dosyalari sec: parse edilir, makul boyut, test degil."""
        out = []
        for r in ast_map["rows"]:
            if r["parse_error"]:
                continue
            if not (min_lines <= r["lines"] <= max_lines):
                continue
            base = Path(r["rel_path"]).name.lower()
            if "test" in base or "spec" in base:
                continue
            out.append(r)
        return out[: self.max_llm_files]

    # ---- birles tirme ----

    @staticmethod
    def _get(llm_results: dict, key: str):
        return llm_results.get(key) if isinstance(llm_results, dict) else None

    def _combine(self, ast_map: dict, llm_results: dict) -> Dict[str, Any]:
        stats = ast_map.get("stats", {})
        return {
            "architecture": {
                "subsystems": stats.get("subsystems", []),
                "python_files": stats.get("total_py", 0),
                "total_lines": stats.get("total_lines", 0),
                "classes": stats.get("total_classes", 0),
                "functions": stats.get("total_functions", 0),
            },
            "files_analyzed": ast_map.get("file_count", 0),
            "purpose": self._get(llm_results, "project_purpose"),
            "tech_infrastructure": self._get(llm_results, "tech_infrastructure"),
            "dev_status": self._get(llm_results, "dev_status"),
            "errors": self._get(llm_results, "errors_missing"),
            "dead_code": self._get(llm_results, "dead_code"),
        }


class AnalysisEngine:
    """Eski API uyumluluk sarmalayicisi.

    Devkit core icinde LLM yoktur; client verilmezse AST_ONLY calisir,
    import hatasi vermez. LLM clienti verilirse HybridAnalysisEngine
    uzerinden HYBRID moda gecer.
    """

    def __init__(self, llm_client=None, model_id: str = "hybrid", max_tokens: int = 800,
                 max_preview_chars: int = 3000, max_files_per_call: int = 4):
        self.llm_client = llm_client
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.max_preview_chars = max_preview_chars
        self.max_files_per_call = max_files_per_call
        self.cancelled = False

    def analyze(self, arch_map=None, analysis_types=None, scanner=None,
                progress_callback=None) -> Dict[str, Any]:
        mode = AnalysisMode.HYBRID if self.llm_client else AnalysisMode.AST_ONLY
        eng = HybridAnalysisEngine(self.llm_client, mode=mode)
        eng.max_llm_files = self.max_files_per_call
        types = []
        for t in (analysis_types or []):
            types.append(t.value if isinstance(t, AnalysisMode) else str(t))
        result = eng.analyze_project(
            scan_root=str(getattr(arch_map, "root", None) or arch_map or "."),
            ignore_list=[],
            analysis_types=types or None,
            progress_callback=progress_callback,
        )
        return result

    def cancel(self) -> None:
        self.cancelled = True