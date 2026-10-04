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
