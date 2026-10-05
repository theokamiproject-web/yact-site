# RC1 Repair Log

Base: `3f474c91c1978f3f1c1da15d6cbc90c0beb61546` (RC1 review frozen; `reviews/RC1_REVIEW.md` sha256 `edd643e5…3f06` is **not modified**).
Order of work (fixed by the repair brief): P0 → P1-A → P1-B → P1-C → P1-D → P1-E → P1-F.

## Freeze record
- branch `claude/bold-shannon-746w8g`, clean tree, HEAD above, 25/25 tests pass, `package.json` sha256 `8f682bc7…`, `package-lock.json` sha256 `d5b83014…`.
- RC1 reproduction tools: `reviews/tools/*` (kept as-is; used again for the RC2 comparison).

## Review item → root cause map (before any fix)

| Review ID | Sev | Symptom (RC1) | Root cause (verified in code) | Planned fix |
|---|---|---|---|---|
| P0-1 | P0 | real issues can be committed to the Pages-served repo | no notion of private vs publishable data; `issues/*` is tracked by default; `new-issue` writes into the public tree; nothing checks | data classification + `workspace/` (git-ignored) as default home for real issues + allow-list for examples + boundary check in validate/build/all/preflight + pre-commit hook |
| P1-1 | P1 | images with Japanese/space/`#` names break | `src="images/${esc(file)}"` – HTML-escaped but never URL-encoded | encode via standard `encodeURIComponent`; NFC-normalise keys; reject path traversal |
| P1-2 | P1 | raw HTML in manuscripts executes / restyles | `marked.parseInline` passes HTML through; Chromium launched with unconditional `--no-sandbox` | marked renderer that escapes HTML and drops images/unsafe links; CSP meta; network-blocked metrics browser; sandbox on by default |
| P1-3 | P1 | A5-only layouts (41 mm literals), B5 pages 60–95 % empty | component CSS and capacity code hard-code A5 millimetres; margins/baseline/font duplicated in CSS and JS | page-relative design tokens (single source = CSS), capacities derived from probed tokens |
| P1-4 | P1 | TOC silently loses items | contents has no capacity contract | `capacity` contract + `CONTENTS_OVERFLOW` validate error |
| P1-5 | P1 | fit_fill misses half-empty pages, quiet-page rewards sparse pages, body_pt wrong | single global threshold; metric conflates "frame occupancy" with "page looks finished" | split into MEASUREMENT / HEURISTIC / REVIEW_REQUIRED; component density contracts; declared intent |
| P1-6 | P1 | 8 of 14 injected bugs survive | preflight checks had no regression tests | tests that tamper artifacts and mutation runner |
| P1-7 | P1 | `critic --reset` overwrites finished reviews; AUTO blocks dirty tracked files | destructive write without check; generated text inside authored files | refuse without `--force`, archive first; move generated text out of reviews; bind reviews to a source hash |
| P1-8 | P1 | orphan lines, quote breaks, text/image contact, unreadable chrome on images, blank bottoms | CSS/component causes (see F-ids) | fixed in theme/components, not in sample CSS |
| P1-9 | P1 | independent re-review needed | process item | **not done here**: listed in RC2_CANDIDATE as required |

---

# Repairs

Commits (in order): `P0 boundary` → `P1-A input safety` → `P1-B page-relative layout` → `P1-C/D metrics + preflight + tests` → `P1-E critic protection` → `P1-F samples/typography/docs`. Every commit ran its own tests; the full suite runs at the end.

## P0-1 — Publishing boundary
- **Severity** P0
- **Root cause** There was no concept of private vs publishable data. `issues/*` was tracked by default, `publication:new` wrote into the public tree, nothing checked, and the only protection was prose.
- **Fix** (a mechanism, not a note)
  - `boundary.json`: five classes (`PRIVATE_SOURCE`, `BUILD_TEMP`, `GENERATED_PRIVATE`, `PUBLISHABLE`, `SYSTEM`); `issues/` is private except the allow-listed examples; `workspace/` is private.
  - `publication:new` creates `workspace/issues/<id>/` (git-ignored). `.gitignore` allow-list ⇄ `boundary.json` (test enforces identity).
  - `validate`, `build`, `all`, `preview` and preflight (P00) **FAIL** when a private issue is tracked by Git or sits in the work tree without being ignored. The override is an explicit, recorded flag (`--i-understand-private-source-may-be-published` / env var) and leaves a WARNING in preflight.
  - `publication:boundary`, a `pre-commit` hook (installed by `npm install` via `prepare`) and a CI workflow reject tracked/staged private or generated files.
- **Files** `boundary.json`, `scripts/lib/boundary.mjs`, `scripts/boundary-check.mjs`, `scripts/lib/paths.mjs`, `scripts/new-issue.mjs`, `scripts/{validate,build,all,preview}.mjs`, `scripts/lib/{build,preflight}.mjs`, `.gitignore`, `.githooks/pre-commit`, `.github/workflows/publishing-boundary.yml`, `workspace/README.md`, `package.json`
- **Tests** `tests/boundary.test.mjs` (12): classification table, allow-list identity, nothing tracked in this repo, not-ignored → FAIL, ignored → ok, force-tracked → FAIL, staged detection, override reported, example/outside-tree ok, CLI exit codes, hook/CI present, `new-issue` lands in ignored `workspace/`, validate/build/all refuse + override + ignore fixes it.
- **Verification** mutation M17 (not-ignored check removed) is killed.
- **Remaining risk** A user can still create a *new* private issue directly under `issues/` — it is git-ignored (allow-list) so it cannot be committed, but is not blocked from being created. Real issues should live in `workspace/` or outside the repository (`PS_ISSUES_DIR`). Pages settings of the GitHub repository were not inspected (no API access).

## P1-1 — Asset paths (Japanese / space / `#` / parentheses)
- **Root cause** `src="images/${esc(file)}"`: HTML-escaped, never URL-encoded.
- **Fix** `encodeURIComponent` (standard API; no hand-written replace) in the single image helper; file names normalised to NFC (macOS stores NFD); references containing separators, `..` or a leading dot are validation errors (`ASSET_PATH_INVALID`).
- **Files** `layouts/_shared.mjs`, `scripts/lib/{load,inputs,validate-model}.mjs`
- **Tests** `tests/security.test.mjs`: `舞台 写真 01.jpg`, `舞台#01.jpg`, `日本海・秋田.jpg`, `photo (1).jpg` through build, render and the PDF (DOM decode, percent-encoding in HTML, images embedded in the PDF, P18 PASS); NFD names; traversal rejected.
- **Verification** RC1 adversarial case 21 now builds with P18 PASS. Mutation M19 killed.
- **Remaining risk** None known for paths; file *names* are still taken from the file system as-is.

## P1-2 — Raw HTML in manuscripts / Chromium
- **Root cause** `marked.parseInline` passes HTML through; Chromium was launched with an unconditional `--no-sandbox`, and Vivliostyle CLI disables the sandbox unless told otherwise.
- **Fix** A `Marked` instance whose renderer escapes HTML (shown as text), drops images, prints links as text; allowed output elements are an explicit list (`p h3 strong em del code br ul ol li blockquote`). CSP meta in the book (`script-src 'none'`, no frames/objects, `img-src 'self'`). The measurement browser is network-blocked (`safePage`). Theme CSS may not `@import` or use remote/scheme `url()`. Sandbox policy: **on by default**; off only with `PS_NO_SANDBOX=1`, or automatically inside the managed remote container *as root* (announced on stderr). Vivliostyle is given `--sandbox` unless that policy applies.
- **Files** `scripts/lib/{text,browser,compose,build,metrics,render,validate-model}.mjs`, `layouts/_shared.mjs`
- **Tests** `tests/security.test.mjs`: script/style/iframe/object/embed/`on*=`/`javascript:`/remote-image manuscript → no such tag in the book, text visible, **PDF still 16 pages** (RC1 case 22 produced a 1-page PDF); allowed-element list equals what the renderer can emit; external CSS rejected; sandbox policy truth table; network unreachable from the measurement browser.
- **Verification** Mutations M18 (HTML unescaped), M20 (sandbox default off), M21 (CSS check removed) killed.
- **Remaining risk** The remote container still runs Chromium without its sandbox (documented, announced, sources sanitised). `preview` serves the web build locally. Theme CSS from `themes/` is trusted code.

## P1-3 — Page-relative layout (A5-only → any page size)
- **Root cause** 41 millimetre literals in component CSS (+ literals inside component JS), margins/font size/baseline duplicated in CSS and in the JS capacity code.
- **Fix** Tokens split into PHYSICAL / PAGE-RELATIVE / TYPOGRAPHY-DERIVED (`themes/base/tokens.css`, `--type-scale` generated from `issue.yaml`). All layouts use tokens. **Body capacity is no longer computed from constants**: pass A composes the book without body text, Chromium measures every text frame (width, height, columns, gap, font size, leading), pass B allocates text into the measured frames. Theme/margin/font overrides therefore flow through automatically.
- **Files** `themes/base/*.css`, `layouts/*/style.css`, `layouts/*/index.mjs`, `scripts/lib/{layout-probe,web,compose,build,inputs,text,theme,metrics}.mjs`
- **Tests** `tests/layout-tokens.test.mjs` (no mm/pt literals in CSS **or** component JS; every `c-*` class defined), `tests/responsive.test.mjs` (the same A5 issue re-set as B5: builds, no overflow, image share and region proportions preserved within 3 %, text frames widen, type scales gently and never below 7 pt; TEST ISSUE 02 on B5).
- **Verification** A5 pages are visually unchanged vs RC1 (mean abs pixel difference < 1.5/255 on 12 of 16 pages; the rest differ by line breaks). Mutation M24 (mm literal back in a token) and M27 (undefined grid class) killed.
- **Remaining risk** Only A5 and B5 verified; compositions use fixed *ratios* (same proportions on every size, not size-specific design). `LINE_EFFICIENCY=0.96` is a calibration constant (text.mjs) — measured occupancy is the authority.

## P1-4 — Contents overflow
- **Root cause** No capacity contract: entries beyond what fits were rendered off the page and vanished from the PDF.
- **Fix** Pass A measures every `.toc-item`; `CONTENTS_OVERFLOW` is a **validation error** with the measured capacity and remedies; preflight P31 re-checks the final render; the contract table records `overflow_strategy: 'error'`. No auto-pagination in v0.1 (by design).
- **Files** `scripts/lib/{metrics,validate-model,preflight}.mjs`, `layouts/_contracts.mjs`
- **Tests** `model.test.mjs` (stubbed probe), `metrics.test.mjs` (counts entries that do not fit), `responsive.test.mjs` (11 entries cannot build — no PDF produced — and every entry of TEST ISSUE 02 is present in the PDF text), `preflight.test.mjs` (P31). Mutations M15, M16 killed.
- **Remaining risk** Authors must reduce entries or pick a more compact variant; no auto 2-page contents.

## P1-5 — Quality metrics (fit_fill etc.)
- **Root cause** One global threshold on "frame fill" conflated physical emptiness with design quality, ignored the page's role in its article, left content-sized frames unmeasured, rewarded under-filled pages as "quiet", and `body_pt` read the first `<p>`.
- **Fix** `fit_fill` removed. MEASUREMENT: `text_occupancy`, `content_extent`, orphan lines, `body_pt` (running text only). HEURISTIC: `layouts/_contracts.mjs` (sparse_allowed, occupancy range by role first/middle/last/only, extent_min) + flatplan `intentional_sparse` (reason required). `quiet` = declared or composed-by-design, never "under-filled". REVIEW_REQUIRED list is explicit. Fingerprint axes carry `class` MEASUREMENT / HEURISTIC / REVIEW_REQUIRED; E5/I2 annotated as weak on a single issue. Preflight items carry `kind`; no "PASS/ready" verdict.
- **Files** `scripts/lib/{metrics,density,analysis,validate-model,preflight,critic-run}.mjs`, `layouts/_contracts.mjs`, `schemas/flatplan.schema.json`
- **Tests** `density.test.mjs` (contract per component; role-dependent; accidental sparseness flagged, declared intent silenced, reason mandatory, quote/photo never flagged), `metrics.test.mjs`, `text.test.mjs`. Mutations M25, M26 killed.
- **Verification** On TEST ISSUE 01 the heuristics flagged p9 and p14 (RC1's 35 % rule caught only p14); after the sample fixes none remain.
- **Remaining risk** Thresholds in `_contracts.mjs` are judgement calls (HEURISTIC). Intensity is still a descriptive composite. Collisions (text touching photos) are not measured.

## P1-6 — Test power
- **Root cause** Preflight checks had no regression tests; the pipeline test passed even with checks disabled.
- **Fix** One real build + per-failure tampering (PDF pages/boxes, metrics, sources) for: page count, trim size, bleed, ppi, overflow (both kinds), blank page, duplicate/missing/wrong folio, broken image, safe area, short bleed, contents loss, orphan/under-filled heuristics, stale PDF for 8 source kinds (article, caption, image bytes, flatplan, issue.yaml, theme_overrides, issue theme.css, credits), missing image, missing caption, unplaced article, bad spread start, render-not-current. `publication:mutation` breaks 28 behaviours one at a time in a sandbox copy.
- **Files** `tests/{preflight,metrics,text,density,security,boundary,responsive,critic-protection,samples,layout-tokens}.test.mjs`, `scripts/mutation.mjs`
- **Verification** see RC2_CANDIDATE (mutation table). RC1: 6 of 14 mutations killed → RC2: see report.
- **Remaining risk** Mutations are hand-picked; PDF font-embedding and crop-mark *content* checks have no injected-failure test.

## P1-7 — Critic data protection
- **Root cause** `--reset` rewrote every review file unconditionally; generated text (timestamps, auto findings) lived inside authored files, so each pipeline run dirtied tracked records.
- **Fix** Review files are created once. `--reset` refuses if any stage holds work (status, findings, scores, reviewer, dispositions); `--reset --force` first archives every file (+ snapshot) to `reviews/archive/<timestamp>/`. Generated numbers moved to `output/<id>/` (`rhythm.md`, `review-pack/context/auto-diff.md`). Reviews bind to the output via `source_hash` (`review-pack/PACK.json`); an older review is STALE, does not gate the new build, and preflight P27 reports MANUAL CHECK.
- **Files** `scripts/lib/{critic,critic-run,preflight}.mjs`, `scripts/critic-pack.mjs`
- **Tests** `tests/critic-protection.test.mjs`, `tests/critic.test.mjs`. Mutations M22, M23 killed.
- **Remaining risk** An author can still delete files by hand; Git is the backstop. Independence of the reviewer is a process rule, not enforced.

## P1-8 — Sample typography/layout defects (fixed at the cause, no sample-specific CSS)
| RC1 finding | Cause | Fix (where) |
|---|---|---|
| F-003 orphan lines (「る。」「す。」「に。」) | no widow control | `text-wrap: pretty` on running text, decks, leads, captions (theme); measured orphan metric + P29 |
| F-004 quote broken as 「だ／け」 | character-based breaking | `word-break: auto-phrase` (theme) |
| F-002 portrait touching the text column | component geometry ignored the grid gutter | portrait ends one gutter before column 4, side-aware (interview component) |
| F-005 unreadable running head / folio on images | fixed chrome colour | image tone measured from pixels (`tone.mjs`); components pass `runheadOn`/`folioOn` |
| F-006 uneven gaps in ~19-character columns | justification on a narrow measure | measured measure < 24 → ragged-right (`.narrow`) |
| F-008 stray paper strip beside the photo | photo stopped at the inner margin | photo runs to the spine, caption horizontal on tone (photo-essay) |
| F-010 red first character | decorative rule | removed |
| F-011 small/pale captions, loose leading | tokens | `--min-text` 7 pt, darker `--color-sub`, baseline 5.0 mm (167 %) |
| F-012 duplicated 「編集」 row | credits + colophon printed the same role | colophon omits roles already in the credits table |
| p3 box looked unfinished | top-aligned box | box floats at the optical centre |
| p9/p14 half-empty | text volume vs contract | sample copy extended so the contract is met (no threshold changed) |
| divider deck collapsed to one column (found during repair) | `c-1-5` class undefined | defined; test that every `c-*` class used is defined |
- **Tests** `samples.test.mjs` (both examples: validate clean, no FAIL, only documented warnings, no orphan lines, no overflow, min font ≥ 7 pt), `layout-tokens.test.mjs`.
- **Remaining risk** F-009 (weak visual identity) and F-007 (same-composition photos, sample art) are **not** P1 and not addressed; text/photo collisions are still only found by a human.

## P1-9 — Independent re-review
Not performed (cannot be done by the repairing session). Listed as required in RC2_CANDIDATE.

---

## RC1 adversarial cases: RC1 vs RC2

RC2 results are from `reviews/evidence-rc2/F-adversarial.json` (same harness `reviews/tools/adversarial.mjs`, `EVIDENCE_DIR` set so RC1 evidence is untouched) and the regression tests above for cases 16–19.

| # | Case | RC1 | RC2 | Result |
|--:|---|---|---|---|
| 1 | very long headline | preflight FAIL only, after render | **validate ERROR `LAYOUT_OVERFLOW`** (before build) | FIXED |
| 2 | very short body | validate warnings + P17 FAIL | same, plus `P30` heuristic | OK (unchanged) |
| 3 | very long body | `TEXT_MAY_OVERFLOW` + P19 FAIL | same | OK |
| 4 | no image | `MISSING_INPUT` | same | OK |
| 5 | missing image | `MISSING_ASSET` | same | OK |
| 6 | extreme portrait | P22 FAIL only because ppi is low | same (a high-resolution extreme crop is still not flagged) | NOT FIXED (P2) |
| 7 | extreme landscape | P22 FAIL (ppi) | same | NOT FIXED (P2) |
| 8 | no caption | validate warn, P05 FAIL | same | OK |
| 9 | long caption | P19 FAIL after render | **validate ERROR `LAYOUT_OVERFLOW`** | FIXED |
| 10 | unplaced article | errors | same | OK |
| 11 | duplicate page | errors | same | OK |
| 12 | spread start | `SPREAD_PARITY` | same | OK |
| 13 | page-count mismatch | errors | same (+ P09 test on a truncated PDF) | OK |
| 14 | body size 12 pt via theme | validate silent, P19 FAIL | allocation adapts to the measured frame; residual clipping still caught by P19 FAIL | PARTIAL (P2: more slack at large sizes) |
| 15 | extreme margins via theme | **WARNING only** (exit 0) | **FAIL** (P19 + P21) | FIXED |
| 16 | article changed, no build | P10 FAIL | P10 FAIL, now regression-tested | OK |
| 17 | image changed, no build | P10 FAIL | P10 FAIL, tested | OK |
| 18 | CSS changed, no build | themes/layouts detected, `scripts/lib` not | same; theme.css/themes/layouts hash tested | PARTIAL (P2: code/toolchain not hashed) |
| 19 | flatplan changed, no build | P10 FAIL | P10 FAIL, tested | OK |
| 20 | blank page | P17 FAIL | same | OK |
| 21 | Japanese/space/`#` file names | **broken images (DEFECT)** | builds; P18 PASS; PDF has the images | **FIXED (P1-1)** |
| 22 | raw HTML in a manuscript | **1-page PDF, script runs (DEFECT)** | escaped; `MD_RAW_HTML_ESCAPED`; 16-page PDF | **FIXED (P1-2)** |
| 23 | article type vs layout mismatch | no detection (GAP) | still none (heuristic warning only) | NOT FIXED (P2) |
| 24 | duplicate article id | `ARTICLE_DUPLICATE` | same | OK |
| — | TOC overflow (TEST ISSUE 02) | silent loss, P19 FAIL | **validate ERROR `CONTENTS_OVERFLOW`** | **FIXED (P1-4)** |

All cases that map to a P0/P1 item (1, 9, 15, 21, 22, TOC) are FIXED.
