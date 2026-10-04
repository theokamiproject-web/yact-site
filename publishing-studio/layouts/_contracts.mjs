// Component density / capacity contracts. ONE table, read by validation, rhythm analysis and preflight.
//
//  sparse_allowed  true  : short or mostly-empty pages are legitimate for this component (quote, divider, photo spread, cover…)
//                  false : a text page that is largely empty is suspicious unless the flatplan declares `intentional_sparse: true` (+ notes)
//  occupancy       expected text-frame occupancy [min, max] by the page's ROLE in its article:
//                  first | middle | last | only   (the last page of an article is naturally part-filled; middle pages must not be)
//  extent_min      the content should reach at least this fraction of the live area's height
//  capacity        contents: overflow_strategy 'error' (build refuses instead of silently losing entries)
//
// These are heuristics (HEURISTIC class): they raise WARNINGs for a human to judge, never "good/bad" verdicts.
const TEXT = (occupancy, extent_min) => ({ sparse_allowed: false, occupancy, extent_min });

export const DENSITY = {
  cover: { sparse_allowed: true },
  contents: { sparse_allowed: true, capacity: { overflow_strategy: 'error', measured: 'toc_items' } },
  'feature-opener': { sparse_allowed: true },
  'feature-body': TEXT({ first: [0.6, 1], middle: [0.75, 1], last: [0.3, 1], only: [0.4, 1] }, 0.68),
  'interview-opener': TEXT({ first: [0.5, 1], middle: [0.5, 1], last: [0.3, 1], only: [0.4, 1] }, 0.8),
  'interview-body': TEXT({ first: [0.5, 1], middle: [0.6, 1], last: [0.25, 1], only: [0.25, 1] }, 0.6),
  essay: TEXT({ first: [0.6, 1], middle: [0.7, 1], last: [0.3, 1], only: [0.3, 1] }, 0.6),
  'photo-essay': { sparse_allowed: true },
  'full-bleed-photo': { sparse_allowed: true },
  'quote-page': { sparse_allowed: true },
  divider: { sparse_allowed: true },
  column: { sparse_allowed: true },
  profile: { sparse_allowed: true },
  credits: { sparse_allowed: true },
  colophon: { sparse_allowed: true },
};
