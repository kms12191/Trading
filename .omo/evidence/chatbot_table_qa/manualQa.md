# Manual QA: chatbot news/disclosure table rendering

Surface: frontend source/runtime build

Verdict: REVISE for full UI completion; PASS for semantic table source structure.

## surfaceEvidence

| scenario id | criterion reference | surface | exact invocation | verdict | artifactRefs |
|---|---|---|---|---|---|
| S1 | News results render as table | Source code: `frontend/src/features/chatbot/ChatbotWidget.jsx` | `Select-String -Path frontend/src/features/chatbot/ChatbotWidget.jsx -Pattern '<table|<thead|<tbody|<th|overflow-x-auto|hidden space-y-3|NewsResults|DisclosureResults|buildNewsPresentation|buildDisclosurePresentation' -Context 0,2` | PASS | A2 |
| S2 | Disclosure results render as table | Source code: `frontend/src/features/chatbot/ChatbotWidget.jsx` | same as S1 | PASS | A2 |
| S3 | Presentation data supports table columns | Node test runner | `node --test frontend/src/features/chatbot/chatbotNewsPresentation.test.mjs frontend/src/features/chatbot/chatbotDisclosurePresentation.test.mjs` | PASS | A3 |
| S4 | Chatbot feature tests remain green | Node test runner | `node --test frontend/src/features/chatbot/*.test.mjs` | PASS | A5 |
| S5 | Current frontend bundle compiles changed JSX | Vite build | `npm.cmd run build --prefix frontend` with `$LASTEXITCODE` captured | PASS | A4 |
| S6 | Browser screenshot confirms visible table layout | Browser UI | Not executed in this QA turn | FAIL | A6 |

## adversarialCases

| scenario id | criterion reference | adversarial class | expected behavior | verdict | artifactRefs |
|---|---|---|---|---|---|
| A1 | News/disclosure should use real table semantics, not card-only layout | Static markup regression | `<table>`, `<thead>`, `<tbody>`, row-mapped `<tr>` and `<th>` are present for both result types | PASS | A2 |
| A2 | Mobile/narrow viewport should not clip table columns | Responsive overflow | Table is wrapped in `overflow-x-auto` and has `min-w` | PASS by source; visual not proven | A2 |
| A3 | Date field for DART receipt date | Data normalization edge | `20260706` becomes `2026-07-06` | PASS | A3 |
| A4 | Stale card renderer should not be visible | Hidden duplicate markup | Old card markup is hidden from visual layout | REVISE: hidden dead markup remains in source | A1, A2 |
| A5 | Actual Korean/CJK visual rendering | CJK visual fidelity | Korean headers/content render without mojibake, clipping, or orphaned wrapping | FAIL: no browser screenshot captured; PowerShell line dump showed mojibake, but git diff/logs indicate this may be terminal encoding, not necessarily app rendering | A2, A6 |

## artifactRefs

| id | kind | description | path |
|---|---|---|---|
| A1 | diff | Current changed UI/presentation/test diff | `.omo/evidence/chatbot_table_qa/chatbot-table-diff.patch` |
| A2 | source audit | Extracted table-related source snippets | `.omo/evidence/chatbot_table_qa/semantic-table-source-audit.txt` |
| A3 | test log | News/disclosure presentation tests, 12 passing | `.omo/evidence/chatbot_table_qa/node-presentation-tests.txt` |
| A4 | build log | Vite production build, `EXIT_CODE=0` | `.omo/evidence/chatbot_table_qa/frontend-build-exitcode.txt` |
| A5 | test log | All chatbot feature `.test.mjs`, 53 passing | `.omo/evidence/chatbot_table_qa/node-chatbot-feature-tests.txt` |
| A6 | blocker note | Browser screenshot/e2e UI capture was not produced in this QA turn | this report |

## findings

- PASS: `NewsResults` now renders a `<section>` containing `overflow-x-auto` and a semantic `<table>` with `<thead>`, `<tbody>`, `<th>` columns and item-mapped `<tr>` rows.
- PASS: `DisclosureResults` mirrors the same table pattern with DART-specific columns.
- PASS: Combined routing into `ChatMessage` still renders news and disclosure result sections independently when their presentation items are non-empty.
- PASS: presentation tests and chatbot feature tests pass, and Vite production build exits with code 0.
- REVISE: the old card layouts remain in `ChatbotWidget.jsx` under `className="hidden space-y-3"`. This is not a visual blocker, but it is dead duplicate JSX and should be removed or intentionally retained behind a named fallback.
- FAIL for visual completion: no browser screenshot or DOM-driven UI test was captured, so visible table layout, CJK wrapping, and actual rendered Korean labels are not fully proven.
