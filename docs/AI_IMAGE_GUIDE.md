# Generating images that print crisply on a Zebra GK420D

The GK420D is a **203 DPI direct-thermal** printer. It can only burn a black dot or leave the sticker white. There is no gray, no color, and no sub-pixel smoothing. Your AI image has to survive that grid.

This app does the final conversion: resize to exact label pixels, then one 1-bit pass (Floyd–Steinberg, Atkinson, or a hard threshold). Generate the art for that pipeline. Do not pre-dither in the generator.

## Hardware limits

| Limit | Value |
| --- | --- |
| Resolution | 203 dots per inch (0.125 mm per dot) |
| Max print width | 4.09 in / 830 dots |
| Max print length | 39 in |
| Tone | Black or white only |
| Media | Direct-thermal sticker/label stock only |

Thin hair, watercolor wash, 6–8 pt type, and 72 DPI web images all fall apart here.

## Exact sizes to request from your generator

Ask for **2× the print pixel size**, then let this app downscale with LANCZOS. That keeps edges cleaner than generating at 203 DPI natively.

| Sticker | Print dots (203 DPI) | Generate at 2× |
| --- | --- | --- |
| 2" × 2" | 406 × 406 | **812 × 812** |
| 3" × 2" | 609 × 406 | **1218 × 812** |
| 4" × 3" | 812 × 609 | **1624 × 1218** |
| 4" × 4" | 812 × 812 | **1624 × 1624** |
| 4" × 6" | 812 × 1218 | **1624 × 2436** |
| 4.09" × 3" (full width) | 830 × 609 | **1660 × 1218** |

Custom size: `print_dots = round(inches × 203)`, then generate at `2 × print_dots`. Width cannot exceed 830 dots.

If your generator only accepts one dimension, lock the aspect ratio to the sticker (1:1 for 4×4, 4:3, 2:3, and so on).

## Prompt add-ons that survive 203 DPI

Append language like this:

```
high-contrast black-and-white sticker, bold shapes, thick outlines
at least 3-4 dots / 0.5 mm wide, flat graphic, limited fine texture,
no tiny text, no photorealistic skin pores, no thin hairlines,
solid fills, simple composition, centered subject, print-ready
```

Good subjects: icons, mascots, badges, bold portraits, geometric patterns, chunky lettering.

Bad subjects: lace, fur close-ups, faint gradients, busy city detail, fine serif text, mist / smoke.

## Export

- Prefer **PNG**.
- Avoid heavy JPEG compression (block artifacts become dirt after dithering).
- Do **not** convert to 1-bit or “halftone” in the generator. This app does one controlled pass.
- Transparent backgrounds become white.

## How to convert in this app

1. Photos / shaded AI art → **Floyd–Steinberg**.
2. Punchy sticker illustrations → **Atkinson**.
3. Logos, text, hard line art → **Threshold**, then move the cutoff until fills stay solid.
4. Raise contrast if the preview looks washed out.
5. Leave sharpen on unless the image is already crunchy.
6. Preview at **2×**. The 1-bit panel is the exact bitmap the head will burn.
7. Print a **calibration** label first. Raise darkness or drop to **2 ips** until 1-dot lines hold.

## Media

The GK420D is **direct thermal**, not thermal transfer. Use direct-thermal sticker or label stock (die-cut with a gap, or continuous). Regular paper and ribbon-based thermal-transfer labels will not print.

Media width: 0.75"–4.25". After loading a new roll, run the printer’s media calibration so label length matches the stock.

## What usually fails

- Images sized for a phone or website (72/96 DPI) and then enlarged
- Thin gray anti-aliased outlines
- Watercolor / airbrush / film-grain looks
- Text smaller than about 12–14 pt, or any thin script
- Busy backgrounds that turn into mud after dithering
- Letting the Windows ZDesigner driver scale or dither the job (this app sends raw ZPL to avoid that)
