# Original SynthDef source on the device

The code screen opens by default with the last selected saved SynthDef. It has
a white background, line numbers and 14-pixel DejaVu Sans Mono with fixed spacing.
Touch/drag over the code plays; use the separate right and bottom strips to
scroll vertically and horizontally. A touch retains the role of its starting
region until release. The 320 × 320 code playing area has scroll-independent
X/Y coordinates. Flicks no longer change patches.

CONTROLS opens the black module-management page: output volume, one Main row,
and FX / Bypass. Tapping Main restarts it and returns to code. Controls shows
the module name and permanent ID. Battery/RX activity/Wi-Fi strength remain in
the header; PANIC is bottom right on both screens and acts on press. Opening
Controls releases the current touch. The code area and
scroll strips end above the footer.

This is a read-only viewer. Source is taken from the original UTF-8 text stored
alongside the compiled SynthDef, rather than reconstructed from graph nodes.
Comments, names, whitespace, escapes and backslash symbols are preserved.

## Colours

| Text | Colour |
| --- | --- |
| Ordinary identifiers, methods, punctuation | Black `#000000` |
| Double-quoted strings, single-quoted symbols, `\symbols`, character literals | Green `#008000` |
| Class names, including UGens and Pattern classes such as `SinOsc`, `Pbind`, `Pseq` | Blue `#0000D2` |
| `~environmentVariables` | Orange `#D05F00` |
| Whole words `arg`, `var` | Red `#BF0000` |
| Integers, floats, exponents, hex/radix literals, `pi`, `inf`, `nil`, booleans | Purple `#800080` |
| Line comments and nested block comments | Classic-style red `#BF0000` |

Quoted text and comments take precedence over keyword/class recognition. For
example, `"SinOsc var"` stays green and `// SinOsc var` stays comment-coloured.
Hash sequences in strings display literally; they are not LVGL recolour markup.
The lexer is a colouring aid, not a SuperCollider parser or support validator.
Uppercase class names are blue whether or not the engine supports that class.

The categories follow the SC IDE's [theme token families](https://github.com/supercollider/supercollider/blob/develop/editors/sc-ide/core/settings/theme.cpp),
using the requested colour scheme. The font is distributed with its Bitstream
Vera/DejaVu notices under `assets/fonts/`; the checked-in glyph C file makes
ordinary firmware builds independent of font-conversion software. Latin-1,
pi and common typographic quotes/dashes are included. Other unsupported glyphs
use a replacement character; the underlying UTF-8 bytes remain unchanged.

## Source ownership and memory

Patch publication supplies the active package's source pointer and explicit
length. The UI owns a PSRAM copy, so subsequent upload/staging-buffer reuse
cannot alter the displayed code. The model swaps under the display lock along
with patch metadata. A source-allocation failure clears the previous document
and shows an unavailable message rather than old code under a new patch name.

The factory patch has bundled original source. Its graph/source SHA-256 pair is
recorded after compilation in `examples/touch-sine.source.json`; `prepare.py`
rejects stale pairs. Re-export a changed factory source with
`python3 host/export_factory.py`. Other source-less packages explicitly show
that no source is attached. Saving/loading package bytes and USB format remain
unchanged.

The renderer draws only visible rows/glyphs. It does not create one widget per
line or pass the whole file through LVGL's text allocator. Source/style bytes
and 32-bit line offsets live in PSRAM, supporting the existing **65,536-byte**
source limit, including 65,537 short lines or one very long line. The maximum
single document is 393,221 bytes; old/new models can coexist briefly during a
swap. These are variable PSRAM allocations, not additional fixed internal RAM.
Tabs display at four-column stops; stored tabs and CR/LF bytes are retained.

The existing 64 KiB LVGL heap is unchanged. The host UI test retains 15,752
bytes free after the extra persistent widgets, repeated metadata changes,
scrolling, snapshots and maximum-size documents. The device source/audio test
retained at least 47,871 internal bytes and a 38,912-byte largest free block.

## Verification

- Real LVGL host interaction tests cover CODE/PLAY, drag scrolling, immediate
  Panic, metadata replacement, an owned source copy after the caller changes
  its buffer, missing source, maximum-length documents and invalid lengths.
- The lexer passes token/escape/comment/UTF-8 tests and 1,000 randomized cases
  under undefined/bounds sanitizers with inaccessible guard pages around the
  input and style buffers. The local AddressSanitizer runtime did not reach
  application startup, so an ASan pass is not claimed.
- On-board snapshots verify factory, Mac Sine, Filtered Tone and a separately
  compiled colour-demonstration SynthDef. Saved graph/source/metadata hashes
  and library generations are unchanged after testing.
- Mac Sine, Filtered Tone and Phase FM play and release while the code viewport
  scrolls/redraws at 25 Hz, with zero new numerical, clipping, queue or DMA
  event errors. The observed overall maximum was 586 µs for these held-note
  tests; this is separate from the broader parameter-stress measurements.
- The seven existing voice/operator matrices and master-delay echo windows
  through five seconds pass again on this image. Compact and FM1 UI profiles
  cross-compile with strict DSP options and unchanged sine-table bytes.

Historical source-view image: `cabbeb035d5b`, 908,032-byte application. See
`evidence/source-view-build.json`, `source-view-compact-build.json`,
`source-device.json`, `source-regression-device.json`, `source-lexer.json` and
`ui-host.json`. Actual device screenshots are `source-colours.png`,
`source-factory.png`, `source-mac-sine.png` and `source-filtered.png`.

```sh
python3 host/test_source.py
python3 host/preview_ui.py
python3 host/test_patches.py
python3 host/test_touch.py
```

Export the diagnostic without opening an audio server:

```sh
sclang -D host/export-code-view.scd
```

With the source-view image on the board, replace PORT with its USB port:

```sh
python3 host/test_device_source.py --port PORT --playback --output evidence/source-device.json
python3 host/test_device_fm1.py --port PORT --output evidence/source-regression-device.json
```

The source test restores the selected saved patch and original effect values,
requests Panic and leaves CODE open. `c`/`v` are explicit USB diagnostics for
opening/closing CODE; `r` scrolls/redraws the source while CODE is open. Font
regeneration is optional and requires Pillow:
`python3 host/generate_code_font.py`.

## Title navigation follow-up

Firmware `be3dbbad76fc` adds the title gestures (908,896-byte FM1 application;
908,592 bytes for the compact UI build). The LVGL host test exercises actual
pointer events for both directions, empty-slot skipping, wraparound, short/
vertical/slow gesture rejection, busy/queued/failed actions and CODE retention.
The fixed 64 KiB LVGL heap has 15,352 bytes free in this test.

`host/test_device_swipe.py` checks ten queued next/previous changes on the
device, graph/source/metadata identity, unchanged saved generations and delay
controls, and recovery after an upload rejects navigation. It captures CODE
after a change. Its `<`/`>` USB commands enter the same UI selection/queue path;
pointer recognition is checked in LVGL simulation, while a physical finger
swipe remains a manual check. See `evidence/swipe-device.json`, `swipe-code.png`, `swipe-build.json`,
`swipe-compact-build.json` and `ui-host.json`. The earlier DSP/audio results
above belong to their recorded image; this follow-up changes no DSP math.

```sh
python3 host/test_device_swipe.py --port PORT --output evidence/swipe-device.json
```

## Body flick follow-up

Image `17fd9d362ccb` adds patch selection across the code body and play pad,
after physical-use feedback identified the earlier title-only restriction.
Native LVGL tests exercise both directions on both bodies, distinguish held/
slow/vertical drags, preserve note release, and tolerate unavailable release
coordinates. UI-header edits now also invalidate the host test build cache.
The FM1 application is 910,096 bytes. See `evidence/body-swipe-build.json`,
`body-swipe-compact-build.json`, `body-swipe-device.json` and `ui-host.json`.
Board diagnostics check the selection/loader path; actual finger gestures
remain a separate user check.
