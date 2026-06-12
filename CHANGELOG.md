# Changelog

All notable changes to doi2bib are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] — 2026-06-12

### Added
- Batch conversion of DOIs from `.csv`, `.xlsx`, and `.xls` files to `.bib`
- CrossRef API integration for full structured metadata
- Semantic Scholar API integration for abstracts (~70% coverage)
- Europe PMC API integration as abstract fallback (biomedical / life sciences)
- doi.org content-negotiation as final fallback
- Auto-generated, collision-safe BibTeX cite keys (e.g. `Jumper2021Highly`)
- `--no-abstract` flag for faster, leaner output
- `--email` flag for CrossRef Polite Pool (higher rate limits)
- Failed-DOI log saved automatically as `*_failed_dois.txt`
- Progress bar via `tqdm` with graceful fallback when not installed
- CC BY 4.0 license
