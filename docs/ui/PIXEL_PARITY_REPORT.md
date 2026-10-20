# Pixel parity report

## Evidence

- Native reference and implementation: 1536×1024.
- Browser: repository-pinned Playwright Chromium, device scale 1.
- Capture: `pnpm exec playwright test e2e/workspace.spec.ts --grep "search, select" --workers=1`.
- Comparison: `node frontend/scripts/capture-visual-comparison.mjs` from `frontend/`.
- Artifact: `assets/visual-comparison.png`; the lower panel uses CSS `mix-blend-mode:difference` at identical 768×512 scaled dimensions.

## Matched structure

The fixed navigation rail, topbar, search placement, dark palette, dense market cards, primary chart, right analytical column, compact tables, border weight, selected navigation state and responsive collapse follow the reference. The chart retains the existing verified Lightweight Charts implementation.

## Deliberate deviations

The test asset is labelled `SYNTHETIC`/`fixture-only`; production never receives it. Pocket Score, directional targets, news, events and ticker prices are absent when no corresponding API evidence exists. The operational chart exposes exact range, UTC, quality and provenance controls that occupy more vertical space than the illustration. Text glyphs replace the reference icon set. These deviations protect data integrity and accessibility.

## Result

Structural and design-language parity is achieved. Numeric pixel equality is neither achieved nor claimed because the source contains illustrative data and different chart content. The remaining visible difference is documented rather than concealed with fabricated production values.
