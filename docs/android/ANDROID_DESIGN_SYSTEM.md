# Pocket Alpha Android design system

The original visual reference is `docs/ui/assets/reference-1536x1024.png`; it was available and visually inspected. Existing CSS and `docs/ui/DESIGN_SYSTEM.md` supply the tokens: base #050C14, panel #091621, border #213A4D, foreground #F0F5FA, muted #8EA0B4, positive/accent #2DD4A0, blue #2F8DE4, cyan #32C8DC, negative #FF4D67 and warning #E8B84D. Native selection containers use a dark blue rather than Material's default purple. The launcher mark adapts the existing triangular identity using vector paths; no new generated brand system is introduced.

Material 3 supplies accessible control foundations. The product theme owns financial colors, cards, borders and typography hierarchy. Cards use 12 dp corners and 16 dp padding; primary spacing follows the existing 4/8/12/16/20/24 scale. Text uses native scalable sans typography. Green/red never supply the sole meaning: price direction, unavailable state and quality are also textual. Pocket Score has a circular renderer and explicit non-probability label.

## Intentional mobile adaptations

Five bottom destinations replace the desktop rail. The drawer/More area contains advanced modules. Phones stack cards; dashboard grids use adaptive 380 dp columns on wider screens. Charts provide native gestures, accessible previous/next bar controls, OHLC/volume text, UTC labels and source metadata. Full chart navigation preserves the selected market/timeframe. The current native renderer does not yet offer the complete server-derived overlay/structure/target system required for final acceptance.

Desktop market-cap aggregates and illustrative prices are not reproduced as real values. Only registered markets and stored observations appear. Missing analysis is explicitly unavailable. Device captures under `screenshots/` are from a disposable, labelled SYNTHETIC-E2E provider and are not production financial evidence. Capture-only instrumentation temporarily clears FLAG_SECURE; production code sets it.

Visual acceptance remains incomplete: captures establish layout/runtime evidence, not pixel equivalence or approval of every device/font-scale/TalkBack state. The original image remains the source for subsequent visual comparison.
