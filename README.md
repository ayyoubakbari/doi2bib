# doi2bib

**Batch DOI → BibTeX converter with abstracts, built for researchers.**

Convert a CSV or Excel file containing hundreds of DOIs into a single, fully
populated `.bib` file — including abstracts — ready to import into Zotero,
Mendeley, JabRef, or Overleaf. No manual copy-pasting, no API keys required.

---

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-CC%20BY%204.0-green?style=flat-square" alt="CC BY 4.0">
  <img src="https://img.shields.io/badge/APIs-CrossRef%20%7C%20Semantic%20Scholar%20%7C%20EuropePMC-orange?style=flat-square" alt="APIs">
  <img src="https://img.shields.io/badge/status-stable-brightgreen?style=flat-square" alt="Status">
</p>

---

## Why doi2bib?

If you are writing a literature review, systematic review, or any paper that
references hundreds of articles, manually exporting BibTeX entries one by one
wastes hours of research time. doi2bib solves this:

- Give it a spreadsheet of DOIs
- Get back a `.bib` file with complete metadata and abstracts
- Import directly into your reference manager

500 DOIs → complete `.bib` file in under 10 minutes.

---

## Features

| Feature | Detail |
|---|---|
| **Bulk processing** | Handles hundreds or thousands of DOIs in one run |
| **Full metadata** | Authors, title, journal, year, volume, issue, pages, publisher, ISSN, DOI, URL |
| **Abstracts** | Fetched from Semantic Scholar and Europe PMC |
| **Smart fallback** | 4-tier pipeline — no entry is silently lost |
| **Auto cite keys** | Human-readable keys like `Jumper2021Highly`, guaranteed unique |
| **Failed-DOI log** | Any unresolvable DOIs saved to a separate `.txt` for manual review |
| **Flexible input** | `.csv`, `.xlsx`, `.xls` — any column name |
| **Rate-limit safe** | Configurable delay + CrossRef Polite Pool support |

---

## Metadata pipeline

For each DOI, doi2bib queries up to four sources in order:

```
DOI
 │
 ├─ 1. CrossRef API ──────────────── authors, title, journal, year, volume,
 │                                   issue, pages, publisher, ISSN, keywords
 │       │
 │       ├─ 2. Semantic Scholar ──── abstract  (~70 % of all disciplines)
 │       │
 │       └─ 3. Europe PMC ────────── abstract fallback  (biomedical / life sci)
 │
 └─ 4. doi.org BibTeX ─────────────── last resort (basic fields, no abstract)
```

---

## Installation

**Requirements:** Python 3.9 or higher.

```bash
# 1. Clone the repository
git clone https://github.com/akbari-moghanjoughi/doi2bib.git
cd doi2bib

# 2. Install dependencies
pip install -r requirements.txt
```

That is all — no API keys, no accounts, no configuration files.

---

## Quick start

```bash
python doi2bib.py --input my_references.xlsx --email yourname@institution.edu
```

This produces `references.bib` in the current directory.

---

## Usage

```
python doi2bib.py [OPTIONS]

Options:
  --input        PATH    CSV or Excel file containing DOIs  (required)
  --doi_column   TEXT    Column name that holds the DOIs    (default: "DOI")
  --output       PATH    Output .bib filename               (default: references.bib)
  --email        TEXT    Your email for CrossRef Polite Pool (strongly recommended)
  --delay        FLOAT   Seconds between requests           (default: 0.3)
  --no-abstract          Skip abstract fetching — faster, smaller output
  --version              Show version and exit
```

### Examples

```bash
# Basic usage with an Excel file
python doi2bib.py --input refs.xlsx

# Specify a custom column name and output file
python doi2bib.py --input refs.csv --doi_column "Digital Object Identifier" --output my_library.bib

# Register your email with CrossRef for higher rate limits (recommended)
python doi2bib.py --input refs.xlsx --email you@university.edu

# Fast mode: skip abstract fetching
python doi2bib.py --input refs.xlsx --no-abstract --delay 0.1
```

---

## Input file format

Your CSV or Excel file needs one column containing DOIs. Any of these formats
are accepted:

| Accepted DOI format | Example |
|---|---|
| Bare DOI | `10.1038/s41586-021-03819-2` |
| With `doi:` prefix | `doi:10.1038/s41586-021-03819-2` |
| Full URL | `https://doi.org/10.1038/s41586-021-03819-2` |
| With `dx.doi.org` | `https://dx.doi.org/10.1038/s41586-021-03819-2` |

A minimal example (`examples/sample_dois.csv`):

```
DOI
10.1038/s41586-021-03819-2
10.1126/science.abc4346
10.1016/j.cell.2021.01.007
```

---

## Output format

Each entry in the `.bib` file looks like this:

```bibtex
@article{Jumper2021Highly,
  author         = {Jumper, John and Evans, Richard and Pritzel, Alexander and ...},
  title          = {{Highly accurate protein structure prediction with AlphaFold}},
  year           = {2021},
  volume         = {596},
  number         = {7873},
  pages          = {583--589},
  publisher      = {Springer Nature},
  issn           = {0028-0836},
  url            = {https://doi.org/10.1038/s41586-021-03819-2},
  doi            = {10.1038/s41586-021-03819-2},
  journal        = {Nature},
  abstract       = {{Proteins are essential to life, and understanding their
                    structure can facilitate a mechanistic understanding of their
                    function. ...}}
}
```

The cite key (`Jumper2021Highly`) is generated automatically and guaranteed
unique within the output file.

---

## Importing into your reference manager

| Manager | Steps |
|---|---|
| **Zotero** | `File → Import → BibTeX file` |
| **Mendeley** | `File → Import → BibTeX (.bib)` |
| **JabRef** | `File → Import → BibTeX` (native format) |
| **Overleaf** | Upload `.bib` directly to your project |
| **EndNote** | `File → Import → BibTeX` |

---

## Handling failed DOIs

A small percentage of DOIs (~2–5 %) may fail, typically because:

- The DOI is malformed or contains a typo
- The publisher has not registered full metadata with CrossRef
- The paper is too recent to be indexed

When this happens, doi2bib saves a `references_failed_dois.txt` file alongside
your `.bib`. For each failed entry you can:

1. Search manually at [search.crossref.org](https://search.crossref.org)
2. Look up the paper on [Google Scholar](https://scholar.google.com) → Cite → BibTeX
3. Check [Semantic Scholar](https://www.semanticscholar.org) directly

---

## Performance

| DOIs | Estimated time (default 0.3 s delay) |
|---|---|
| 100 | ~1–2 minutes |
| 500 | ~5–8 minutes |
| 1 000 | ~10–15 minutes |
| 2 000+ | ~20–30 minutes |

To speed things up, reduce `--delay` (minimum ~0.1 s to stay within API limits)
and use `--no-abstract` if you don't need abstracts.

---

## API credits

doi2bib is built on three excellent free APIs. Please respect their terms:

| API | Coverage | Rate limit |
|---|---|---|
| [CrossRef](https://api.crossref.org) | All disciplines | Polite Pool: ~50 req/s with email |
| [Semantic Scholar](https://api.semanticscholar.org) | All disciplines | ~100 req/min |
| [Europe PMC](https://europepmc.org/RestfulWebService) | Biomedical / life sciences | Generous |

---

## Citing this tool

If doi2bib saves you time in your research, please cite it:

```bibtex
@software{AkbariMoghanjoughi2026doi2bib,
  author       = {Akbari-Moghanjoughi, A.},
  title        = {{doi2bib: Batch DOI to BibTeX Converter with Abstracts}},
  year         = {2026},
  institution  = {Universitat Polit{\`e}cnica de Catalunya (UPC)},
  url          = {https://github.com/akbari-moghanjoughi/doi2bib},
  license      = {CC BY 4.0}
}
```

---

## Contributing

Contributions are very welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for
guidelines. Ideas for future features are listed there too.

---

## License

This project is licensed under the
[Creative Commons Attribution 4.0 International (CC BY 4.0)](LICENSE) license.

You are free to use, share, and adapt this tool for any purpose, including
commercially, as long as you give appropriate credit.

---

**Author:** A. Akbari-Moghanjoughi  
**Affiliation:** Universitat Politècnica de Catalunya (UPC)  
**Contact:** open an issue on GitHub
