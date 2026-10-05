# RC2 Candidate Report

Scope: repair of RC1_REVIEW.md P0/P1 items. `RC1_REVIEW.md` is unchanged (audit record).
Detail: `docs/RC1_REPAIR_LOG.md`. Evidence: `reviews/evidence-rc2/`.

## 1. Fixed
| Item | Fix | Verification |
|---|---|---|
| P0 publishing boundary | 5 classes in `boundary.json`; real issues default to git-ignored `workspace/issues/`; `.gitignore` allow-list ⇄ `boundary.json` identity test; pre-commit hook; CI workflow; P00 preflight; explicit override flag/env | `boundary` tests |
| P1-A asset path / raw HTML / sandbox | `encodeURIComponent` + NFC names, traversal rejected; Markdown HTML escaped, images dropped, links as text; CSP; measurement browser network-blocked; theme CSS cannot `@import`/remote `url()`; Chromium sandbox on by default (off only via `PS_NO_SANDBOX=1` or announced root-in-remote case) | `security` tests; adversarial #21, #22 |
| P1-B page-relative layout | Physical / page-relative / typography-derived tokens; `--type-scale`; no mm/pt literals in layout CSS or component JS (tested) | `layout-tokens`, `responsive` tests |
| P1-C capacity / metrics | Two-pass probe measures real text frames and contents capacity; density contracts; `text_occupancy`, `content_extent`, orphan lines; `fit_fill` removed; metrics classed MEASUREMENT / HEURISTIC / REVIEW_REQUIRED | `text`, `density`, `metrics` tests; adversarial #1, #9 |
| P1-D tests / preflight | New P29–P31 automated/heuristic checks; P32–P34 manual items; items typed AUTOMATED / HEURISTIC / MANUAL; no "ready" wording; 28 mutations | see §2 |
| P1-E critic protection | Reviews never rewritten; `--reset` refuses over authored work, `--force` archives; reviews bound to `source_hash`, stale ones do not gate | `critic-protection` tests |
| P1-F sample layout defects | Fixed at theme/component/capacity level (tone-aware chrome, gutters, colophon dedupe, `auto-phrase`, `text-wrap: pretty`, `.narrow`); no per-sample CSS patches | `samples` tests, page review |

No thresholds loosened; no checks removed.

## 2. Tests
- Unit/integration: **98 / 98 pass** (~116 s).
- Mutation (`scripts/mutation.mjs`): **28 / 28 killed** across runs (RC1 baseline: 6 of 14). M28 first survived, then was killed after a multi-column test was added.
- Adversarial (24 cases; harness unchanged except `EVIDENCE_DIR`): FIXED #1, #9, #15, #21, #22; unchanged OK for the rest; open: #6, #7, #14 (partial), #18 (partial), #23. Table in repair log.
- TEST ISSUE 01 (A5/16p) and 02 (B5/24p): `all` → preflight **WARNING**; PASS 23 / WARNING 2 (P14, P25; both listed with reasons in `expected-warnings.yaml`) / FAIL 0 / MANUAL CHECK 7.

## 3. Known limitations (not fixed)
- P2: extreme aspect or crop at high resolution not flagged; article type vs layout mismatch not detected; large theme font sizes can still clip (caught by P19); `scripts/lib`/toolchain not hashed for staleness; no text/photo collision detection; no automatic two-page contents.
- Visual identity of the sample (RC1 F-009) not addressed.
- Out of scope: vertical writing, CMYK, PDF/X, EPUB/web, GUI/CMS.
- Sandbox is disabled in this root cloud container (announced on stderr); sandbox-on path was not exercised here.

## 4. Remaining manual checks
ICC/colour profile (P32), overprint/trapping/TAC (P33), printer compatibility (P34); proofreading, rights, and visual review of every page. Preflight does not certify commercial print readiness.

## 5. Independent review
Independent re-review of RC2 (P1-9) has **not** been performed by the repairing session and is required. This report makes no acceptance decision.

## Judgement
**READY FOR INDEPENDENT REVIEW**
