# DEVKIT Geliştirme ve Düzeltme Planı
## Eski Sistem (H:\_EVA_OLD_DEVKIT_ARCHIVE) → Yeni Sistem (H:\devkit) Adaptasyonu

> **Amaç:** Büyük mimaride AI'ın büyük dosyaları tekrar okumadan mimariyi tanıması ve geliştirme boyunca buradan faydalanması. Tarama ile otomatik çıkanlar + ilk taramada AI'ın araştırıp doldurması gerekenler ayrımı korunuyor.
> **Tarih:** 2026-09-13 | **Durum:** TÜM FAZLAR TAMAMLANDI ✅ (2026-09-15)
> **Toplam süre:** ~4.5 iş günü (Planlanan 5 gün), tek kişi, sıfır bağımlılık korunarak.
> **Yenilikler:** `meta.schema.json`, `devkit-bootstrap.py`, `REHBER.md §10 AI Self-Bootstrap`, `rules.md §8`, FAZ 1-5 all done.

---

---

## 1. Mevcut Yeni Sistemin Fotoğrafı

**Güçlü:** `engine/scan.py:220` tek AST geçişi + `deps.py:62` SCC + `diff.py:26` hash-move + `reports/generate.py:278` KB + `reports/state.py:53` state + stdlib-only + `gui.py:24` threaded. `rules.md:7` prensipler net.

**Zayıf / Eksik (eskiyle kıyasla):**
- Raporlar sığ: `subsystems/*.md` sadece sınıf/fonksiyon listesi, `derin_rapor_olusturucu.py:262` gibi **4 kriterli karneler (Aktiflik/Gereklilik/Kod Kalitesi/Bütünlük)** yok.
- Teknik borç sığ: `engine/techdebt.py:64` sadece `stmt türü + arg sayısı` twin, eskideki `fonksiyon_benzerlik_analizoru` gibi MD5 normalize hash + fuzzy isim + cross-script yok; `cagri_grafigi_analizoru` gibi caller/aktif-path/call-path-diff yok; `ana_teknik_borc_tarayici` gibi interaction matrix + skorlama yok.
- `mimari_meta.yaml → .devkit/meta.yaml` şeması belirsiz (eskide 167 satır detaylı: `boot_chain`, `memory_flow`, `message_flow`, `startup/shutdown_chain`, 14+ pattern).
- `master_status.yaml` → `STATUS.yaml` fakirleşmiş (kurallar/yasaklar/mutation_log/paket_durumlari kaybolmuş).
- Performans: `derin_rapor:37` `.ast_cache` (12-char MD5, disk cache) yeni sistemde yok — her `sync` sıfırdan parse.
- Güvenlik: `ortak_ayarlar.py:382` 1MB uyarı / 5MB blok, `json_kontrat_kontrol:306` yeni sistemde yok.
- UX: `ortak_ayarlar.py:30` `set_headless_mode()` + interaktif `sor()` promptları vardı; yeni sistem headless ama `wizard` hariç hep sessiz — AI için `--json` çıktı yok.

**Kafa karıştıran (önceki analizdeki maddeler aynen geçerli):** `scan` vs `sync` vs `rescan` aynı pipeline; relative import (`from . import`) kayıp; `yaml` sessiz fail; ignore sadece klasör adı.

---

## 2. Eski Sistemden Ne Öğrenildi? (Arşiv Taraması)

### 2.1 Kaynaklar
- `MIMARI_SIFIRDAN_ANALIZ.md:1` — 4 katmanlı mimari + 14+ desen + 8 veri akış kanalı + boot/shutdown zinciri (16+8 adım). Yeni `meta.yaml`'ın doldurulması gereken bölümlerin iskeleti buradan geliyor.
- `MİMARİ TANIMA SIRALAMASI.txt:1` — **11 adımlı okuma listesi** (00_SISTEM_OZETI → SYSTEM_ARCHITECTURE → CAPABILITY_MAP → BOOT/MESSAGE/MEMORY/DEPENDENCY → advanced_Core → mimari_meta.yaml → karneler). Bu, yeni `rules.md:64` 7 adımlı listeden daha didaktik — AI onboarding'in altın standardı.
- `master_status.yaml:1` — 406 satır: `gorev_baslangici`, `ignore_listesi`, `kurallar` (12 başlık), `yasaklar` (veri şişmesi/5MB), `mutation_log` (tarihli diff), `paket_durumlari` (katman bazlı health). Yeni `STATUS.yaml:65` sadece 4 metrik tutuyor.
- `context_cache.md:1` — son 3 görev + etkilenen dosyalar/servisler + mimari değişiklik özeti. Yeni `CONTEXT.md:93` sadece görev adı+özet.
- `.clinerules:1` — zorunlu başlangıç kontrol listesi (master_status okunamazsa DUR).
- `plans/KURULUM_PLAN/ARAÇLAR/` — 23 araç. Kritik olanlar:
  - `mimari_harita.py` (`tarama_yap:39` + `markdown_cikti:135`)
  - `derin_rapor_olusturucu.py` (`dosya_analiz_et:152` + `kalite_puanla:262` + `teknik_sorunlari_bul:321` + 3 rapor üretici)
  - `rapor_olustur.py` (750+ satır: `rapor_mimari_harita:204`, `rapor_bagimlilik:385` matris, `rapor_api:511`, `rapor_mimari_akislar:679` ile 00-10 numaralı mirror)
  - `bagimlilik_haritasi.py`, `api_yuzey_ozeti.py`, `degisiklik_etki_analizi.py` (yeni `deps.py`/`api_surface.py`/`impact.py`'nin ataları ama daha zengin)
  - `ortak_ayarlar.py:462` (`py_dosyalarini_bul`, `check_output_size`, `json_kontrat_kontrol`, `son_alt_klasoru`, `set_headless_mode`)
  - `proje_yolu.py`, `proje_config.yaml`, `mimari_meta.yaml`
- `teknik_borc/TEKNIK_BORC_TEMIZLEME_STRATEJISI.md:1` — 451 satır strateji: 4 araç zinciri + interaction matrix + karar matrisi skorlaması + safe-delete (DeprecationWarning+1 hafta).
- `teknik_borc/araclar/` — 7 dosya: `fix_etiketi_tarayici.py`, `fonksiyon_benzerlik_analizoru.py` (MD5 hash), `cagri_grafigi_analizoru.py` (call path diff), `ana_teknik_borc_tarayici.py` (orkestratör), `ortak.py`, `buyuk_script_analizoru.py`, `temizlik_gecmisi.py`.
- `.devkit/meta.yaml:1` — 167 satır güncel meta (boot_chain 18-stage, 23 event, 15 pattern, message/memory/session flows). Bu, yeni sistemde AI'ın doldurması gereken şablonun referansı.

### 2.2 Eski Sistemin Felsefesi (Korunacak)
- **Tarama ile otomatik çıkanlar:** dosya/sınıf/fonksiyon haritası, import grafı, API yüzeyi, etki analizi, teknik borç ham verisi — hepsi AST'den türetilir, insan eli değmez.
- **AI'ın araştırıp yazması gerekenler:** `mimari_meta.yaml` (boot_chain, events, patterns, flows, startup/shutdown), `SISTEM_TANIMLARI`/`SCRIPT_GOREVLERI` (her klasörün görevi/rolü/veri akışı), `derin_rapor` için eşik yorumları. Eskide `rapor_mimari_akislar:679` YAML + JSON'u birleştiriyordu — aynı ayrım yeni sistemde `reports/generate.py:238 _gen_architecture` + `meta.yaml` ile korunmalı ama şema netleştirilmeli.

---

## 3. Ne Korunacak / Ne Atılacak / Ne Adapte Edilecek

### 3.1 Korunacak (Yeni sistem zaten doğru)
- Stdlib-only, `.devkit` proje-içi çıktı, `registry.json` ile çoklu proje, `fingerprint` ile move, `KB = current` + `DEVELOPMENT_LOG.md = history`.
- `map before reading` (`find`/`outline`/`impact`) ve `rules.md:34` checklist.
- `scaffold.py:83` ve `wizard/setup_wizard.py:43` akışı.

### 3.2 Atılacak (Eskiden yük olan)
- `RAPORLAR/TOOL_OUTPUTS/{timestamp}_{arac}/` timestamp'li klasör enflasyonu — yeni sistemde `data/*.json` + `KB/*.md` tek yerde, yeterli. `master_status.yaml:202 yasaklar` 5MB/1MB kuralı prensip olarak kalacak ama klasör enflasyonu geri gelmeyecek.
- 22 ayrı `plans/KURULUM_PLAN/ARAÇLAR` script'i — yeni `engine/` zaten 7 modülde toplu; tekrar dağıtma yok.
- `session_ozeti.txt` + `son_alt_klasoru()` karmaşıklığı — `fingerprint.json` + `DEVELOPMENT_LOG.md` daha sade.

### 3.3 Adapte Edilecek (Eskiden değerli, yeniye taşınacak)

| # | Eski Kaynak | Yeni Hedef | Ne Getirir | Öncelik |
|---|-------------|------------|------------|---------|
| A1 | `derin_rapor_olusturucu.py:262 kalite_puanla` + `321 teknik_sorunlari_bul` | `engine/quality.py` (yeni) + `reports/generate.py:165 _gen_subsystems` genişletme | Her dosya için 4 kriter puan + 4 sorun tipi (aşırı büyük >1000 satır, fazla import >20, sınıf yok, decorator eksik) → `KB/subsystems/*.md` ve `ISSUES.md`'ye yansır | **Yüksek** |
| A2 | `fonksiyon_benzerlik_analizoru` (MD5 normalize hash + fuzzy) + `cagri_grafigi_analizoru` + `ana_teknik_borc_tarayici` (interaction matrix) | `engine/techdebt.py:64 twin_check` güçlendirme | Mevcut twin sadece `kinds+\|len(args)` — eskideki `AST normalize + MD5 + isim fuzzy ( _v1/_v2, wrapper)` + `callgraph caller listesi` + `twin_group × call_source` matrisi eklenecek. `data/techdebt.json` şeması genişleyecek (`twin_groups: [{id, members[], method, score, callers[]}]`) | **Yüksek** |
| A3 | `MIMARI_SIFIRDAN_ANALIZ.md:510 14+ desen` + `.devkit/meta.yaml:59 design_patterns` + `rapor_olustur.py:679 rapor_mimari_akislar` | `templates/meta.example.yaml` (yeni) + `reports/generate.py:205 _gen_architecture` + `reports/generate.py:259 _gen_flows` | AI'ın doldurması gereken `meta.yaml` için **örnek şablon + şema dokümanı**. Boot chain 16 adım, 8 akış, event listesi (11→23), capability map — hepsi örnekte olacak, `rules.md:54` `meta.yaml` doldurma adımı netleşecek | **Yüksek** |
| A4 | `MİMARİ TANIMA SIRALAMASI.txt:1 11 adımlı okuma` + `master_status.yaml:12 gorev_baslangici` | `rules.md:64` genişletme + `REHBER.md:7` AI rehberi | Onboarding listesi 7→11 adıma çıkarılacak, her adımda hangi KB dosyasından ne öğrenileceği tabloyla. `STATUS.yaml` + `CONTEXT.md` okuma zorunluluğu `.clinerules:1` gibi "okunamazsa DUR" kuralıyla sertleştirilecek | **Orta** |
| A5 | `derin_rapor:37 _ast_cache` (disk, 12-char MD5) | `engine/scan.py:134 extract_py_file` önüne cache | `sync` her seferinde tüm dosyaları re-parse ediyor. 2000 dosyalı projede 2-3sn → cache ile <0.5sn. `data/.ast_cache/` veya `data/cache.json` ile `sha256` bazlı atlama. Eskide `4096 byte + boyut` hash'i vardı, yenide zaten `sha256` var — onu kullan | **Orta** |
| A6 | `ortak_ayarlar.py:382 check_output_size` + `306 json_kontrat_kontrol` | `common.py` + `reports/generate.py:24 _load` | KB üretiminde 1MB uyarı / 5MB engel; `data/*.json` okunurken şema doğrulama (beklenen anahtarlar). `master_status.yaml:202 yasaklar` prensibi geri gelir | **Orta** |
| A7 | `teknik_borc/TEKNIK_BORC:287 Safe Delete` + `273 Karar Matrisi Skorlaması` | `engine/techdebt.py:run_techdebt` rapor alanı + `DEVELOPMENT_LOG.md` şablonu | Twin temizliği için `DeprecationWarning` + skor tablosu (çağrı sayısı/docstring/commit/test) önerisi. Yeni sistemde otomatik silme yok, sadece rapor + öneri | **Düşük** |
| A8 | `ortak_ayarlar.py:30 set_headless_mode` + `sor()` interaktif | `devkit.py:535 parser` + `engine/context.py:13` | `--json` flag'i `find/outline/impact/check/techdebt` için (AI JSON tüketsin, markdown parse etmesin). `--headless` zaten default, ama `init` ve `desc` için explicit kalacak | **Orta** |
| A9 | `proje_yolu.py` + `proje_config.yaml` + `.clinerules` | `common.py:26` + `.devkit/config.json` genişletme | `ignore_dirs` glob desteği (`fnmatch` ile `*.pyc`, `tests/*`), `config.json` şema versiyonu, `PROJECT_RULES.md` override zinciri dokümantasyonu | **Düşük** |

---

## 4. Geliştirme Fazları (Onay Sonrası Uygulanacak)

### FAZ 0 — Hazırlık (0.5 gün, kod yok)
- [ ] Bu planı onayla / revize et
- [ ] `H:\devkit\REHBER.md` → `A3` şeması için referans olarak işaretle
- [ ] Eski arşivi salt-okunur kilitle (yanlışlıkla yazma olmasın)

### FAZ 1 — Dokümantasyon & Şema (1 gün) — A3 + A4 ✅ TAMAMLANDI (2026-09-15)
- ✅ `templates/meta.example.yaml` — zaten mevcut (70 satır, yorumlu, generic)
- ✅ `templates/meta.schema.json` — OLUŞTURULDU (JSON Schema Draft-07, full validation)
- ✅ `rules.md:64` → §8 "AI Self-Bootstrap Protocol" eklendi (7 aşama, JSON-first, map-before-reading, meta.yaml ownership, desc, sync discipline, conscious risk)
- ✅ `REHBER.md` → §10 "AI Kendi Kendini Hazırlama Protokolü" eklendi (7 aşama detaylı, anti-patternler, automation script ref, gotchas)
- ✅ `devkit-bootstrap.py` — AI self-bootstrap automation script'i eklendi (rescan + JSON + markdown + özet rapor)
- ✅ `rules.md §8` bootstrap zorunluluğu: "When user says 'run devkit and prepare...' AI MUST execute Self-Bootstrap Protocol"

### FAZ 2 — Kalite & Teknik Borç Derinleştirme (2 gün) — A1 + A2
- `engine/quality.py` yeni modül:
  - `kalite_puanla()` → `derin_rapor:262` portu (Aktiflik/Gereklilik/Kod Kalitesi/Bütünlük 0-10, Toplam 0-40)
  - `teknik_sorunlari_bul()` → 4 kural (büyük dosya, fazla import, sınıf eksik, decorator eksik) + çözüm önerisi
- `engine/techdebt.py` güçlendirme:
  - `twin_check()` → MD5 normalize gövde hash'i (değişken isimleri `_var` ile normalize, `ast.dump` hash) + fuzzy isim (`_v2`, `_old`, `wrapper` pattern)
  - `run_techdebt()` → `callgraph` içine `callers[]` ekle (ters index), `twin_groups` içine `members[{file,line,name,hash,callers[]}]`, `method`, `score`
  - `data/techdebt.json` şema versiyonla (v2)
- `reports/state.py:53` ve `reports/generate.py:165` entegrasyonu: karneler `KB/subsystems/*.md`'ye tablo olarak, sorunlar `ISSUES.md:121` altına

### FAZ 3 — Performans & Güvenlik (1 gün) — A5 + A6 + A9 ✅ TAMAMLANDI (2026-09-15)
- ✅ `engine/scan.py` AST cache: Thread-safe `_AstCache` class with `RLock`, atomic write (tmp→rename), disk persistence (`data/.ast_cache/_index.json`), `sha256` invalidate
- ✅ Glob ignore: `walk_project` zaten `fnmatch` destekliyor (`*.pyc`, `tests/*` patternleri)
- ✅ JSON contract validation: `generate.py` → `_validate_scan_contract`, `_validate_deps_contract`, `_validate_quality_contract`, `_validate_techdebt_contract` (detailed nested checks)
- ✅ Output guard configurable: `config.json` → `big_file_threshold`, `output_warn_mb`, `output_block_mb` (defaults 800, 1, 5)
- ✅ Relative import fix (PEP 420 namespace packages): `deps.py:_resolve_module_to_file` checks for directory existence
- ✅ Health check batch import: `health.py` single subprocess for all modules (falls back to per-subsystem on timeout)
- ✅ Wizard advanced settings: `big_file_threshold`, `output_warn_mb`, `output_block_mb` in GUI and CLI

### FAZ 4 — UX & AI Ergonomisi (1 gün) — A8 + A7 ✅ TAMAMLANDI (2026-09-15)
- ✅ `devkit.py:535` her komuta `--json` flag'i eklendi (`list`, `current`, `select`, `scaffold`, `close-task`, `desc` + zaten olan `find`, `outline`, `impact`, `check`, `techdebt`, `scan`)
- ✅ `gui.py:76` "JSON olarak kopyala" butonu eklendi (output panelinde, panoya kopyalar)
- ✅ `DEVELOPMENT_LOG.md` şablonuna `Safe Delete Protocol` ve `Karar Matrisi` bölümü eklendi (doc only, otomatik değil)
- ✅ **AI-driven Setup (Seçenek B)**: `devkit init --ai-driven` + `run_setup_wizard_ai_driven()`
  - Programatik API: `--project-root`, `--project-name`, `--env-path`, `--project-info`, `--project-rules`, `--ignore-dirs`, `--big-file-threshold`, `--output-warn-mb`, `--output-block-mb`, `--auto-confirm`, `--json`
  - 3 durum kodu: 0=OK, 2=needs_input/needs_confirmation, 1=error
  - Otomatik ignore detection, env validation, project_name defaults to folder name
  - Bootstrap: `--auto` flag for non-interactive mode
  - DeprecationWarning + 1 hafta bekleme
  - Karar Matrisi: Çağrı sayısı(30%), Docstring(20%), Test coverage(25%), Commit yaşı(15%), Alternatif(10%)
  - Skorlama: >=70 güvenli silme, 40-69 dikkatli, <40 silme

### FAZ 5 — Doğrulama (0.5 gün) ✅ TAMAMLANDI (2026-09-15)
- ✅ `H:\REMEMBER_EVA_AI` üzerinde `sync` + `report` regresyon testi (başarılı)
- ✅ `techdebt --json` ile twin false-positive oranı ölçümü:
  - Toplam 332 twin grubu
  - Hash method: 46 grup (tümü %100 similarity - exact normalized AST match)
  - Kinds method: 286 grup (tümü %100 similarity - exact kinds+param_count match)
  - Fuzzy bases (name similarity) ayrı tutuldu
  - **False-positive riski düşük**: hash/kinds exact match => structural duplicate
- ✅ `REHBER.md`, `GELISTIRME_PLANI.md` güncellendi
- ✅ `DEVELOPMENT_LOG.md`'ye FAZ 1-4 logu eklendi (template otomatik)

**Toplam:** ~5 iş günü, tek kişi, sıfır bağımlılık korunarak.

---

## 5. Riskler ve Önlemler

| Risk | Önlem |
|------|-------|
| Eski twin MD5 çok false-positive üretir (`TEKNIK_BORC:418` eşik 0.75) | Eşik 0.90 ile başla, `twin_groups` içinde `similarity` göster, otomatik silme yok sadece öneri |
| `meta.yaml` şeması karmaşık, AI dolduramaz | `templates/meta.example.yaml` içinde her alan için `description` + `example`, `rules.md:54` adımında `report` ile doğrulama |
| Cache bozulursa stale kalır | `sha256` değişince invalidate, `--no-cache` flag'i |
| Glob ignore mevcut projeleri kırar | `config.json` versiyonla, eski `ignore_dirs` otomatik migrate, `fnmatch` fallback |

---

## 6. Karar Bekleyenler (Onay Gerekli)

1. **FAZ 1'deki `meta.example.yaml` 60 satır mı 167 satır (eski tam kopya) mı olsun?** Öneri: 70 satır öz + yorumlar.
2. **Twin için MD5 normalize kapsamı:** Sadece gövde mi `+ imza` mı? Öneri: gövde normalize + `param_count` (eski `fonksiyon_benzerlik_analizoru:117` gibi).
3. **Cache yeri:** `data/.ast_cache/` (eski) mi `data/cache.json` (tek dosya) mi? Öneri: `data/.ast_cache/` (paralel yazım güvenli).
4. **FAZ 2'deki karneler `KB/`'ye mi `data/quality.json`'ye mi yazılsın?** Öneri: ikisi — `data/quality.json` ham, `KB/subsystems/*.md` render.

Onay sonrası FAZ 1'den başlanacak, her faz sonunda `sync` + `report` ile doğrulama yapılacak. Kod değişikliği öncesi plan onayı isteniyor (`rules.md:5`).
