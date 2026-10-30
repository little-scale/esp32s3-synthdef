# Pinned sources

`fm1-synthdef` is a vendored subset of
<https://github.com/little-scale/fm1-synthdef>, commit
`00ac338904304e87845477808e598ef973f49b52`.
`SOURCES.json` records the downloaded archive hash and every retained source hash.

Retained: full `synthdef-engine` including fixtures, independent reference
sources, tools and notices; repository README/LICENSE/THIRD_PARTY/docs;
FM1 math include files and fm1-base headers/notices needed by host comparison
tests; compiled FM1 examples used by upstream tests. FM1 platform sources and
freestanding runtime are not linked into the ESP32 app.

The snapshot is unchanged. The new ESP32 wrapper preserves normal C99 maths,
`-fno-fast-math` and `-ffp-contract=off`. GCC 14 reports three warning classes in
the pinned compact code: misleading indentation, pointer/array parameter spelling
and possible uninitialized values. These remain visible but are not fatal for
the engine component. Parser checks establish arithmetic input counts and literal
MaxLocalBufs counts before rendering; the new adapter retains ordinary warnings
as errors. No global warning suppression or unsafe maths optimization is enabled.

To update: choose an explicit new commit; download it into a separate temporary
directory; review the engine/API/license/test diff; replace only the retained
subset; regenerate the source manifest from those exact archive files; run
`python3 host/prepare.py`, the upstream and adapter tests, reference comparisons
and ESP32 build; then update status/evidence. Do not silently follow the latest
branch, regenerate fixtures, or rebaseline hashes after unreviewed edits.

`waveshare-examples` contains the official `00_board_check` and `12_i2s_codec`
examples plus the repository license at commit
`78e13f852929c2ab4f9d5e0ad1c50ea378dbf2b4` of
<https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.8>.
Local console/tone overrides live in `docs/*.defaults`; vendor source is retained
as downloaded. Generated example lockfiles record each example's own resolution.
