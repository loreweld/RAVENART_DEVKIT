# RAVENART DEVKIT — AI Kod Geliştirme Destek Sistemi

Projeden bağımsız (**project-agnostic**) bir araç: Bir AI'ın (veya geliştiricinin) **hiç bilmediği bir kod tabanını büyük dosyaları tekrar okumadan** mimari olarak tanımasını ve geliştirme boyunca bu bilgiyi güncel tutmasını sağlar.

> **Felsefe:** *Haritayı önce çıkar, sonra oku; bilgiyi tek yerde tut; geçmişi sadece log'da sakla.*

- **Bağımlılık:** Sıfır üçüncü taraf bağımlılık (sadece stdlib + Tkinter)
- **Tip:** Proje-bağımsız, üretim kalitesinde
- **Dil:** Python 3.8+

## Ne Yapar?

| Yetenek | Üretir | Açıklama |
|---|---|---|
| **Yapısal Tarama (scan)** | `scan.json` | Tek AST geçişi: sınıf/fonksiyon/metod/imza/docstring + importlar (relative dahil) |
| **Bağımlılık (deps)** | `deps.json` | Graph/reverse/matrix + Tarjan SCC + relative import çözümü |
| **API Yüzeyi** | `api.json` | Alt-sistem bazlı sınıf/fonksiyon yüzeyi |
| **Kullanım Doğrulama** | `usage.json` | `pyproject.toml` bağımlılıkları vs. gerçek importlar |
| **Kalite Karnesi** | `quality.json` | 4 kriter (Aktiflik/Gereklilik/Kod Kalitesi/Bütünlük 0-10, toplam 0-40) |
| **Teknik Borç** | `techdebt.json` | İkiz (twin) tespiti (normalize MD5 hash + fuzzy isim), `fix_tags`, callgraph |
| **Sağlık** | `health.json` | Proje interpreter'ında subprocess import testi |
| **Etki** | — | `deps.json` üzerinden dependents/dependencies |
| **Sembol/Anahat** | — | `find` / `outline` ile sembol arama, `--json` destekli |
| **KB Raporları** | `KB/*.md` | QUICKREF / PROJECT_MAP / DEPENDENCIES / SYMBOL_INDEX / ARCHITECTURE / subsystems / flows |
| **State** | `STATUS.yaml` vb. | scan+health+deps+quality+techdebt → STATUS / CONTEXT / ENVIRONMENT / ISSUES |
| **Diff + Sync** | `fingerprint.json` | sha256 ile added/deleted/modified/moved + `DEVELOPMENT_LOG.md` |

**Ek altyapı:** AST cache (sha256 bazlı), glob ignore (`*.pyc`, `tests/*` vb. pattern'ler), `--json` çıktı (AI doğrudan JSON tüketir), output guard (1MB uyarı / 5MB engel).

## Ne Değildir?

- Build sistemi değildir; kodu değiştirmez, sadece analiz eder.
- Çıktıyı kendi klasörüne (`H:\devkit`) **asla** yazmaz; hep `<proje>/.devkit/` altına yazar.

## Başlangıç

```
DEVKIT.bat
```

veya:

```
python devkit.py <komut> [args]
python devkit-bootstrap.py
```

**Sihirbaz:** İlk kurulumda `init` komutu GUI klasör seçiciyle projeni kayıt altına alır; projeye özel bilgi ve ek kurallar ayrı `.txt` çıktıları olur.

**Komutlar:**
- `init` — Yeni proje kurulum sihirbazı
- `select [ad]` — Aktif projeyi değiştir
- `list` — Kayıtlı projeleri listele
- `help` — Kullanım kılavuzu

**Tek seferlik (manual) araçlar** (`python manual/scan.py <klasor> [--ignore ...]` vb.): kayıtlı proje olmadan tek geçişlik analiz; dosya yazmaz, sadece yazdırır.

## Çalışma Kuralları

Global kurallar `rules.md` içindedir: *üretim kalitesi, büyük resimden bakma, tek dosyada izole değişiklik yapmama, kısa-script dağınıklığından kaçınma* gibi ilkeler. Projeye özel kurallar `<proje>/.devkit/PROJECT_RULES.md` içinde tanımlanır ve globali ezer.

## Dokümantasyon

- `REHBER.md` — Kullanıcı + AI için ayrıntılı rehber
- `rules.md` — Global çalışma kuralları
- `GELISTIRME_PLANI.md` — Eski sistem (`_EVA_OLD_DEVKIT_ARCHIVE`) → yeni sistem adaptasyon planı ve dersler

## Yerel Kayıt

`registry.json` (makineye özel proje yolları) versiyon kontrolü dışındadır. Format şablonu: `registry.example.json`.

## Proje Yapısı

```
devkit/
├── devkit.py            # CLI giriş noktası
├── devkit-bootstrap.py  # Kurulum/başlatma yardımcısı
├── common.py            # Registry + proje kökü yardımcıları
├── gui.py               # Tkinter arayüz
├── engine/              # Tarama, deps, kalite, teknik borç, sağlık, etki, scaffold
├── reports/             # KB raporları + state üretici
├── wizard/              # Kurulum sihirbazı
├── templates/           # meta.yaml şablonu + JSON şeması
└── manual/              # Tek seferlik analiz araçları
```

## Lisans

Bu proje özel/henüz lisanssızdır. Kullanım ve dağıtım koşulları için proje sahibiyle iletişime geçin.

---

© 2026 **İlker Can Karagülle** · [Loreweld AI](https://loreweld.ai) tarafından geliştirildi.