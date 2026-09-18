# DEVKIT — AI Kod Geliştirme Yardımcı Asistan Sistemi

## Rehber Dokümanı (Kullanıcı + AI için) — v2.2 (Güncel)

> **Sürüm:** H:\devkit 2026-09-15 v2.2 | **Dil:** Python 3.8+ | **Bağımlılık:** Sadece stdlib + Tkinter | **Tip:** Proje-bağımsız, production-ready

---

## 1. Özet — DEVKIT Nedir?

DEVKIT, **projeden bağımsız (project-agnostic)** bir araçtır. Sıfırdan bir proje veya ortasındaki bir projede bir AI'ın (veya geliştiricinin) **büyük dosyaları tekrar okumadan mimariyi tanıması** ve geliştirme boyunca bu bilgiyi güncel tutması için tasarlandı.

**Felsefe:** *Haritayı önce çıkar, sonra oku; bilgiyi tek yerde tut; geçmişi sadece log'da sakla.*

### Ne Yapar? (Güncel Yetenek Matrisi)

| Yetenek | Ne Üretir | Nasıl |
|---------|-----------|-------|
| **Yapısal Tarama (scan)** | `scan.json` | `engine/scan.py:220` tek AST geçişi: sınıf/fonksiyon/metod/imza/docstring + `module_imports` + `relative_imports` (level>0) |
| **Bağımlılık (deps)** | `deps.json` | `engine/deps.py:62` graph/reverse/matrix + Tarjan SCC ( `__init__.py` hariç) + **relative import çözümü** |
| **API Yüzeyi** | `api.json` | `engine/api_surface.py:10` alt-sistem bazlı sınıflar/fonksiyonlar |
| **Kullanım Doğrulama** | `usage.json` | `engine/usage.py:68` `pyproject.toml` vs import |
| **Kalite Karnesi (yeni)** | `quality.json` | `engine/quality.py:1` 4 kriter (Aktiflik/Gereklilik/Kod Kalitesi/Bütünlük 0-10, Toplam 0-40) + 4 sorun tipi |
| **Teknik Borç (güçlendi)** | `techdebt.json` | `engine/techdebt.py:64` twin (kinds **+ normalize MD5 hash** + fuzzy `_v1/_new`), `fix_tags`, `callgraph {callees, callers}` |
| **Sağlık (health)** | `health.json` | `engine/health.py:16` proje interpreter'ında subprocess import testi |
| **Etki (impact)** | — | `engine/impact.py:38` `deps.json` üzerinden dependents/dependencies |
| **Sembol/Anahat** | — | `scan.json` üzerinden `find`/`outline` (`--json` ile) |
| **KB Raporları** | `KB/*.md` | `reports/generate.py:278` + `quality` + `meta.yaml` → QUICKREF/PROJECT_MAP/DEPENDENCIES/SYMBOL_INDEX/ARCHITECTURE/subsystems/flows |
| **State** | `STATUS.yaml` etc. | `reports/state.py:53` scan+health+deps+quality+techdebt → STATUS/CONTEXT/ENVIRONMENT/ISSUES |
| **Diff+Sync** | `fingerprint.json` | `engine/diff.py:26` sha256 ile added/deleted/modified/moved + `DEVELOPMENT_LOG.md` |

**Ek Altyapı (v2 yeni):**
- **AST Cache** (`engine/scan.py:_cached_extract`) — `data/.ast_cache/_index.json` sha256 bazlı, `scan`/`sync` `--no-cache` ile kapatılabilir.
- **Glob Ignore** (`engine/scan.py:120` `fnmatch`) — `*.pyc`, `tests/*` gibi patternler per-proje `config.json`'da saklanır (`common.py:CONFIG_VERSION=2`).
- **JSON Çıktı** (`devkit.py:546` `--json`) — `find/outline/impact/check/techdebt/scan` için AI doğrudan JSON tüketir.
- **Output Guard** (`reports/generate.py:_check_output_size`) — 1MB warn / 5MB block, eski `master_status.yaml:202` yasağı.

### Ne Değildir?
- Build sistemi değil; kodu değiştirmez, sadece analiz eder.
- Çıktıyı asla `H:\devkit` altına yazmaz; hep `<proje>/.devkit/` (`common.py:95`).

### Sabit İlkeler (`rules.md:7` — her proje için non-negotiable)
1. Production-ready only — demo/mock/skeleton/placeholder/`pass`/`TODO`/`yara bandı`/`şimdilik` yasak.
2. Big picture — domino etkisi düşünülmeden izole değişiklik yok.
3. No clutter — var olan scripte ekle, yeni alan = domain klasörü.
4. Mimariyi koru — pattern'e uy.
5. Plan onayı olmadan kod yok.
6. Kodda emoji/süs yok.
*Per-proje `PROJECT_RULES.md` sadece ek kural ekler, bu 6'yı gevşetemez.*

---

## 2. Mimari — Dosya Yapısı (v2)

```
H:\devkit\
├── devkit.py              # CLI (argparse, --json/--no-cache)
├── common.py              # registry, config_version=2, glob normalize
├── gui.py                 # Tkinter, threaded
├── DEVKIT.bat
├── registry.json          # {active_project, projects} — per-machine, boş dağıtılır (bak: registry.json.bak)
├── rules.md               # Global kurallar (14 adım onboarding)
├── engine/
│   ├── context.py         # require_project()
│   ├── scan.py            # walk_project (glob) + extract + cache
│   ├── deps.py            # graph + relative resolve + SCC
│   ├── api_surface.py
│   ├── usage.py
│   ├── quality.py         # (yeni) kalite puanlama + sorun tespiti
│   ├── techdebt.py        # (güçlendi) hash+callers
│   ├── health.py
│   ├── impact.py
│   ├── diff.py
│   ├── descriptions.py    # migrate
│   └── scaffold.py
├── reports/
│   ├── generate.py        # KB + JSON kontrat + size guard + quality entegrasyonu
│   └── state.py           # STATUS/ISSUES artık quality+techdebt içerir
├── wizard/setup_wizard.py
├── manual/                # standalone, dosya yazmaz
├── templates/
│   ├── meta.example.yaml  # (yeni) generic şablon — hiçbir EVA ismi içermez
│   └── meta.schema.json   # (yeni) meta şeması
├── REHBER.md              # bu dosya
└── GELISTIRME_PLANI.md    # FAZ1-5 planı
```

### Proje Çıktısı (`<proje>/.devkit/`)

```
<proje>/.devkit/
├── config.json            # {project_name, root, env_path, ignore_dirs[], config_version:2}
├── PROJECT_INFO.txt
├── PROJECT_RULES.md       # (opsiyonel) per-proje ek kurallar
├── map_descriptions.json
├── meta.yaml              # AI-authored (templates/meta.example.yaml şablon)
├── state.json
├── fingerprint.json
├── DEVELOPMENT_LOG.md
├── STATUS.yaml            # + quality avg + techdebt sayıları + quality_by_subsystem
├── CONTEXT.md
├── ENVIRONMENT.md
├── ISSUES.md              # + Quality issues + Twin detailed + Fix tags
├── data/
│   ├── scan.json
│   ├── deps.json
│   ├── api.json
│   ├── usage.json
│   ├── quality.json       # (yeni) by_file/by_subsystem/summary
│   ├── health.json
│   ├── techdebt.json      # (yeni) twin_groups + twin_detailed + callgraph{callees,callers}
│   └── .ast_cache/_index.json  # (yeni) sha cache
└── KB/
    ├── QUICKREF.md
    ├── PROJECT_MAP.md
    ├── DEPENDENCIES.md
    ├── SYMBOL_INDEX.md
    ├── ARCHITECTURE.md
    ├── subsystems/<name>.md  # + Quality satırı + issue listesi
    └── flows/*.md
```

---

## 3. Nasıl Çalışır?

### 3.1 Kurulum (Bir Kez, Her Proje İçin Aynı)
```
DEVKIT.bat -> [1] Yeni Proje -> wizard/setup_wizard.py:43
  klasör seç (H:\MyProject — boş veya mevcut) -> ad (klasörden) -> bilgi
  -> ek kurallar (PROJECT_RULES.md) -> env (python.exe, opsiyonel) -> ignore (glob destekli)
  -> save_project_config() (config_version=2) -> registry.json
```
Scaffold boş projede `.gitignore/pyproject.toml/.git` oluşturur, mevcut projede dokunmaz.

### 3.2 Tarama (scan)
`run_scan(root, ignore, data_dir, use_cache)` (`engine/scan.py:220`):
- `walk_project` glob + hidden prune.
- Her `.py` için `extract_py_file` (sha256, lines, doc, classes, functions, imports, module_imports, relative_imports). Cache açıksa `sha16` hit → parse atlanır.
- Boş projede stats 0 ile döner, crash yok.

### 3.3 Bağımlılık (deps)
`run_deps(scan)` — absolute + **relative** (`from . import`) çözümü (`_resolve_relative`), matrix, SCC.

### 3.4 Kalite (quality)
`run_quality(scan)` (`engine/quality.py`): her dosya için skor + 4 sorun ( >1000 satır kritik, >20 import, sınıf yok, decorator yok) → `by_file` + `by_subsystem` avg.

### 3.5 Teknik Borç (techdebt)
`run_techdebt` — twin iki yöntem (kinds + **normalize MD5** `ast.unparse` fallback `ast.dump` için 3.8), `callgraph` now `{callees, callers}` (eski `cagri_grafigi_analizoru`).

### 3.6 Sync Pipeline
`devkit.py:272 _run_pipeline(label, record_diff, _args)`:
```
run_scan(use_cache) -> diff (hash-move) -> migrate_descriptions
-> run_deps/api/usage/quality -> _write_data -> save_fingerprint
-> generate_all (KB + size guard + kontrat) -> generate_state (STATUS/ISSUES)
-> log -> _report_new_code_checks (yeni klasör + twin uyarısı)
```

---

## 4. Komut Referansı (v2)

```bash
python devkit.py <komut> [--json] [--no-cache]
```

| Komut | Ek Flag | Çıktı |
|-------|---------|-------|
| `init` | `--ai-driven` `--project-root` `--project-name` `--env-path` `--project-info` `--project-rules` `--ignore-dirs` `--big-file-threshold` `--output-warn-mb` `--output-block-mb` `--auto-confirm` `--json` | `.devkit/config.json` (programatik kurulum) |
| `init` | (interactive) | `.devkit/config.json` (GUI/CLI sihirbaz) |
| `list` / `select` / `help` | `--json` | registry |
| `scan` | `--json` `--no-cache` | `data/*.json` (+ quality) |
| `report` | — | `KB/` |
| `sync` / `rescan` | `--no-cache` | data+KB+log |
| `find <sym>` | `--json` | `kind symbol file:line` |
| `outline <file>` | `--json` | outline + sig |
| `impact <file>` | `--json` | dependents/dependencies |
| `check` | `--json` | health (modül bazında ok/fail + gerçek hata mesajı) |
| `changed` | `--json` | git-diff + AST → değişen dosya/fonksiyon (git repo yoksa fingerprint fallback) |
| `techdebt` | `--json` | twin_detailed + callgraph + twin başına refactor önerisi (`remediation`) |
| `desc <path> <text>` | `--json` | map_descriptions.json |
| `close-task` | `--json` | state.json + log |

Tüm komutlar `--project "<ad>"` alır (registry'deki aktif projeden bağımsız, paralel AI kullanımı için).

GUI aynı butonlar, çıktı paneli.

### 4.1 Skor Saydamlığı ve Öncelikli Onarım

`scan`/`sync` her seferinde:
- `quality.json.summary.score_breakdown` — 4 boyut (Aktiflik/Gereklilik/Kod Kalitesi/Butunluk) ortalamaları.
- `quality.json.summary.top_actions` — kritik→düşük sıralı, `{file,line,type,detail,cozum,iyilestirilen_skor}` listesi. Konsolda ilk 5, `STATUS.yaml` `top_remediation` içinde ilk 8.
- `techdebt.json` twin gruplarında `remediation` — benzerlik yüzdesine göre somut refactor önerisi (kopyayı tek kaynak yap / mode parametresi / callgraph ile doğrula).

### 4.2 Kendi Kendine Keşif (INSIGHTS.md + meta.draft.yaml)

`sync`/`rescan` `KB/INSIGHTS.md` üretir (LLM'siz, statik):
- **Hub modüller** — en çok bağımlılık alan dosyalar (refactor önceliği).
- **Katman yapısı** — alt-sistemler arası bağımlılık yönünden otomatik seviye (0 = en çok kullanılan/kütüphane).
- **Base-class / polymorphic harita** — en az 2 alt sınıfı olan sınıflar (scan artık `bases` kaydeder).
- **Entry points** — `if __name__ == "__main__":` guard'ı tespiti (`stats.entry_files`).

`meta.yaml` yoksa `<proje>/.devkit/meta.draft.yaml` otomatik taslak oluşur (üzerine yazılmaz). AI onu `OBJECT` ile okur, düzeltip `meta.yaml` yapar — sıfırdan yazmaz.

### 4.3 Varsayılan İgnore Genişletildi

`common.py:DEFAULT_IGNORE_DIRS` artık `miniconda*`/`anaconda*`/`.conda`/`.tox`/`*_cache` vb. içerir. 3. parti env klasörleri (örn. miniconda3) tam taramaya girip skoru kirletmez.

---

## 5. Kullanıcı Rehberi

**Kurulum (Seçenek A - İnteraktif):** `DEVKIT.bat` -> Yeni Proje -> `H:\MyProject` seç -> kaydet -> `<proje>\.devkit\` oluşur.

**Kurulum (Seçenek B - AI-driven, programatik):**
```bash
# Tek komutla tam otomatik (AI kullanıcıdan onay almaz, direkt kurar)
python devkit.py init --ai-driven --project-root "H:\Proje" --project-name "ProjeAdi" --project-info "Açıklama" --auto-confirm --json

# AI gerekli bilgileri kullanıcıdan isteyip, onay alıp kurar (3 aşamalı)
python devkit.py init --ai-driven --project-root "H:\Proje" --json
# → {"status": "needs_input", "missing": ["project_name", "env_path"]}
# AI kullanıcıdan ister → tekrar çağırır
python devkit.py init --ai-driven --project-root "H:\Proje" --project-name "X" --env-path "..." --auto-confirm --json
```

DEVKIT hiçbir proje adını kodda sabit tutmaz (eski `REMEMBER_EVA_AI` temizlendi, `registry.json` boş dağıtılır).

**Günlük:** `sync` -> `check` -> `ISSUES.md/STATUS.yaml` oku. `sync --no-cache` cache bypass.

**İpucu:** `desc` ile yazdığın özetler move'da migrate olur; cache `data/.ast_cache` `.devkit` içinde (ignore).

---

## 6. AI Rehberi (rules.md özeti — harfiyen uy)

**14 Adım Onboarding (`rules.md:41`):**
1-2 Hazırlık: `rescan` + kuralları öğren
3-5 Hızlı resim: `QUICKREF` -> `ARCHITECTURE` -> `meta.yaml` (yoksa `templates/meta.example.yaml` şablonla YAZ, `src/core/*` oku)
6-9 Akışlar: `flows/boot.md`, `message.md`, `memory.md` + `DEPENDENCIES.md`
10-14 Derin: `subsystems/<name>.md` -> `desc` doldur -> `meta.yaml` güncelle (akış değiştiyse) -> `report` -> özet ver

**Task Başı Blokaj (`rules.md:84`):** `STATUS.yaml` okunamazsa DUR -> `CONTEXT.md` -> `PROJECT_RULES.md` -> `QUICKREF` -> `PROJECT_MAP` -> `ARCHITECTURE+flows` -> `subsystems` -> `meta.yaml`

**Map Before Reading:** `find` -> `outline --json` -> `impact --json` -> tam dosyayı oku -> onayla değiştir. Büyük dosyayı 200 satır kör tarama yasak.

**KB Politikası:** KB hep güncel, geçmiş sadece `DEVELOPMENT_LOG.md`; output 1MB warn/5MB block; JSON kontrat bozuksa rapor edilir.

**Meta Yönetimi:** Sadece sınıf/fonksiyon eklendi → güncelleme yok. Akış/event/desen/boot değişti → MUTLAKA `meta.yaml` güncelle.

---

## 7. Örnek Akış

```bash
python devkit.py init                # H:\MyApp
python devkit.py rescan              # data+KB
python devkit.py find UserService --json
python devkit.py outline src/service.py --json
python devkit.py impact src/service.py --json
python devkit.py desc src/service.py "User CRUD"
python devkit.py report
python devkit.py sync                # +2 -0 ~1, twin uyarısı?
python devkit.py check --json
python devkit.py close-task --name "feat" --summary "ok"
```

---

## 8. SSS

**H:\devkit silinirse?** Proje `.devkit/` durur, `registry.json` gider (yedeği `registry.json.bak`).

**scan vs sync?** `scan` sadece data, `sync/rescan` data+KB+log (aynı pipeline, etiket farklı).

**Cache?** `data/.ast_cache/_index.json` sha bazlı, `--no-cache` ile bypass.

---

## 9. Dosya→Satır

| Konu | Dosya:Satır |
|------|-------------|
| CLI | `devkit.py:36` / `devkit.py:546` |
| Sync | `devkit.py:272` |
| Registry | `common.py:17` |
| Scan+cache+glob | `engine/scan.py:120` / `engine/scan.py:220` |
| Deps+relative | `engine/deps.py:62` |
| Quality | `engine/quality.py:1` |
| Techdebt hash+callers | `engine/techdebt.py:64` / `engine/techdebt.py:85` |
| KB+guard | `reports/generate.py:278` |
| State+quality | `reports/state.py:53` |
| Template | `templates/meta.example.yaml` |

---

## 10. AI Kendi Kendini Hazırlama Protokolü (Self-Bootstrap)

> **Bu bölüm, DEVKIT'i çalıştıracak AI'nin (senin) kendi başına, kullanıcı müdahalesi olmadan projeyi anlayıp "hazır durum"a gelmesi için tasarlanmıştır.**
> Kullanıcı: *"DEVKIT'i çalıştır, mimariyi anla, benimle çalışmaya başla"* dediğinde bu protokolü **sırasıyla, atlamadan** uygula.

### 10.1 Neden Bu Protokol Gerekli?

- DEVKIT **sadece veri üretir** (scan, deps, quality, techdebt, health). Anlamı (meta.yaml, desc, rules) **AI yazar**.
- Kullanıcı her seferinde "şunu oku, bunu analiz et" demez; AI **otonom** KB'yi üretir, okur, içselleştirir, `meta.yaml` yazar.
- Bu protokol, AI'nın **context window'unu verimli doldurmasını**, **kör tarama yapmamasını**, **yanlış varsayımlar kurmamasını** garanti altına alır.

### 10.2 Protokol — 7 Aşama (Toplam ~5-10 dakika)

#### **AŞAMA 0 — Ortam Kontrolü (30 sn)**
```bash
python devkit.py list                    # Hangi projeler kayıtlı?
python devkit.py current                 # Aktif proje bu mu?
# Değilse: python devkit.py select <proje_adı>
```

#### **AŞAMA 1 — Bilgi Tabanını Üret / Güncelle (1-2 dk)**
```bash
python devkit.py rescan                  # Tam tarama + KB + log
# Veya incremental (daha hızlı):
python devkit.py sync                    # Diff + KB + log
```
> **Bekle:** Çıktı bitene kadar. `scan.json`, `deps.json`, `quality.json`, `techdebt.json`, `health.json`, `KB/*` hazır.

#### **AŞAMA 2 — Hızlı Genel Resim (30 sn) — JSON ile tüket, markdown parse ETME**
```bash
python devkit.py scan --json             # Stats: dosya/satır/sınıf/fonksiyon/subsistem sayısı
python devkit.py check --json            # Runtime health: import hataları var mı?
python devkit.py techdebt --json         # Twin gruplar, fix tags, callgraph özeti
```
> **Çıktıyı JSON olarak oku:** `stats`, `summary`, `twin_groups`, `fix_tags`, `callgraph` — bu senin **sayısal zihni modelin**.

#### **AŞAMA 3 — Mimari Haritasını İçselleştir (1-2 dk) — Markdown oku**
```bash
# Sırasıyla oku, atlama:
cat <proje>/.devkit/KB/QUICKREF.md       # Proje ne yapıyor? Boyut? Entry point'ler?
cat <proje>/.devkit/KB/PROJECT_MAP.md    # Klasör/dosya ağacı + özetler
cat <proje>/.devkit/KB/ARCHITECTURE.md   # Katmanlar, desenler, event'ler, yetenekler (meta.yaml'dan)
cat <proje>/.devkit/KB/DEPENDENCIES.md   # Subsistem matrisi + circular import'ler
```
> **Not al (içsel):** "Bu proje X katmanlı, Y subsistem, Z entry point, W circular import var."

#### **AŞAMA 4 — Runtime Akışlarını Anla (1 dk) — meta.yaml + flows**
```bash
cat <proje>/.devkit/meta.yaml            # Boot chain, events, patterns, message/memory/session flows
cat <proje>/.devkit/KB/flows/boot.md     # Sistem nasıl başlar?
cat <proje>/.devkit/KB/flows/message.md  # İstek/mesaj yolu (fast/slow path, cancel)
cat <proje>/.devkit/KB/flows/memory.md   # Veri yazma/okuma yolları
```
> **Eğer `meta.yaml` eksik/boş/placeholder ise:** **ŞİMDİ DOLDUR.** `templates/meta.example.yaml` şablonunu kopyala, `src/core/*`, `src/app.py`, `main.py` okuyarak gerçek değerlerle doldur. Sonra `python devkit.py report` ile KB'yi yenile.

#### **AŞAMA 5 — Çalışılacak Alanın Derinlemesine Analizi (gerektiğinde)**
```bash
# Hangi subsistem/değişiklik alanına odaklanacaksan:
cat <proje>/.devkit/KB/subsystems/<subsystem>.md   # Dosyalar, sınıflar, metotlar, quality skorları, issue'lar

# Sembol arama (Map Before Reading):
python devkit.py find <SymbolName> --json          # Nerede tanımlı? Hangi dosya:satır?

# Dosya anahatı (büyük dosyayı kör okuma):
python devkit.py outline <path/to/file.py> --json  # Sınıf/fonksiyon/metot + line range + signature

# Etki analizi (değişiklik öncesi şart):
python devkit.py impact <path/to/file.py> --json   # Kim bu dosyayı import ediyor? (dependents)
                                                   # Bu dosya kime bağımlı? (dependencies)
```

#### **AŞAMA 6 — Kural ve Bağlam Yükleme (30 sn)**
```bash
cat <proje>/.devkit/PROJECT_RULES.md       # Proje özel kuralları (varsa)
cat <proje>/.devkit/STATUS.yaml            # Mevcut metrikler, health, quality, techdebt, cycles
cat <proje>/.devkit/CONTEXT.md             # Son 3 görev neydi? Ne değişti?
cat <proje>/.devkit/ISSUES.md              # Açık sorunlar (import hataları, cycles, quality, twin, fix tags)
```

#### **AŞAMA 7 — Hazır Bildirimi Ver (Kullanıcıya)**
```text
"Hazırım. Proje: <adı> — <ne yapıyor 1 cümle>.
Mimari: <X katman, Y subsistem, Z entry point>.
Runtime: <boot chain özeti>, <event sayısı>, <message/memory flow özeti>.
Kalite: Avg <skor>/40, <kritik issue sayısı> kritik, <twin grup sayısı> potansiyel duplicate.
Açık riskler: <ISSUES.md'den kritik 3 madde>.
Hangi alanda çalışacağız?"
```

---

### 10.3 Protokol Kuralları (Kesin)

| Kural | Açıklama |
|-------|----------|
| **Atlama yok** | Aşama 1-4 **zorunlu**. Aşama 5-6 görev gerektirdiğinde. |
| **JSON first** | `scan/check/techdebt/find/outline/impact --json` ile veri al, markdown parse etme. |
| **Map Before Reading** | Hiçbir dosyayı `cat`/`read` etmeden önce `find` + `outline` + `impact` yap. |
| **meta.yaml sorumluluğu** | Eksikse/eskise **sen doldurursun/güncellersin**. Kullanıcı yapmaz. |
| **Desc yaz** | Her anladığın klasör/dosya için `python devkit.py desc <path> "<özet>"` yaz. Move edilirse migrate olur. |
| **Sync disiplini** | Her anlamlı değişiklikten sonra `sync` → `check` → `close-task`. |
| **Bilinçli risk alma** | `impact` çıktısı riskliyse (çok dependent), kullanıcıya **risk raporu** ver, onay al. |

---

### 10.4 Sık Yapılan Hatalar (Yapma)

| Hatalı Davranış | Doğrusu |
|-----------------|---------|
| `rescan` yapmadan dosya okumaya başlama | Önce KB üret, sonra oku |
| `meta.yaml` placeholder kalmasına izin verme | Eksikse **şimdi** doldur (boot chain, events, patterns) |
| `impact` bakmadan değiştirme | Domino etkisini gör, dependents'ı oku, onay al |
| `desc` yazmamak | Her anladığın yer için 1 satır özet yaz — gelecekte (ve senin gelecekteki oturumlarında) kurtarıcı olur |
| `health.json`/`check` atlama | Static analysis göremez: circular import runtime, missing dep, version conflict |
| `techdebt` uyarılarını görmezden gelme | Twin gruplar = refactor fırsatı; fix_tags = teknik borç; callgraph = coupling |

---

### 10.5 Otomatikleştirme İpucu (AI İçin)

Bu protokolü **tek komutla** çalıştıran hazır script: `H:\devkit\devkit-bootstrap.py`

```bash
# Temel kullanım (aktif proje için)
python devkit-bootstrap.py

# Belirli proje için
python devkit-bootstrap.py --project MyProject

# Sadece JSON sayısal model (hızlı, markdown okumaz)
python devkit-bootstrap.py --json-only

# Mevcut KB'yi kullan (rescan atla)
python devkit-bootstrap.py --skip-rescan
```

Script şunu yapar: rescan → JSON çıktılar (scan/check/techdebt) → Markdown raporlar (QUICKREF, PROJECT_MAP, ARCHITECTURE, DEPENDENCIES) → meta.yaml + flows → subsystems → PROJECT_RULES/STATUS/CONTEXT/ISSUES → özet rapor.

Eski bash function yöntemi de hala çalışır:

```bash
# ~/.bashrc veya proje içinde devkit-bootstrap.sh
devkit-bootstrap() {
  local project="${1:-$(python devkit.py current | cut -d' ' -f1)}"
  python devkit.py rescan
  python devkit.py scan --json
  python devkit.py check --json
  python devkit.py techdebt --json
  echo "=== QUICKREF ==="; cat .devkit/KB/QUICKREF.md
  echo "=== ARCHITECTURE ==="; cat .devkit/KB/ARCHITECTURE.md
  echo "=== META ==="; cat .devkit/meta.yaml
  echo "=== DEPENDENCIES ==="; cat .devkit/KB/DEPENDENCIES.md
  echo "=== STATUS ==="; cat .devkit/STATUS.yaml
  echo "=== ISSUES ==="; cat .devkit/ISSUES.md
}
```

---

## 11. Bilinen Sınırlar & Gotchas (Kullanım Sırası)

| Alan | Detay | Workaround |
|------|-------|------------|
| **Sadece Python derin analiz** | JS/TS/Rust/Go/C# için `scan.json` sadece dosya listesi + hash üretir. `deps/quality/techdebt` Python-specific. | Multi-lang projede Python tarafına odaklan, diğer diller için ayrı toolchain. |
| **PyYAML stdlib değil** | `meta.yaml` okunamazsa `ARCHITECTURE.md` boş gelir. | `pip install pyyaml` veya `meta.yaml` JSON olarak da yaz. |
| **Relative import (namespace pkg)** | `__init__.py` olmayan paketlerde `from . import x` çözmez. | `__init__.py` ekle (boş olsa bile) veya `deps.py` geliştirecek PR at. |
| **AST cache thread-safety** | `gui.py` threaded, `scan.py` global `_CACHE` dict — race condition riski. | CLI modunda (`devkit.py`) sorun yok. GUI kullanırken `sync` butonuna basıp bitmesini bekle. |
| **Health check env** | `config.env_path` ayarlanmazsa sistem python'u kullanır — yanlış env'de test eder. | Wizard'da `python.exe` mutlaka seç (venv'in python'u). |
| **Twin false positive** | Benzer yapıda ama farklı amaçlı fonksiyonları twin olarak yakalayabilir. | `techdebt --json` ile `twin_detailed` incele, `similarity` skoru (gelecek FAZ2) bekle. |
| **Output guard 5MB** | Çok büyük subsistem raporu 5MB geçerse `ValueError` fırlatır. | `engine/scan.py:21` `BIG_FILE_THRESHOLD=800` düşür (400) veya `reports/generate.py:300` limit artır. |
| **Concurrent sync (same project)** | Aynı proje için 2 process aynı anda yazma → fingerprint/state bozulabilir. | `devkit-lock` ile serialize ediliyor; farklı projeler bloklanmaz. |
| **hybrid_analyzer.py** | Eski `core.*` bağımlılıkları kaldırıldı (2026-09-18); bagımsız AST_ONLY mod. | LLM client istege baglı; verilmezse `analyze_files()` NotImplementedError fırlatmaz. |

---

## 12. Geliştirme Yol Haritası (Özet)

Detaylı plan: `GELISTIRME_PLANI.md`

| Faz | Konu | Süre | Durum |
|-----|------|------|-------|
| FAZ 0 | Plan onayı | 0.5 gün | ⏳ Bekliyor |
| FAZ 1 | `meta.example.yaml` + `meta.schema.json` + rules.md güncelleme | 1 gün | 📋 Planlı |
| FAZ 2 | `engine/quality.py` + `engine/techdebt.py` güçlendirme (hash+callers) | 2 gün | 📋 Planlı |
| FAZ 3 | AST cache + glob ignore + JSON kontrat + relative import fix | 1 gün | 📋 Planlı |
| FAZ 4 | `--json` flag tamamlama + GUI JSON copy + DEVELOPMENT_LOG şablonu | 1 gün | 📋 Planlı |
| FAZ 5 | Regression test + dokümantasyon güncelleme | 0.5 gün | 📋 Planlı |

**Toplam:** ~5 iş günü, tek kişi, sıfır bağımlılık korunarak.

---

*Bu rehber v2.2 — FAZ 1-5 tamamlandı: AI Self-Bootstrap (Bölüm 10), Bilinen Sınırlar (Bölüm 11), `--json` all commands, GUI JSON copy, Safe Delete/Karar Matrisi template, configurable output guard, batch health check, relative import PEP 420 fix. `sync` sonrası güncel kalır.*
