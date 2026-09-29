# Archive

Earlier versions of the stitching pipeline, kept for reference. They are not maintained, and the first two did not produce usable results.

| File | Approach | Outcome |
|---|---|---|
| `stitch_scriptv1.py` | `aicspylibczi.read_mosaic`, placing tiles by microscope stage coordinates only. | Misaligned tiles and swapped colour channels. Accepts 25-tile mosaics only. |
| `stitch_script_fiji.py` | Fiji Grid/Collection stitching reading the `.czi` directly through Bio-Formats. | Ghosting (full-resolution tiles stitched against the embedded pyramid levels) and memory failures. |
| `stitch_v1.py` | Hybrid pipeline: Python tile extraction, Fiji phase-correlation stitching, Python OME-TIFF compression. Originally named `stitch_script_extract_fiji.py`. | Working. No illumination correction. Superseded by `stitching/stitch_v2.py` and `stitching/stitch_v3.py`. |
