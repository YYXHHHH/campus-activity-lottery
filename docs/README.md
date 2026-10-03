# Documentation Index — Campus Activity Registration, Lottery & Check-in System

> **Documentation model**: organized by software development life-cycle phase, following the document types of GB/T 8567.
> **Version**: v1.0 | **Updated**: 2026-10-02
> **Format**: Markdown source only (lightweight); Word (`.docx`) versions are generated on demand via `scripts/md_to_docx.py` and gitignored.
> **Build**: `scripts/md_to_docx.py` (Markdown to Word) and `scripts/verify_docx.py` (structural check).
> **Language**: document bodies are written in Chinese; this index and the repository README are in English.

---

## 1. Directory layout

```
docs/
├─ README.md                    this index (English)
├─ README.zh-CN.md              Chinese index
├─ 01-project-plan/             development plan, quality assurance plan, configuration management plan
├─ 02-requirements/             requirements specification
├─ 03-design/                   high-level, detailed, database and interface design
├─ 04-implementation/           implementation notes
├─ 05-testing/                  test plan, test report
├─ 06-deployment/               deployment manual, user manual
├─ 07-acceptance/               acceptance report, project summary
└─ 99-archive/                  process log (historical)
```

## 2. Standard document map

| Phase | Standard document | Project document | File (.md) |
| --- | --- | --- | --- |
| Plan | Software development plan | Project development plan | 01-project-plan/project-development-plan |
| Plan | Software quality assurance plan (SQAP) | Software quality assurance plan | 01-project-plan/software-quality-assurance-plan |
| Plan | Software configuration management plan (SCMP) | Software configuration management plan | 01-project-plan/software-configuration-management-plan |
| Requirements | Software requirements specification (SRS) | Requirements specification | 02-requirements/requirements-specification |
| Design | High-level design (HLD) | High-level design | 03-design/high-level-design |
| Design | Detailed design (DLD) | Detailed design | 03-design/detailed-design |
| Design | Database design (DBD) | Database design | 03-design/database-design |
| Design | Interface design (IDD) | Interface design | 03-design/interface-design |
| Implementation | Coding / implementation notes | Implementation notes | 04-implementation/implementation-notes |
| Testing | Software test plan (STP) | Test plan | 05-testing/test-plan |
| Testing | Software test report (STR) | Test report | 05-testing/test-report |
| Deployment | Deployment and operations manual | Deployment manual | 06-deployment/deployment-manual |
| Deployment | User manual | User manual | 06-deployment/user-manual |
| Acceptance | Acceptance test report | Acceptance report | 07-acceptance/acceptance-report |
| Closure | Project development summary report | Project summary | 07-acceptance/project-summary |

> 15 documents covering planning, requirements, design, implementation, testing, deployment, acceptance and closure.

## 3. Reading order

1. **Understand the project**: project development plan -> requirements specification
2. **Understand the solution**: high-level design -> detailed design -> database design -> interface design
3. **Check the implementation**: implementation notes
4. **Verify quality**: software quality assurance plan -> test plan -> test report -> acceptance report
5. **Deploy and use**: deployment manual -> user manual
6. **Review and close**: project summary

## 4. Sources and rules

- **Requirements specification** - from the Requirements and Design Document, sections 1-6, 12.2, 15.1-15.2.
- **High-level design** - from the Development Document, sections 1-2, and the Requirements and Design Document, sections 7 and 10.
- **Detailed design** - from the Development Document, sections 3, 5-7 and appendices A/B.
- **Database design** - from the Development Document, section 4, and the Requirements and Design Document, sections 8.3 and 8.5.
- **Interface design** - from the interface list produced during implementation (renamed to the standard document name).
- **Test plan** - from the Development Document, section 10 and appendix D, and the Requirements and Design Document, sections 12.1 and 12.3.
- **Acceptance report** - from the manual acceptance checklist produced during implementation (renamed to the standard document name).
- **Plans (development / quality / configuration)** - from the Requirements and Design Document, sections 6, 13 and 14; the Development Document, sections 6, 7, 9 and 10; and actual engineering practice.
- **Project summary** - from the implementation notes (section 7), the test report, the acceptance report and the process log.

> Section numbers in the derived documents follow the source documents, so they can be cross-referenced with the originals.

## 5. Archive and build

- `99-archive/`: the development-day process log, kept for traceability. Reference only; not a formal deliverable.
- `scripts/`: documentation build and check scripts, kept outside `docs/` so the documentation folder contains documents only.
- Generated `.docx` files are gitignored to keep the repository lightweight.

## 6. Maintenance

- Each document describes only its own phase; cross-phase information is referenced, not copied.
- Markdown is the single source of truth; run `scripts/md_to_docx.py` to generate Word versions when needed.
- The Word table of contents is a field: Word / WPS updates it automatically (`updateFields`) or with F9.
- Update the requirements specification first on any change, then synchronize the design, database, interface and test documents.
- The archive keeps only the historical process log for traceability.

---
(End of document)
