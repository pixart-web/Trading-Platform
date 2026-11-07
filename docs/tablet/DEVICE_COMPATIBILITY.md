# Tablet device compatibility

## Primary physical evaluation target

The operator identified **Redmi Pad 2** on 2026-11-07. Exact RAM/storage variant, Wi-Fi/4G variant, installed Android/HyperOS version, security patch level and connected peripherals remain unconfirmed. No physical test has been performed.

The [Xiaomi specification](https://www.mi.com/sg/product/redmi-pad-2/specs/) lists an 11-inch 16:10 display, 2560 × 1600 pixels, up to 90 Hz, HyperOS 2, and regional 4GB/128GB and 8GB/256GB variants. Do not infer the operator's RAM or currently installed Android version from the product family. Physical display density does not establish Android's configured logical density.

## Planned reproducible profiles

| Profile | Pixels | Logical density | Purpose | Status |
|---|---|---|---|---|
| Redmi-sized landscape | 2560 × 1600 | 280 dpi, test assumption | Wide sidebar, multi-panel layout, chart input | Not executed |
| Redmi-sized portrait | 1600 × 2560 | 280 dpi, test assumption | Rotation, vertical composition, keyboard | Not executed |
| Enlarged UI landscape | 2560 × 1600 | 360 dpi, stress assumption | Larger display settings, clipped controls and readability | Not executed |

Emulator profiles reproduce geometry only. They cannot reproduce MediaTek GPU behavior, OEM process termination, HyperOS battery policy, thermal throttling, pen latency or sustained memory pressure. Verify logical density, font scale, RAM and OS on the actual tablet before final acceptance. Do not report emulator results as Redmi hardware qualification.

## Conservative resource policy pending measurements

Treat the 4GB variant as the provisional minimum resource envelope, not as the user's confirmed device. Start with one bounded local research job at a time; measure actual app PSS, native/Python heap, dataset limits, thermal state and cancellation latency before choosing numeric budgets. Do not size jobs from total RAM or promise sustained 90fps. Local engine ABI/runtime proof remains a separate prerequisite.

## Physical acceptance record required

Record model/variant, Android/API/HyperOS build, patch level, logical density/font scale and app SHA. Test cold launch without Pocket Alpha services, real public provider retrieval, local accounting, explicit active-session PAPER execution, UI close/reopen, rotation, process death, Doze/screen-off, power loss recovery, export/restore and extended thermal/battery endurance. Record actual gaps and require reconciliation/explicit resume; never backfill simulated orders during suspended intervals.

PHYSICAL_TABLET_TESTED = NO. DEVICE_COMPATIBLE = NOT YET QUALIFIED.
