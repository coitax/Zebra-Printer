# Printer setup (one 4×4 label)

If a print lands across two labels, or sits in the middle of two stickers, the printer is not synced to the gap. The app now forces gap sensing and a 4×4 length (812×812 dots), but the printer still has to measure the stock.

## Physical load

1. Use **direct-thermal** 4×4 sticker stock. The GK420D / GX420d has no ribbon.
2. Open the lid. Load the roll so labels come over the top, facing the head.
3. Slide the guides until they just touch the liner. Snug, not crushing.
4. Pull the liner forward so a **gap** sits under the printhead.
5. Close the lid firmly.

## Calibrate

1. In the app, set size to **4" × 4"** (the default).
2. Click **Calibrate media**. The printer will feed a few labels while it finds the gap.
3. Press **FEED** once. It should advance **exactly one** label and stop at the tear bar.
4. Click **Print one-label test**. The black box must stay on a single sticker.

## Printer shuts off on the 3rd sticker

A full 4×4 graphic at 2 ips and high darkness is a heavy load for the GK420D / GX420d brick. The head draws a surge on every black area; after two labels the supply overheats and the printer goes dark mid-batch.

Check this first:

1. Use the **original Zebra 20V** power supply, not a generic laptop brick.
2. Plug it into a **wall outlet**, not a cheap power strip or USB-C trigger.
3. Feel the brick after two prints — if it is very hot, that is the failure.
4. For batches: darkness **12–15**, speed **3 ips**.
5. Let it sit 30 seconds after a shutdown before powering back on.

The app now downloads the graphic once and prints copies one at a time with a pause so the supply can recover.

If FEED still runs two labels:

- Wipe the gap sensor window under the head
- Confirm the stock is gap/die-cut, not continuous or black-mark
- Repeat **Calibrate media**

## Driver

Install the printer in Windows (ZDesigner GX420d / GK420d is fine). This app sends **RAW ZPL**, so the driver must not scale or dither the job. Do not print through Microsoft Print to PDF.
