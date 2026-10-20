# Visual reference

The supplied 1536×1024 Pocket Alpha image is the desktop source of truth. It defines a 202 px left rail, 58 px top bar, dense two-column analytical content, near-black navy surfaces, quiet one-pixel borders, compact typography and green/red financial semantics.

The production UI reproduces that hierarchy without copying the image's illustrative values. The image's prices, scores, opportunities, portfolio values, news and events are not application evidence. Operational widgets render only API responses; the visual capture uses an explicitly synthetic Playwright fixture.

Reference: `assets/reference-1536x1024.png`. Implementation: `assets/implementation-1536x1024.png`. Reproducible comparison: `visual-comparison.html` and `frontend/scripts/capture-visual-comparison.mjs`.

Substitutions: the system font stack replaces the unidentified reference font; lightweight text glyphs replace proprietary icons; unavailable backend aggregations use honest status cards rather than decorative numbers.
