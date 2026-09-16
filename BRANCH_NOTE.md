# Branch note — do not use for production

**Branch:** `cursor/adaptive-4x6-crop-aspect-635d`  
**Status:** Unneeded fix — kept for reference only

## What happened

Printing appeared to use only 4×4 of 4×6 label stock. Investigation added adaptive crop aspect, landscape rotation, and cover-fit changes on this branch (merged to `main` via PR #3).

**Actual root cause:** the printer was not **Calibrated media** after loading 4×6 stock. Running **Calibrate media** in the app (with the correct size preset selected) fixed printing without requiring these code changes.

## Guidance

- Prefer `main` for daily use.
- When switching label paper sizes (4×4 ↔ 4×6, new roll, etc.), always run **Calibrate media** before printing.
- This branch is archived context only; no further work expected here.
