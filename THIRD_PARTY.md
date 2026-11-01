# Provenance and licenses

Project port/adapter sources use GPL-3.0-or-later. See `LICENSE` and the SPDX
headers. This inventory records selected components; distribution review remains
part of a future release.

| Material | Version / source | Treatment |
| --- | --- | --- |
| DejaVu Sans Mono | Bundled `assets/fonts/DejaVuSansMono.ttf` | Bitstream Vera / DejaVu notices in `assets/fonts/LICENSE-DejaVu`; generated glyph subset in `code_font.c` |
| SynthDef engine and adapted DSP | FM1 commit `00ac338904304e87845477808e598ef973f49b52` | GPL-3.0-or-later; linked into firmware |
| SuperCollider / Mutable Instruments / mi-UGens source and credits | Pins in upstream reference manifests and `upstream/fm1-synthdef/THIRD_PARTY.md` | Retained original per-file notices; independent reference code is test-only |
| FM1 math shim and fm1-base headers | Same upstream snapshot | Host device-math tests only; accompanying notices retained; excluded from firmware includes |
| ESP-IDF | v5.5, commit in `evidence/esp32-build.json` | Apache-2.0 and component-specific terms retained in installed SDK |
| Waveshare BSP | 2.0.3, upstream component commit `9f4030c6e5cb888ad4cc268bfa7584c93ad53e30` | Apache-2.0; pin/codec setup adapted in `board_audio` |
| Official Waveshare examples | Board repo commit `78e13f852929c2ab4f9d5e0ad1c50ea378dbf2b4` | Repository LICENSE retained under `upstream/waveshare-examples` |
| esp_codec_dev | 1.5.11 | Apache-2.0, managed component |
| LVGL | 8.4.0 in instrument build | MIT; touchscreen UI and linked BSP support |
| pyserial | 3.5, host Python dependency | BSD; installed separately for the CLI and browser USB bridge |
| Other managed display/touch/expander support | Exact versions in application `firmware/dependencies.lock` | Original LICENSE files retained by component manager |

The full upstream engine includes kernel adaptations from SuperCollider and
Mutable Instruments. Their licensing does not disappear when changing MCU.
The package manager's selected source directories and lockfile, not the original
handover's candidate versions, define this build. Other application examples may
resolve a different LVGL version; they have separate lockfiles.
