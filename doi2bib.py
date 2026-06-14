"""
doi2bib — Batch DOI to BibTeX Converter with Abstracts
=======================================================
Converts a CSV or Excel file of 500+ DOIs into a fully populated .bib file,
including abstracts, for direct import into Zotero, Mendeley, JabRef, or Overleaf.

Author      : A. Akbari-Moghanjoughi
Affiliation : Universitat Politècnica de Catalunya (UPC)
License     : Creative Commons Attribution 4.0 International (CC BY 4.0)
Repository  : https://github.com/ayyoubakbari/doi2bib

Abstract pipeline (7 sources tried in order until one succeeds):
  1. CrossRef          — structured metadata + abstract when publisher shares it
  2. OpenAlex          — best overall abstract coverage (Physics/Eng/CS ++)
  3. Semantic Scholar  — strong for CS / ML / interdisciplinary
  4. Europe PMC        — biomedical / life sciences
  5. CORE              — open-access full-text repository
  6. Unpaywall         — open-access metadata including abstracts
  7. doi.org BibTeX    — last-resort fallback (basic fields, no abstract)

Usage:
    pip install pandas openpyxl requests tqdm
    python doi2bib.py --input refs.xlsx --doi_column "DOI" --output references.bib --email you@institution.edu

Arguments:
    --input        Path to CSV or Excel file (.csv / .xlsx / .xls)
    --doi_column   Column name that contains the DOIs  (default: "DOI")
    --output       Output .bib filename                (default: references.bib)
    --email        Your email — used by CrossRef Polite Pool AND OpenAlex (strongly recommended)
    --delay        Seconds between API requests        (default: 0.3)
    --no-abstract  Skip abstract fetching (faster, smaller file)
"""

import argparse
import html
import re
import sys
import time
from pathlib import Path

import requests
import pandas as pd

try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, iterable, **kw):
            self.it = iterable; self.total = kw.get("total", "?"); self.n = 0
        def __iter__(self):
            for x in self.it:
                self.n += 1
                print(f"  [{self.n}/{self.total}]", end="\r", flush=True)
                yield x
            print()
        def write(self, s): print(s)


# ── Constants ─────────────────────────────────────────────────────────────────

__version__ = "1.1.0"
__author__  = "A. Akbari-Moghanjoughi"

CROSSREF_TYPE_MAP = {
    "journal-article":     "article",
    "proceedings-article": "inproceedings",
    "book-chapter":        "incollection",
    "book":                "book",
    "dissertation":        "phdthesis",
    "report":              "techreport",
    "posted-content":      "misc",
    "dataset":             "misc",
}


# ── Utility helpers ───────────────────────────────────────────────────────────

def clean_doi(raw: str) -> str:
    doi = str(raw).strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.strip()


def clean_html(text: str) -> str:
    """Strip HTML/XML tags and decode entities."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Remove JATS XML artefacts common in CrossRef abstracts
    text = re.sub(r"\b(Abstract|ABSTRACT)\s*:?\s*", "", text, count=1).strip()
    return text


def escape_bibtex(text: str) -> str:
    if not text:
        return ""
    for old, new in [("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_")]:
        text = text.replace(old, new)
    return text


def make_citekey(authors: list, year: str, title: str) -> str:
    last   = "Unknown"
    if authors:
        last = re.sub(r"[^a-zA-Z]", "", authors[0].split(",")[0].split()[-1])
    yr     = str(year) if year else "0000"
    words  = re.findall(r"[A-Za-z]{4,}", title or "")
    suffix = words[0].capitalize() if words else "Ref"
    return f"{last}{yr}{suffix}"


def _get_year_from_crossref(msg: dict) -> str | None:
    for field in ("published", "published-print", "published-online", "issued"):
        parts = msg.get(field, {}).get("date-parts", [[]])
        if parts and parts[0]:
            return str(parts[0][0])
    return None


# ── API 1: CrossRef ───────────────────────────────────────────────────────────

def fetch_crossref(doi: str, session: requests.Session, email: str = "") -> dict | None:
    """
    CrossRef REST API — primary source for structured metadata.
    Abstract available only when publisher explicitly shares it (~40% of papers).
    Springer, Elsevier, IEEE rarely share abstracts here.
    https://api.crossref.org
    """
    params = {"mailto": email} if email else {}
    try:
        r = session.get(
            f"https://api.crossref.org/works/{doi}",
            params=params, timeout=15
        )
        if r.status_code != 200:
            return None
        msg = r.json().get("message", {})
    except Exception:
        return None

    entry_type = CROSSREF_TYPE_MAP.get(msg.get("type", ""), "misc")

    authors = []
    for a in msg.get("author", []):
        family = a.get("family", "")
        given  = a.get("given", "")
        if family:
            authors.append(f"{family}, {given}".strip(", "))
        elif given:
            authors.append(given)

    containers = msg.get("container-title", [])
    short_ct   = msg.get("short-container-title", [])
    event      = msg.get("event") or {}
    pages      = msg.get("page", "").replace("-", "--")

    return {
        "entry_type":   entry_type,
        "doi":          doi,
        "title":        (msg.get("title") or [""])[0],
        "authors":      authors,
        "year":         _get_year_from_crossref(msg),
        "journal":      containers[0] if containers else "",
        "journal_abbr": short_ct[0]   if short_ct   else "",
        "booktitle":    event.get("name", ""),
        "volume":       msg.get("volume",    ""),
        "number":       msg.get("issue",     ""),
        "pages":        pages,
        "publisher":    msg.get("publisher", ""),
        "issn":         (msg.get("ISSN")  or [""])[0],
        "isbn":         (msg.get("ISBN")  or [""])[0],
        "abstract":     clean_html(msg.get("abstract", "")),
        "keywords":     ", ".join(s.get("value", "") for s in msg.get("subject", [])),
        "url":          f"https://doi.org/{doi}",
    }


# ── API 2: OpenAlex ───────────────────────────────────────────────────────────

def fetch_openalex_abstract(doi: str, session: requests.Session, email: str = "") -> str:
    """
    OpenAlex — the most comprehensive open academic graph.
    Reconstructs abstracts from inverted index; excellent for Physics/Eng/CS/Springer.
    Covers 250M+ works. Free, no key needed (email for polite pool).
    https://openalex.org
    """
    params = {"mailto": email} if email else {}
    try:
        r = session.get(
            f"https://api.openalex.org/works/doi:{doi}",
            params=params, timeout=15
        )
        if r.status_code != 200:
            return ""
        data = r.json()

        # OpenAlex stores abstracts as an inverted index: {word: [positions]}
        inv_index = data.get("abstract_inverted_index")
        if inv_index:
            # Reconstruct the abstract from the inverted index
            word_positions = []
            for word, positions in inv_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort(key=lambda x: x[0])
            return " ".join(w for _, w in word_positions)

        # Some records also have a plain abstract field
        return clean_html(data.get("abstract", "") or "")
    except Exception:
        return ""


# ── API 3: Semantic Scholar ───────────────────────────────────────────────────

def fetch_s2_abstract(doi: str, session: requests.Session) -> str:
    """
    Semantic Scholar Graph API.
    Strong for CS, ML, neuroscience, and interdisciplinary fields.
    https://api.semanticscholar.org
    """
    try:
        r = session.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "abstract"},
            timeout=12,
        )
        if r.status_code == 200:
            return clean_html(r.json().get("abstract") or "")
    except Exception:
        pass
    return ""


# ── API 4: Europe PMC ─────────────────────────────────────────────────────────

def fetch_epmc_abstract(doi: str, session: requests.Session) -> str:
    """
    Europe PubMed Central — excellent for biomedical and life sciences.
    https://europepmc.org
    """
    try:
        r = session.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": f"DOI:{doi}", "format": "json",
                    "resultType": "core", "pageSize": 1},
            timeout=12,
        )
        if r.status_code == 200:
            results = r.json().get("resultList", {}).get("result", [])
            if results:
                return clean_html(results[0].get("abstractText") or "")
    except Exception:
        pass
    return ""


# ── API 5: CORE ───────────────────────────────────────────────────────────────

def fetch_core_abstract(doi: str, session: requests.Session) -> str:
    """
    CORE — aggregates open-access research from repositories worldwide.
    Good for engineering and CS papers deposited in institutional repositories.
    https://core.ac.uk
    """
    try:
        r = session.get(
            "https://api.core.ac.uk/v3/search/works",
            params={"q": f"doi:{doi}", "limit": 1},
            timeout=12,
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                return clean_html(results[0].get("abstract") or "")
    except Exception:
        pass
    return ""


# ── API 6: Unpaywall ─────────────────────────────────────────────────────────

def fetch_unpaywall_abstract(doi: str, session: requests.Session, email: str) -> str:
    """
    Unpaywall — tracks open-access versions of papers.
    Occasionally has abstracts not found elsewhere, especially for preprints.
    Email is required by Unpaywall's terms of use.
    https://unpaywall.org
    """
    if not email:
        return ""
    try:
        r = session.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": email},
            timeout=12,
        )
        if r.status_code == 200:
            return clean_html(r.json().get("abstract") or "")
    except Exception:
        pass
    return ""


# ── API 7: doi.org BibTeX fallback ───────────────────────────────────────────

def fetch_doi_org_bibtex(doi: str, session: requests.Session) -> str:
    """Raw BibTeX via doi.org content negotiation. No abstract, but basic fields."""
    try:
        r = session.get(
            f"https://doi.org/{doi}",
            headers={"Accept": "application/x-bibtex"},
            timeout=15,
        )
        if r.status_code == 200 and r.text.strip().startswith("@"):
            return r.text.strip()
    except Exception:
        pass
    return ""


# ── Abstract hunting ─────────────────────────────────────────────────────────

def hunt_abstract(doi: str, session: requests.Session, email: str) -> tuple[str, str]:
    """
    Try all abstract sources in order of coverage quality for Physics/Eng/CS.
    Returns (abstract_text, source_name).
    """
    sources = [
        ("OpenAlex",         lambda: fetch_openalex_abstract(doi, session, email)),
        ("Semantic Scholar", lambda: fetch_s2_abstract(doi, session)),
        ("Europe PMC",       lambda: fetch_epmc_abstract(doi, session)),
        ("CORE",             lambda: fetch_core_abstract(doi, session)),
        ("Unpaywall",        lambda: fetch_unpaywall_abstract(doi, session, email)),
    ]
    for name, fn in sources:
        try:
            result = fn()
            if result and len(result.strip()) > 30:   # sanity-check: real abstract
                return result.strip(), name
        except Exception:
            continue
    return "", "none"


# ── BibTeX serialiser ─────────────────────────────────────────────────────────

def build_bibtex(meta: dict, used_keys: set) -> str:
    entry_type = meta.get("entry_type", "misc")
    authors    = meta.get("authors", [])

    key = base = make_citekey(authors, meta.get("year"), meta.get("title", ""))
    counter = 2
    while key in used_keys:
        key = f"{base}{chr(96 + counter)}"
        counter += 1
    used_keys.add(key)

    fields: dict[str, str] = {}

    if authors:
        fields["author"] = " and ".join(authors)

    title = meta.get("title", "")
    if title:
        fields["title"] = "{" + escape_bibtex(title) + "}"

    for f in ("year", "volume", "number", "pages", "publisher",
              "issn", "isbn", "url", "keywords"):
        v = meta.get(f, "")
        if v:
            fields[f] = escape_bibtex(str(v))

    if meta.get("doi"):
        fields["doi"] = meta["doi"]

    if entry_type == "article" and meta.get("journal"):
        fields["journal"] = escape_bibtex(meta["journal"])
    elif meta.get("booktitle"):
        fields["booktitle"] = escape_bibtex(meta["booktitle"])
    elif meta.get("journal"):
        fields["journal"] = escape_bibtex(meta["journal"])

    abstract = meta.get("abstract", "")
    if abstract:
        fields["abstract"] = "{" + escape_bibtex(abstract) + "}"

    lines = [f"@{entry_type}{{{key},"]
    items = list(fields.items())
    for i, (field, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f"  {field:<14} = {{{value}}}{comma}")
    lines.append("}")
    return "\n".join(lines)


# ── Per-DOI pipeline ──────────────────────────────────────────────────────────

def process_doi(
    doi: str,
    session: requests.Session,
    email: str,
    skip_abstract: bool,
) -> tuple[dict | None, str]:

    # Step 1: CrossRef for structured metadata
    meta = fetch_crossref(doi, session, email)

    if meta:
        if not skip_abstract and not meta.get("abstract"):
            abstract, source = hunt_abstract(doi, session, email)
            meta["abstract"] = abstract
            src_tag = f"[abstract from {source}]" if abstract else "[no abstract found]"
        elif meta.get("abstract"):
            src_tag = "[abstract from CrossRef]"
        else:
            src_tag = "[skipped]"
        return meta, f"✅  OK {src_tag}"

    # Step 2: doi.org BibTeX fallback
    raw = fetch_doi_org_bibtex(doi, session)
    if raw:
        return {"_raw_bibtex": raw, "doi": doi}, "⚠️   fallback BibTeX (no abstract)"

    return None, "❌  FAILED — not found in any source"


# ── I/O helpers ───────────────────────────────────────────────────────────────

def load_dois(filepath: str, doi_column: str) -> list[str]:
    path = Path(filepath)
    if not path.exists():
        sys.exit(f"❌  File not found: {filepath}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(filepath, dtype=str)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, dtype=str)
    else:
        sys.exit(f"❌  Unsupported format '{suffix}'. Use .csv, .xlsx, or .xls")

    col_map = {c.lower(): c for c in df.columns}
    matched = col_map.get(doi_column.lower())
    if not matched:
        sys.exit(
            f"❌  Column '{doi_column}' not found.\n"
            f"    Available columns: {list(df.columns)}"
        )
    raw = df[matched].dropna().tolist()
    return [clean_doi(d) for d in raw if str(d).strip() not in ("", "nan")]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="doi2bib",
        description="Batch-convert DOIs from CSV/Excel to a full BibTeX file with abstracts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python doi2bib.py --input refs.xlsx --email me@uni.edu
  python doi2bib.py --input dois.csv --doi_column "Digital Object Identifier" --output my_library.bib
  python doi2bib.py --input refs.xlsx --no-abstract --delay 0.1
        """,
    )
    parser.add_argument("--input",       required=True)
    parser.add_argument("--doi_column",  default="DOI")
    parser.add_argument("--output",      default="references.bib")
    parser.add_argument("--email",       default="",
                        help="Your email — enables CrossRef & OpenAlex polite pools (recommended)")
    parser.add_argument("--delay",       type=float, default=0.3)
    parser.add_argument("--no-abstract", action="store_true")
    parser.add_argument("--version",     action="version", version=f"doi2bib {__version__}")
    args = parser.parse_args()

    print(f"\n  doi2bib v{__version__} — {__author__}, UPC")
    print(f"  {'─'*52}")
    print(f"  Input  : {args.input}")
    print(f"  Output : {args.output}")
    if args.email:
        print(f"  Email  : {args.email}")
    print(f"  Abstract sources: OpenAlex → Semantic Scholar → EuropePMC → CORE → Unpaywall")
    print()

    dois = load_dois(args.input, args.doi_column)
    print(f"  ✅  {len(dois)} DOIs loaded\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": f"doi2bib/{__version__} (https://github.com/ayyoubakbari/doi2bib; mailto:{args.email})"
    })

    bib_entries:  list[str] = []
    fallback_raw: list[str] = []
    failed:       list[str] = []
    used_keys:    set[str]  = set()

    bar = tqdm(dois, desc="  Fetching", unit="DOI", total=len(dois))
    for doi in bar:
        result, status = process_doi(doi, session, args.email, args.no_abstract)

        if result is None:
            failed.append(doi)
            bar.write(f"  {status}  {doi}")
        elif "_raw_bibtex" in result:
            fallback_raw.append(result["_raw_bibtex"])
            bar.write(f"  {status}  {doi}")
        else:
            bib_entries.append(build_bibtex(result, used_keys))

        time.sleep(args.delay)

    out = Path(args.output)
    all_entries = bib_entries + fallback_raw
    out.write_text("\n\n".join(all_entries) + "\n", encoding="utf-8")

    abstract_count = sum(1 for e in bib_entries if "abstract" in e)
    print(f"\n  {'─'*52}")
    print(f"  ✅  Written to     : {out}")
    print(f"  📄  Total entries  : {len(all_entries)}")
    print(f"  📝  With abstract  : {abstract_count} / {len(bib_entries)}")
    print(f"  ⚠️   Fallback only  : {len(fallback_raw)}")
    print(f"  ❌  Failed         : {len(failed)}")
    print(f"  {'─'*52}\n")

    if failed:
        fail_path = out.with_name(out.stem + "_failed_dois.txt")
        fail_path.write_text("\n".join(failed), encoding="utf-8")
        print(f"  Failed DOIs → {fail_path}")
        print(f"  Resolve manually at https://search.crossref.org\n")


if __name__ == "__main__":
    main()
