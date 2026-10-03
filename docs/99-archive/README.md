# Archive

> Historical process material kept for traceability. **Reference only** - not a formal deliverable.
> The formal documents live in the phase folders above; see the [index](../README.md).

## Contents

| File | Description |
| --- | --- |
| `process-log-2026-10-01.md` | Development-day process log (authoring, implementation, verification, defect fixes). |

## Why the archive is minimal

To keep the repository lightweight, the pre-reorganization material below was removed - its content is already folded into the phase documents, and the Word originals can be regenerated:

- `source-drafts/` - the Development Document Markdown drafts (`devdoc_part0..5`), now distributed into `03-design/` and `05-testing/`.
- `requirements-design-extracted.txt` - text extracted from the original combined document, now distributed into `02-requirements/` and `03-design/`.
- `original-combined-docs/` - the two original combined Word documents (superseded).

## Regenerating Word versions

The documentation is Markdown-only by default. To produce `.docx` deliverables on demand:

```bash
python scripts/md_to_docx.py
python scripts/verify_docx.py
```

Generated `.docx` files are gitignored.

---
(End of note)
