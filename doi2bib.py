"""
doi2bib — Batch DOI to BibTeX Converter with Abstracts
=======================================================
Converts a CSV or Excel file of 500+ DOIs into a fully populated .bib file,
including abstracts, for direct import into Zotero, Mendeley, JabRef, or Overleaf.

Author      : A. Akbari-Moghanjoughi
Affiliation : Universitat Politècnica de Catalunya (UPC)
License     : Creative Commons Attribution 4.0 International (CC BY 4.0)
Repository  : https://github.com/akbari-moghanjoughi/doi2bib

Metadata pipeline (per DOI):
  1. CrossRef API        — structured fields (authors, title, journal, year, volume, pages, ...)
  2. Semantic Scholar    — abstract (~70% coverage across all disciplines)
  3. Europe PMC          — abstract fallback (strong for biomedical / life sciences)
  4. doi.org BibTeX      — last-resort fallback for any remaining DOIs

Usage:
    pip install pandas openpyxl requests tqdm
    python doi2bib.py --input refs.xlsx --doi_column "DOI" --output references.bib --email you@institution.edu

Arguments:
    --input        Path to CSV or Excel file (.csv / .xlsx / .xls)
    --doi_column   Column name that contains the DOIs  (default: "DOI")
    --output       Output .bib filename                (default: references.bib)
    --email        Your email for CrossRef Polite Pool (strongly recommended)
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
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

    class tqdm:
        """Minimal fallback progress indicator when tqdm is unavailable."""
        def __init__(self, iterable, **kw):
            self.it = iterable
            self.total = kw.get("total", "?")
            self.n = 0
        def __iter__(self):
            for x in self.it:
                self.n += 1
                print(f"  [{self.n}/{self.total}]", end="\r", flush=True)
                yield x
            print()
        def write(self, s):
            print(s)


# ── Constants ─────────────────────────────────────────────────────────────────

__version__ = "1.0.0"
__author__  = "A. Akbari-Moghanjoughi"

CROSSREF_URL   = "https://api.crossref.org/works/{doi}"
S2_URL         = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
EPMC_URL       = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DOI_ORG_URL    = "https://doi.org/{doi}"

CROSSREF_TYPE_MAP = {
    "journal-article":    "article",
    "proceedings-article":"inproceedings",
    "book-chapter":       "incollection",
    "book":               "book",
    "dissertation":       "phdthesis",
    "report":             "techreport",
    "posted-content":     "misc",
    "dataset":            "misc",
}


# ── Utility helpers ───────────────────────────────────────────────────────────

def clean_doi(raw: str) -> str:
    """Normalise a DOI: strip URL prefixes, whitespace, and 'doi:' labels."""
    doi = str(raw).strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.strip()


def clean_html(text: str) -> str:
    """Strip HTML tags and decode entities (common in CrossRef abstracts)."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def escape_bibtex(text: str) -> str:
    """Escape characters that are special in BibTeX field values."""
    if not text:
        return ""
    for old, new in [("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_")]:
        text = text.replace(old, new)
    return text


def make_citekey(authors: list, year: str, title: str) -> str:
    """
    Build a human-readable cite key: <FirstAuthorLastName><Year><FirstLongWord>
    Example: Jumper2021Highly
    """
    last = "Unknown"
    if authors:
        # authors stored as "Family, Given" — take the family name
        last = re.sub(r"[^a-zA-Z]", "", authors[0].split(",")[0].split()[-1])
    yr     = str(year) if year else "0000"
    words  = re.findall(r"[A-Za-z]{4,}", title or "")
    suffix = words[0].capitalize() if words else "Ref"
    return f"{last}{yr}{suffix}"


# ── API fetch functions ───────────────────────────────────────────────────────

def _get_year(msg: dict) -> str | None:
    for field in ("published", "published-print", "published-online", "issued"):
        parts = msg.get(field, {}).get("date-parts", [[]])
        if parts and parts[0]:
            return str(parts[0][0])
    return None


def fetch_crossref(doi: str, session: requests.Session, email: str = "") -> dict | None:
    """
    Query the CrossRef REST API for full structured metadata.
    Registering a polite-pool email (--email) unlocks higher rate limits.
    https://api.crossref.org
    """
    params = {"mailto": email} if email else {}
    try:
        r = session.get(CROSSREF_URL.format(doi=doi), params=params, timeout=15)
        if r.status_code != 200:
            return None
        msg = r.json().get("message", {})
    except Exception:
        return None

    entry_type = CROSSREF_TYPE_MAP.get(msg.get("type", ""), "misc")

    # Authors
    authors = []
    for a in msg.get("author", []):
        family = a.get("family", "")
        given  = a.get("given", "")
        if family:
            authors.append(f"{family}, {given}".strip(", "))
        elif given:
            authors.append(given)

    # Container (journal / book title)
    containers    = msg.get("container-title", [])
    short_ct      = msg.get("short-container-title", [])
    pages         = msg.get("page", "").replace("-", "--")
    event         = msg.get("event") or {}

    return {
        "entry_type":   entry_type,
        "doi":          doi,
        "title":        (msg.get("title") or [""])[0],
        "authors":      authors,
        "year":         _get_year(msg),
        "journal":      containers[0]  if containers else "",
        "journal_abbr": short_ct[0]    if short_ct   else "",
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


def fetch_s2_abstract(doi: str, session: requests.Session) -> str:
    """
    Semantic Scholar Graph API — abstracts for ~70 % of papers, all disciplines.
    No API key required for reasonable usage.
    https://api.semanticscholar.org
    """
    try:
        r = session.get(
            S2_URL.format(doi=doi),
            params={"fields": "abstract"},
            timeout=12,
        )
        if r.status_code == 200:
            return clean_html(r.json().get("abstract") or "")
    except Exception:
        pass
    return ""


def fetch_epmc_abstract(doi: str, session: requests.Session) -> str:
    """
    Europe PubMed Central REST API — excellent coverage for biomedical /
    life-science literature indexed in PubMed.
    https://europepmc.org/RestfulWebService
    """
    try:
        r = session.get(
            EPMC_URL,
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


def fetch_doi_org_bibtex(doi: str, session: requests.Session) -> str:
    """
    doi.org content-negotiation fallback — returns raw BibTeX when all
    structured APIs fail. No abstract, but better than nothing.
    """
    try:
        r = session.get(
            DOI_ORG_URL.format(doi=doi),
            headers={"Accept": "application/x-bibtex"},
            timeout=15,
        )
        if r.status_code == 200 and r.text.strip().startswith("@"):
            return r.text.strip()
    except Exception:
        pass
    return ""


# ── BibTeX serialiser ─────────────────────────────────────────────────────────

def build_bibtex(meta: dict, used_keys: set) -> str:
    """
    Serialise a metadata dict to a BibTeX entry string.
    Guarantees unique cite keys within the output file.
    """
    entry_type = meta.get("entry_type", "misc")
    authors    = meta.get("authors", [])

    # Unique cite key
    key = base = make_citekey(authors, meta.get("year"), meta.get("title", ""))
    counter = 2
    while key in used_keys:
        key = f"{base}{chr(96 + counter)}"   # Smith2021a, Smith2021b, …
        counter += 1
    used_keys.add(key)

    fields: dict[str, str] = {}

    if authors:
        fields["author"] = " and ".join(authors)

    title = meta.get("title", "")
    if title:
        # Extra braces preserve capitalisation in LaTeX
        fields["title"] = "{" + escape_bibtex(title) + "}"

    for f in ("year", "volume", "number", "pages", "publisher",
              "issn", "isbn", "url", "keywords"):
        v = meta.get(f, "")
        if v:
            fields[f] = escape_bibtex(str(v))

    if meta.get("doi"):
        fields["doi"] = meta["doi"]

    # Journal vs booktitle
    if entry_type == "article" and meta.get("journal"):
        fields["journal"] = escape_bibtex(meta["journal"])
    elif meta.get("booktitle"):
        fields["booktitle"] = escape_bibtex(meta["booktitle"])
    elif meta.get("journal"):
        fields["journal"] = escape_bibtex(meta["journal"])

    # Abstract last (longest field)
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
    """
    Full fetch pipeline for a single DOI.
    Returns (metadata_dict_or_None, human_readable_status).
    """
    meta = fetch_crossref(doi, session, email)

    if meta:
        if not skip_abstract and not meta.get("abstract"):
            meta["abstract"] = fetch_s2_abstract(doi, session)
        if not skip_abstract and not meta.get("abstract"):
            meta["abstract"] = fetch_epmc_abstract(doi, session)

        tag = "[+abstract]" if meta.get("abstract") else "[no abstract]"
        return meta, f"✅  OK {tag}"

    # Fallback: raw BibTeX from doi.org
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
    parser.add_argument("--input",       required=True,              help="CSV or Excel file with DOIs")
    parser.add_argument("--doi_column",  default="DOI",              help="Column name containing DOIs (default: DOI)")
    parser.add_argument("--output",      default="references.bib",   help="Output .bib file (default: references.bib)")
    parser.add_argument("--email",       default="",                 help="Email for CrossRef Polite Pool (recommended)")
    parser.add_argument("--delay",       type=float, default=0.3,    help="Delay between requests in seconds (default: 0.3)")
    parser.add_argument("--no-abstract", action="store_true",        help="Skip abstract fetching (faster)")
    parser.add_argument("--version",     action="version", version=f"doi2bib {__version__}")
    args = parser.parse_args()

    print(f"\n  doi2bib v{__version__} — by {__author__}, UPC")
    print(f"  {'─'*50}")
    print(f"  Input  : {args.input}")
    print(f"  Output : {args.output}")
    if args.email:
        print(f"  Email  : {args.email} (CrossRef Polite Pool active)")
    print()

    dois = load_dois(args.input, args.doi_column)
    print(f"  ✅  {len(dois)} DOIs loaded\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": f"doi2bib/{__version__} (https://github.com/akbari-moghanjoughi/doi2bib)"
    })

    bib_entries: list[str] = []
    fallback_raw: list[str] = []
    failed: list[str] = []
    used_keys: set[str] = set()

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

    # Write .bib
    out = Path(args.output)
    all_entries = bib_entries + fallback_raw
    out.write_text("\n\n".join(all_entries) + "\n", encoding="utf-8")

    # Summary
    abstract_count = sum(1 for e in bib_entries if "abstract" in e)
    print(f"\n  {'─'*50}")
    print(f"  ✅  Written to     : {out}")
    print(f"  📄  Total entries  : {len(all_entries)}")
    print(f"  📝  With abstract  : {abstract_count} / {len(bib_entries)}")
    print(f"  ⚠️   Fallback only  : {len(fallback_raw)}")
    print(f"  ❌  Failed         : {len(failed)}")
    print(f"  {'─'*50}\n")

    if failed:
        fail_path = out.with_name(out.stem + "_failed_dois.txt")
        fail_path.write_text("\n".join(failed), encoding="utf-8")
        print(f"  Failed DOIs saved to : {fail_path}")
        print(f"  Resolve manually at  : https://search.crossref.org\n")


if __name__ == "__main__":
    main()
