# Junior RC6 → Junior 2.0 native UI audit

This inventory is the packaging gate for user-visible parity. `Complete` means the
control is native, wired to durable behavior, and covered by an automated test.

| Surface | RC6 controls and states | Native status | Remaining gap |
|---|---|---|---|
| Home | workflow cards, latest-scan cards, attention queue, filtered review links | Complete | — |
| Profile overview | five status cards, scan summary, structured preferences, company count | Complete | — |
| Résumé | import/replace, confirmation, active-file state, readable preview | Complete | — |
| Job fit | four categories, individual terms, explanations, add, move, remove, ignored state | Complete | — |
| Role discovery | generate, evidence, source context, three explicit decisions | Complete | — |
| Managed profiles | create, select/activate, delete, import, export | Complete | — |
| Companies | summary cards, search, status/source filters, source health, add/edit/toggle/test, import/export | Complete | — |
| Scan | full/selected scans, company selection, most-recent receipt, warnings | Complete | — |
| Review jobs | latest-scan inbox, saved/passed decisions, summary/filter/sort, decision actions, evidence/workbench access | Complete | — |
| Applications | summary cards, search, status/outcome filters, sort, add/edit, bulk outcome/history | Complete | — |
| History | summary cards, search, decision/outcome filters, sort, edit/delete/restore | Complete | — |
| Reports & audit | current outputs, retained runs, view/download, report generation, email | Complete | — |
| Settings | diagnostics, admin unlock, applied retention, privacy-safe troubleshooting bundle, email, USAJobs, schedule, source health, backup | Complete | — |
| Help/About | operating guidance, privacy, support, version/runtime information, local data action | Complete | — |
| First run | profile, résumé, job fit, companies, and first-scan guided progression | Complete | — |

## Release verification

- [x] Every `In progress` row above is closed with regression coverage.
- [x] Full profile → scan → evaluation → review → tracking → history → report test (`test_clean_install_full_scan_lifecycle`).
- [x] Read-only RC6 database/company migration and profile transfer tests using representative data.
- [x] Clean-data-directory launch and first-run routing tests.
- [x] Managed local LLM startup/model availability tests without a manually started Ollama.
- [ ] macOS signed application and drag-to-install disk image smoke test.
- [ ] Windows installer install/launch/uninstall smoke test on Windows.
- [ ] Linux package install/launch/uninstall smoke test on its target distribution.
