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

Use the full printed URL when opening Studio in Chrome or another browser.
Each browser tab keeps its own session access. After restarting Studio, open
the newly printed URL to authenticate again.

```sh
# Explicit compiler/port override; --port is the local web port, not USB.
python host/studio.py --sclang /path/to/sclang --port 8766 --no-open
```

`STUDIO_PYTHON` chooses the interpreter for the shell launcher. Ctrl-C stops the
service and releases USB. Use the browser's Disconnect button before another
tool accesses the board. Restarting Studio disconnects SC clients; stop patterns
first, then reconnect and restart them afterward.

## Install firmware on a USB board

Build the desired image once on the host. Studio uses `firmware/build-xiao` for
the [XIAO ESP32-S3 headless build](HEADLESS.md#build-and-flash) and
`firmware/build-instrument` for the [Waveshare AMOLED 1.8 V2 build](BUILD.md#build-the-current-instrument).
The programmer uses esptool 4.9–4.x from the Studio Python environment or the
installed ESP-IDF 5.5 Python environment.

1. Plug in the board with a USB data cable and open **Install firmware**.
2. Choose the exact board model and its USB port. Use **Refresh** if the port
   has just appeared. A fresh board can be flashed before using **Connect**.
3. Click **Review firmware**. Check the board, USB port and local build, then
   click **Flash firmware**. Studio releases its connection to that port and
   esptool checks the chip and flash size before writing the bootloader,
   partition table and application. Leave the board plugged in until verification.
4. After verification, refresh the USB ports if needed and **Connect** to the
   board. Use the [standard audio check](COMMISSIONING.md) to commission it.

On 11 November 2026, Studio verified a physical XIAO USB flash and connected to
the XIAO afterward. The [headless guide](HEADLESS.md#ns4168-i2s-dac-and-speaker-amplifier)
records the user-confirmed hardware test with the NS4168 DAC and speaker amp.

The flash log includes errors and verification output. If esptool cannot enter
download mode, hold **BOOT** while reconnecting USB, release it, and refresh and
review again. The installer writes the three build images without a full-chip
erase. On an existing installation, keep the same partition layout to retain
saved patches and settings.

## Standalone pattern programs (experimental)

Choose **Main → Pattern example** to load an `ESP32Program(sound, pattern)`
expression. Compile the whole expression, then upload Main. The target needs
firmware advertising `pattern_programs: 1`; older firmware is rejected before
Main is overwritten. The sound and its pattern are saved separately and verified,
then the pattern starts on the device. With `autostart: true`, it also starts
after reboot without Studio or the SC IDE.

The **Standalone pattern** panel shows loaded/running/finished/error status,
whether Main still matches, event count, binary size, runtime RAM and peak
evaluation time. Use **Restart pattern**, **Stop pattern** or **Refresh pattern**.
Refresh reads the latest program counters; the audio CPU gauge measures the
audio task separately. Stop cancels pattern events; a continuous gate-free Main
can keep sounding until Panic. Main replacement and Panic require an intentional
program restart.

Paste `ESP32Program(...)` without its IDE `.sendESP32(target)` suffix in Studio.
Targets are chosen by the existing USB/Wi-Fi/group/Omni upload controls.
See [the exact pattern subset and bounds](SUPERCOLLIDER.md#standalone-pattern-programs-experimental).
This update needs a Studio restart; the server already running in memory does
not gain new Python routes/configuration from a browser refresh alone.

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

The SC extension separates definitions from autonomous blocks:
`.sendESP32` saves silently and `ESP32.play` creates a saved definition.
Function `.playESP32` saves a block that also starts after power-up; literal
SynthDef `.playESP32` creates a runtime instance of a saved definition that boots
inactive. See
[SUPERCOLLIDER.md](SUPERCOLLIDER.md); browser autoplay is not the SC API default.

## CPU and resources

The **CPU and resources** panel shows the selected module's current average audio
CPU load, its peak since reset, free internal RAM, and free PSRAM. Studio reads
cached USB diagnostics every two seconds. A module controlled over Wi-Fi can
also show live values when Studio retains its USB log connection.

CPU is the combined Main/active FX, controls/preparation and output conversion
time as a percentage of the audio block deadline. **CPU peak since reset**
retains the highest reported peak from connection or the last **Reset peak**
click. Studio processes reports between browser refreshes and displays peaks
above 100%. Free RAM values describe the whole module's live heap.

**Program RAM** shows internal instruction RAM (IRAM) and static data RAM
(DRAM) reserved by the linked firmware. **Program flash** shows the running
application image in MiB, the application partition capacity, and the percentage
used. These figures come from the connected firmware over USB or Wi-Fi. Install
the current build to add them to an older module. Firmware reads the image
metadata once before audio starts, and Studio displays the figures for the
selected connection.

**Reset peak** changes Studio's measurement only. It clears the retained peak
and excludes the first report that could contain a pre-click spike. Wait for the
new peak value to appear before starting a test you want to measure; this takes
a few seconds. The selected module's open Studio tabs share the measurement.
Connecting another module starts a new measurement. No device command, sound
restart, patch reload, volume change or firmware update is used by the reset.

Values older than five seconds are hidden independently, so fresh memory logs
cannot make an old CPU reading look live. Missing diagnostics show a dash,
not zero. Switching modules or disconnecting discards the previous display.
After updating Studio's host code, restart Studio and refresh the browser to
load the new backend and panel; restarting interrupts existing SC connections.

## Output volume

The **Output volume** slider activates after connection and shows the confirmed level from
0–100%. Drag for live, smoothed changes; release to save the final level across
restarts. It scales the combined Main/FX output without recompiling, reloading
or restarting either graph. Zero mutes the output. The slider controls only the
currently connected module, including when a group or all modules are selected for uploads.
It works over USB or paired Wi-Fi, on both AMOLED and headless XIAO firmware.
Use **Refresh** to read changes made from SC or the device's physical slider.

The readout also shows output gain in dB, calculated as `20 * log10(percent / 100)`:
100% is 0.0 dB, 50% is −6.0 dB, 20% is −14.0 dB and mute is −∞ dB. This is the
slider's gain relative to full volume; actual signal level in dBFS depends on the
patch's audio and is not measured by this readout.

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

## Module groups and multi-module uploads

Open **Groups** and click **Find modules**. To create a group, choose **New
group**, enter a name, check the member modules, and save. Choose an existing
group to rename it or change its checked members. Offline members stay in the
list so you can keep or remove them. **Dissolve group** removes the saved grouping.
Studio keeps groups on this computer and uses permanent module IDs for membership.
The same groups are available from [SuperCollider](SUPERCOLLIDER.md#module-groups).

### Identify a physical module

In **Groups**, enable **Identify modules**, then click a module name. That module
plays a 440 Hz sine cue for half a second at 50% of its current output setting.
Short fades blend out the program and bring it back afterwards. The program and
its FX continue processing during the cue. The activity indicator lights for the
cue, including the LED on XIAO builds. Membership checkboxes remain available.

Identify requires updated firmware with `identify_tone` in its HELLO response.
Studio checks the permanent device ID before sending `IDENTIFY`, and supports
paired online Wi-Fi modules and the connected USB module. Mute also mutes the
cue. Panic and upload maintenance cancel an active cue.

### Upload to a group or all discovered modules

In **Patches**, choose a group or **All discovered modules** under **Upload to**.
Use **Find modules** to refresh discovery, then **Review recipients**. The review
shows the existing Main or FX patch on each eligible board and flags offline or
unpaired group members. **All discovered modules** includes paired online Wi-Fi
modules and the connected USB module. Studio uses USB when a board appears on
both transports. A newly discovered Wi-Fi board needs pairing before upload.

Compile once and upload to send the same graph and original source to each ready
recipient. Up to eight transfers run concurrently, with independent verification
and results per module. Each module starts its own graph as its transfer finishes.
A review freezes up to 64 recipients, expires after ten minutes, and is used once.
Studio requires a fresh review after a group edit and checks each device identity
and patch generation before upload. Main uploads retain each module's FX choice.
FX uploads enable FX.

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
