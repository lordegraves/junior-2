# Junior 1.x → Junior 2.0 parity gate

Junior 2.0 may be packaged for user acceptance testing only when every row below
is complete and covered by automated tests. Native presentation may differ from
the 1.x web interface; behavior and durable data must remain equivalent.

| Area | 1.x behavior | 2.0 status |
|---|---|---|
| Profile | RC6 overview cards, structured preferences, résumé, job fit, role discovery, managed profiles, transfer | Complete |
| Companies | Full source settings, filtering, enable/disable | Complete |
| Company import | Read complete 1.x YAML catalog | Complete |
| Database import | Read-only import of 1.x lifecycle database | Complete |
| Tracker | Add, edit, remove, dates, status, outcome, notes | Complete |
| Greenhouse | Collection and persistence | Complete |
| Lever | Collection and persistence | Complete |
| Ashby | Collection and persistence | Complete |
| Workday | Collection and persistence | Complete |
| SmartRecruiters | Collection and persistence | Complete |
| USAJobs | Collection and persistence | Complete |
| Phenom | Collection and persistence | Complete |
| Rippling | Collection and persistence | Complete |
| Oracle HCM | Collection and persistence | Complete |
| JobSync | Collection and persistence | Complete |
| ADP | Collection and persistence | Complete |
| Dayforce | Collection and persistence | Complete |
| Jibe | Collection and persistence | Complete |
| HTML | Collection and persistence | Complete |
| WEKA | Collection and persistence | Complete |
| SelectMinds | Collection and persistence | Complete |
| Activate | Collection and persistence | Complete |
| iCIMS | Collection and persistence | Complete |
| SchoolSpring | Collection and persistence | Complete |
| Remaining collectors | All Junior 1.x collectors migrated | Complete |
| Compensation | Parse and compare annual ranges to profile floor | Complete |
| Resume matching | Profile evidence and known-gap classification | Complete |
| Scoring | Keyword, title, location, top-match and review policy | Complete |
| LLM interpretation | Managed local runtime and evidence validation | Complete |
| Scan evaluation | Persist interpretation and deterministic decision per job | Complete |
| Recommendations | Top match, review, omit and auditable reasons | Complete |
| History | Import, match, summarize, archive, tracker synchronization and RC6 controls/cards | Complete |
| Reports | Current scan, saved reports, HTML/Markdown views and RC6 audit cards | Complete |
| Email | Preview, providers, authenticated connection test, secret references, and configured delivery | Complete |
| Scheduling | Native user-level schedules and headless installed-app scans on all three platforms | Complete |
| Native pages | Complete RC6 card, field, dropdown, filter, action, and help parity | Complete — tracked in `NATIVE_UI_AUDIT.md` |
| Packaging | Clean macOS, Windows, Linux installs after the complete native UI gate | Platform smoke tests pending |

The gate is functional parity, not identical source layout or an identical raw
test count. Each migrated behavior must have equivalent or stronger regression
coverage, and the final suite must include a clean-install end-to-end scan.
