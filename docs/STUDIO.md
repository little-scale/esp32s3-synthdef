# SynthDef Studio: browser compiler and USB / Wi-Fi uploader

Studio runs locally on the computer. SuperCollider compiles the source; the ESP32
runs the compiled graph. The Python service owns USB and paired LAN connections,
so the browser does not require Web Serial. Assets are bundled without a CDN.
Keep Studio running for browser operations and live SC messages/patterns. Once a
sound is saved and running, the computer is not needed for its synthesis.

## Start

Install SuperCollider (tested with 3.14.1), Python 3.11+, a C compiler (`cc`) and
`host/requirements.txt` in a Python environment. Then, from the project root:

```sh
sh host/studio.sh
```

The launcher chooses a Python with pyserial, including an existing ESP-IDF Python
environment, opens the browser, and prints its session URL. Keep the terminal
running. Open the complete URL including its fragment; the session token is not
part of a shareable/public URL. Close other serial monitors before connecting.

```sh
# Explicit compiler/port override; --port is the local web port, not USB.
python host/studio.py --sclang /path/to/sclang --port 8766 --no-open
```

`STUDIO_PYTHON` chooses the interpreter for the shell launcher. Ctrl-C stops the
service and releases USB. Use the browser's Disconnect button before another
tool accesses the board. Restarting Studio disconnects SC clients; stop patterns
first, then reconnect and restart them afterward.

## Main + FX destinations

Each device has one writable **Main** patch and one writable **FX** patch.
Main feeds FX/bypass, then the global output scale and the board's audio output
(mono onboard audio on AMOLED; stereo I²S on XIAO).
The normal UI has no numbered library. Protected FX Bypass passes Main through
without deleting the saved FX; a factory Main remains a recovery fallback.
Legacy sound files 2–8 remain on storage but are not selectable or writable here.

Choose **Editing → Main** or **FX**. Each editor keeps its own local source draft,
name and imported graph. Upload replaces that role on the selected device.
**Read Main / Read FX** retrieves the compiled graph and original source. Reading
FX temporarily selects its stored code if needed and restores the prior bypass
selection; it can reinitialize FX state. It does not replace Main.

The browser's sound-block workflow starts uploaded Main blocks automatically,
without touch, and retains that behaviour after reboot. **Panic** stops Main;
**Restart Main** reloads it, including new initial-rate random values. A named
SynthDef's envelope/routing still determines how it responds to touch or controls.

Updated firmware fades the complete output down for about 5 ms before parking
for replacement and fades it up after loading. Output remains zero during the
DMA drain and load, including preserved FX. Loading/storage may make the silent
gap longer than the ramps. User volume and definition/instance semantics do not
change. See [DSP and transitions](DSP_OPTIMIZATIONS.md).

The SC extension deliberately separates saving and instantiation:
`.sendESP32` saves silently, `.playESP32` saves and creates, and `ESP32.play`
creates a saved definition. SC-managed definitions boot inactive. See
[SUPERCOLLIDER.md](SUPERCOLLIDER.md); browser autoplay is not the SC API default.

## Output volume

After connecting, **Output volume** shows the module's confirmed level from
0–100%. Drag for live, smoothed changes; release to save the final level across
restarts. It scales the combined Main/FX output without recompiling, reloading
or restarting either graph. Zero mutes the output. The slider controls only the
currently connected module, including when Omni upload mode is selected.
It works over USB or paired Wi-Fi, on both AMOLED and headless XIAO firmware.
Use **Refresh** to read changes made from SC or the device's physical slider.

Drag updates are coalesced, with one volume request in flight at a time; only
the release is saved to flash. Every write names the exact module ID, and stale
requests are rejected if Studio's selected device has changed. A missing reply
reports an unconfirmed level rather than silently retrying a write. Existing
firmware with `global_volume` support needs no firmware update for this control.

## First USB upload

1. Connect the V2 board, select its USB device and **Connect**. The module name
   and permanent ID identify the destination. Close any other serial monitor.
2. Choose Main or FX, paste source/open a `.scd` file, or import a compiled
   `.scsyndef`. Use a self-contained source expression returning one Function or
   one SynthDef. `SynthDef(...).add` and top-level `({ ... }.play)` are accepted.
3. **Compile**. The result shows graph/source sizes, controls, UGens, arena demand
   and compiler output. The generated native checker uses the same FM1 engine
   profile as the device. Acceptance is not a CPU performance qualification.
4. Choose a display name and **Upload Main / Upload FX**. An occupied destination
   is shown explicitly. Source edits invalidate an old compile result and disable
   upload until compilation/check succeeds again.
5. Upload transfers and commits the package, installs it into the fixed writable
   role, then reads graph/source/metadata back. Success means saved and verified.
   Maintenance can pause audio. FX upload enables the processor; Main upload
   retains the module's FX selection.

The source draft stays in browser local storage; the latest eight compile
artifacts stay in the running host process. Download buttons export the graph
and source. Restarting Studio clears those in-memory artifacts: compile again
before upload. Changing the module requires disconnecting the old selection.

### Sound Functions

```supercollider
{
    arg freq = 220;
    Splay.ar(SinOsc.ar(freq * [1, 1.01], 0, 0.05));
}.play
```

Studio removes the top-level playback suffix for compilation; it does not play
on the computer or start a local audio server. `SynthDef.wrap` retains arguments
and defaults, supplies output bus 0, and marks browser Main blocks for automatic
playback. No envelope or gain control is silently inserted. Return mono/stereo:
more channels need `Mix`, `Splay` or explicit stereo routing. Function blocks
that write `Out`/`LocalOut` themselves, nested `.play`, explicit playback arguments
and extra statements are rejected. Use a literal SynthDef for authored outputs.

Browser source retains the original parentheses, comments, spacing and `.play`
for the display. A binary imported with source has attached text; the service does
not independently prove that text compiled to that binary. The integrity check
verifies transferred bytes. Compiler input executes in the host SC language
process, so compile trusted code and make external dependencies self-contained.

### Master FX

A Function may return processing of `In.ar(0, 2)`; Studio supplies stereo output 0.
A literal SynthDef should provide its own `Out.ar(0, ...)`. The default protected
Bypass uses direct input/output routing with no effect. For example:

```supercollider
{
    arg wet = 0.25;
    var input = In.ar(0, 2);
    FreeVerb2.ar(input[0], input[1], wet, 0.8, 0.4);
}
```

**FX bypass** toggles between protected Bypass and the editable FX package.
Saved Main/FX packages and selection survive restart. Global output volume is
separate from both graphs; see [UI](UI.md) and the SC module-setting API.

## Pair and target Wi-Fi modules

1. Connect each board by USB once. Open **Wi-Fi setup · this USB module**.
2. Use **Find Wi-Fi networks**, choose the exact 2.4 GHz SSID, enter credentials
   and a readable module name, then **Save Wi-Fi and pair this module**. The
   password field is cleared after saving. **Pair existing Wi-Fi setup** pairs
   an already configured module without changing its network settings.
3. **Check Wi-Fi**, disconnect USB in Studio, leave the board powered, and select
   **Connection → Wi-Fi**. **Find modules**, then choose the intended name **and
   permanent ID**. If broadcast discovery is blocked, enter its IPv4 address.
4. Compile/upload/read Main or FX as with USB. Each operation remains bound to
   the selected module's ID. Another board appearing at the same IP is rejected.

Names can duplicate; IDs use the complete station MAC (`esp32-<12 hex digits>`),
so they remain stable across DHCP/IP changes. Controls also displays name/ID.
Wi-Fi RSSI in dBm and the receive dot give local feedback on the node.

Pairing keys are obtained only over USB and stored with mode 0600 in Git-ignored
`build/host/private/network-devices.json`. They are not returned to the browser
or discovery broadcast. Configuration is USB-only. LAN HTTP is authenticated,
without TLS/cloud access, for a trusted network. UDP discovery uses port 32101;
HTTP uses TCP port 80. Client isolation or a firewall can block either path.

Starting Wi-Fi and writing settings pause audio under the maintenance handshake.
Network work stays outside the audio task; network tasks run on core 0 and packet
storage prefers PSRAM. Uploads retain bounded chunks, CRCs, hashes and generation
records. A lease excludes competing Wi-Fi writers, and the patch service excludes
competing USB writes. After an interrupted install, refresh/read before retrying;
the operation may have completed even if its acknowledgement was lost.

## Omni broadcast uploads

Choose **Wi-Fi upload mode → Omni broadcast**, find modules, then **Review
broadcast recipients**. Review paired online names/IDs and their existing Main
or FX packages. Compile once, then **Broadcast Main / FX over Wi-Fi** sends the
same graph and original source to that frozen recipient list. A single-module
connection is optional in Omni mode. Unpaired/offline nodes are excluded.

Uploads use up to eight concurrent authenticated connections and at most 64 nodes.
Each result reports its own verified success or failure. It is reliable fan-out,
not UDP code delivery, a simultaneous start guarantee, or an all-or-nothing fleet
transaction. Each node still has its own random seed and DSP state.

A recipient review expires after ten minutes and is consumed once. New nodes do
not join it; changed identities or destination generations are rejected. Review
again before another broadcast/retry. Main uploads retain each node's FX choice;
FX uploads enable FX. The SC `\all` target resolves paired online recipients
without the browser review flow; callers explicitly select that target.

## Evidence and limits

Host tests use real loopback HTTP with two independent device simulators, native
SC clients and browser logic through a DOM adapter. They cover targeting, shared
names, changed IP ownership, pairing privacy, concurrent byte-identical uploads,
partial failures, expired reviews, lifecycle, cancellation and compact controls.
Physical single-node Wi-Fi, Main/FX and compact-note tests are recorded separately
in [the evidence index](../evidence/README.md). Multi-board RF timing/scalability
has not been established by those simulator tests.

Use `python3 -m unittest test_studio test_network test_control_client test_ide_bridge`
from `host/` for host checks; see [BUILD.md](BUILD.md) for prerequisites. Historical
numbered-slot/storage details remain in [PATCHES.md](PATCHES.md).
