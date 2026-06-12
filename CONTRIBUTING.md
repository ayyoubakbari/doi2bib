# Contributing to doi2bib

Thank you for considering a contribution! doi2bib is an open-science tool and
all improvements are welcome — whether it's a bug report, a new API source,
better documentation, or a translation.

---

## How to contribute

### Reporting a bug

1. Check [existing issues](https://github.com/akbari-moghanjoughi/doi2bib/issues)
   to see if it is already reported.
2. Open a new issue with:
   - A short, descriptive title
   - The command you ran and the full error output
   - Your Python version (`python --version`) and OS
   - A sample DOI that triggers the problem (if applicable)

### Suggesting a feature

Open an issue with the label `enhancement` and describe:
- What problem it solves for researchers
- A proposed interface or behaviour

### Submitting a pull request

1. Fork the repository and create a feature branch:
   ```bash
   git checkout -b feature/my-improvement
   ```
2. Keep changes focused — one feature or fix per PR.
3. Follow the existing code style (PEP 8, type hints where practical).
4. Test your changes against a small CSV of DOIs before submitting.
5. Update `README.md` and the docstring in `doi2bib.py` if behaviour changes.
6. Open the PR against the `main` branch with a clear description.

---

## Ideas for future contributions

- Support for additional abstract sources (PubMed API, OpenAlex, CORE)
- Output formats beyond BibTeX: RIS, CSL-JSON, EndNote XML
- A `--field-filter` flag to select which BibTeX fields to include
- Async/concurrent requests for faster batch processing
- A minimal web UI or Streamlit app
- Support for ISBN lookup (books)

---

## Code of conduct

Be respectful, constructive, and collegial — this is a tool built by and for
the research community.
