# DEVKIT - Global Working Rules (applies to all projects)
# ========================================================
# The AI working on a project MUST follow these rules. Project-specific rules
# live in <project>/.devkit/PROJECT_RULES.md and override these when they
# conflict.

## WORKING PRINCIPLES (internalize FIRST - non-negotiable)

1. Production-ready only. No band-aids, no temporary/idareten fixes, no
   skeleton/demo/placeholder/pass/TODO code. Fix the ROOT CAUSE, never the
   symptom. Every button, every path, every feature must actually work.

2. Big picture before single file. NEVER change a script in isolation.
   Before touching anything, think about the domino effect: who imports it,
   who depends on it, which flows pass through it. Read the whole file and
   the affected components, not just the one line you are changing. In a
   large codebase, one wrong assumption made in isolation can waste weeks
   of work.

3. No script clutter. Do NOT create many small scripts. First add to the
   existing script that already owns that responsibility. New areas open as
   their own folders/subfolders by domain (e.g. persona/, memory/,
   model_system/). Every file must have a clear owner domain - a stranger
   must be able to tell what each file does from its location.

4. Preserve the architecture. Match existing patterns and conventions. No
   unnecessary refactor, no simplification, no feature reduction. A new
   feature plugs into the existing architecture.

5. Plan approval. No code change without user approval.

6. No emoji or decorative characters in code (comments included).

## PRE-CHANGE CHECKLIST (before EVERY code change)
1. python devkit.py find <symbol>   -> already exists? extend/move, never duplicate
2. python devkit.py outline <file>  -> read the file map (line ranges) first
3. python devkit.py impact <file>   -> who depends on this file? (domino effect)
4. read the dependents and the full relevant code, not just one line
5. only then change, and only with user approval

## 0. Onboarding (first contact with a project) — 14-step reading order
When the user says "run the devkit and prepare for architecture development"
(or on first contact with a project), perform this onboarding flow.
Inspired by old system MIMARI TANIMA SIRALAMASI (11 files) — each step
answers one question; do them in order, no skipping.

Preparation:
1. python devkit.py rescan         -> generate the knowledge base (KB) + data/*.json
2. Learn the rules: rules.md + <project>/.devkit/PROJECT_RULES.md

Quick picture (2 min each):
3. Read KB/QUICKREF.md             -> what does the project do? how big? which subsystems?
4. Read KB/ARCHITECTURE.md         -> 4-layer architecture, dependency chain, design patterns
5. Read .devkit/meta.yaml          -> runtime truth: boot_chain, events (11+), flows (message/memory/session), startup/shutdown
   -> If missing or stale (flows changed but meta still old): CREATE/UPDATE it now.
      Template: devkit/templates/meta.example.yaml . Fill by reading src/core/event_bus.py, src/app.py, src/domain/* etc. (project-specific entry + core).

Flows (10 min):
6. Read KB/flows/boot.md            -> how does the system start? which create_instance() in which order?
7. Read KB/flows/message.md          -> user message path: Fast vs Slow, decision layer, cancel
8. Read KB/flows/memory.md           -> write path vs RAG query path
9. Read KB/DEPENDENCIES.md           -> subsystem matrix + circular imports; most critical modules

Deep dive:
10. Read KB/subsystems/<relevant>.md -> the subsystem you will touch: files, classes, methods, line ranges
11. Fill one-line summaries for every folder and file:
        python devkit.py desc <path> "<summary>"
    (list all with: python devkit.py desc list)
12. Write <project>/.devkit/meta.yaml (boot chain, events, design patterns,
    flows) if it is missing or stale. See templates/meta.example.yaml for schema.
13. python devkit.py report         -> regenerate KB with the new summaries
14. Report back to the user with a short summary:
   - what the project does and how it is structured
   - what the generated reports contain
   - the working principles you will follow (production-ready, no band-aids,
     full read + domino-effect analysis, etc.)

Meta-yonetimi (when to update meta.yaml):
- Only new class/function added -> NO update needed (scan.json is enough).
- Flow logic changed (new pipeline step, new event, new pattern, boot order) -> MUST update meta.yaml
- New design pattern introduced -> MUST update meta.yaml
- See templates/meta.schema.json for required keys.

## 1. Task start - mandatory read order (BLOCKING)
If any of 1-2 cannot be read -> STOP the task (old .clinerules rule).
1. <project>/.devkit/STATUS.yaml        -> active_task, metrics, health, cycles
2. <project>/.devkit/CONTEXT.md         -> last 3 tasks (what changed recently)
3. <project>/.devkit/PROJECT_RULES.md (if it exists) -> overrides rules.md
4. <project>/.devkit/KB/QUICKREF.md     -> 2-min picture (size, subsystems, entry points)
5. <project>/.devkit/KB/PROJECT_MAP.md (only the parts relevant to the task)
6. <project>/.devkit/KB/ARCHITECTURE.md and the relevant KB/flows/*.md
   when flow knowledge is needed (boot/message/memory/session)
7. <project>/.devkit/KB/subsystems/<name>.md before touching a subsystem
8. <project>/.devkit/meta.yaml          -> runtime flows/events/patterns (when relevant)
   -> If stale vs KB/DEPENDENCIES.md -> flag it, update after task

## 2. Map before reading (MANDATORY before adding or changing code)
- python devkit.py find <symbol>  -> check whether the symbol already exists.
- python devkit.py outline <file> -> read the file map (line ranges) first.
- Never blind-scan large files in 200-line chunks.
- If the symbol already exists: extend or move it. NEVER duplicate it.

## 3. Knowledge base policy
- KB/ files always hold the CURRENT final state. They are regenerated, not
  annotated. No change notes inside KB files.
- No development notes, FIX/TODO history comments inside KB files or code.
- All change/decision history goes ONLY to DEVELOPMENT_LOG.md (append-only).
  If you need to know what changed and why, read DEVELOPMENT_LOG.md.
- Output size guard: KB generation warns at 1MB, blocks at 5MB per file
  (old master_status.yaml yasak). Large reports are split by subsystem.
- JSON contracts: data/*.json must contain expected keys (stats/files for scan,
  graph/reverse/matrix/cycles for deps). Broken contracts are reported, not silently ignored.

## 4. Change safety
- python devkit.py impact <file>  before editing a file.
- python devkit.py check           after meaningful changes (runtime health).
- Respect ignore dirs in every scan. Never scan miniconda, java, node_modules,
  .git, site-packages or any user-defined ignore dir.

## 5. Sync discipline
- python devkit.py sync    -> incremental update (fingerprint diff).
- python devkit.py rescan  -> full fresh scan ("Taramayi Guncelle"). Use it
  after long work periods or whenever reports look stale. Always produces the
  final current reports; history goes only to DEVELOPMENT_LOG.md.

## 6. Task close - mandatory protocol
1. python devkit.py sync
2. python devkit.py check            -> update health before closing
3. python devkit.py close-task       -> state.json + CONTEXT.md + DEVELOPMENT_LOG.md
   -> If twin/quality warnings appeared in sync, include them in close-task summary

## 7. Meta-yonetimi (AI-authored runtime knowledge)
- meta.yaml is AI-authored, not scan-authored. Scan gives structure; AI gives meaning.
- Template: devkit/templates/meta.example.yaml ; Schema: devkit/templates/meta.schema.json
- Update triggers:
  - New class/function only -> NO update (scan.json enough)
  - Flow/event/pattern/boot order changed -> MUST update
  - See GELISTIRME_PLANI.md FAZ1 for the 70-line example.

## 8. AI Self-Bootstrap Protocol (MANDATORY on first contact)
When user says "run devkit and prepare for architecture development" (or on first
contact with a project), the AI MUST execute the Self-Bootstrap Protocol
defined in REHBER.md §10 — 7 stages, no skipping:

1. **Environment check** → `devkit list` / `devkit current` / `devkit select`
2. **KB generation** → `devkit rescan` (or `sync` for incremental)
3. **Numerical model** → `devkit scan --json`, `check --json`, `techdebt --json`
4. **Architecture internalization** → Read QUICKREF, PROJECT_MAP, ARCHITECTURE, DEPENDENCIES
5. **Runtime flows** → Read meta.yaml + KB/flows/*.md (CREATE meta.yaml if missing/stale)
6. **Deep dive (on demand)** → subsystems/*.md, find/outline/impact --json
7. **Rules & context load** → PROJECT_RULES.md, STATUS.yaml, CONTEXT.md, ISSUES.md
8. **Ready report** → Summarize to user (what, structure, runtime, quality, risks)

**Core rules during bootstrap:**
- JSON first: consume `--json` outputs, don't parse markdown.
- Map before reading: find → outline → impact → then read file.
- meta.yaml ownership: if missing/stale, YOU fill it now (template: templates/meta.example.yaml).
- Desc everything: `devkit desc <path> "<summary>"` for every understood folder/file.
- Sync discipline: after every meaningful change → sync → check → close-task.
- Conscious risk: impact shows many dependents → report risk, get approval.

See REHBER.md §10 for full protocol, anti-patterns, and automation snippet.
