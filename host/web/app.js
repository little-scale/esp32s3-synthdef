'use strict';
const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem('studio-token') || '';
if (location.hash) { sessionStorage.setItem('studio-token', token); history.replaceState(null, '', location.pathname); }
let config, device = null, artifact = null, binary = null, busy = false;
let networkDevices = [], broadcast = null;
let volumeSending = false, volumeTimer = null, volumePending = null, volumeEpoch = 0;
let audioEpoch = 0, audioPolling = false, audioLatest = null;
let editorTarget = 'sound';
const drafts = {};
const encoder = new TextEncoder();

function message(text = '', success = false) {
  $('message').textContent = text; $('message').hidden = !text; $('message').classList.toggle('success', success);
}
async function api(path, body) {
  if(body!==undefined && device?.hello.device_id)body={device_id:device.hello.device_id,...body};
  const response = await fetch('/api/' + path, {method: body === undefined ? 'GET' : 'POST',
    headers: {'X-Studio-Token': token, ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
    ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The host service could not complete the request');
  return result;
}
function isMaster() { return $('target').value === 'master'; }
function bank() { return (isMaster() ? device?.masters : device?.slots) || []; }
function destination() { return bank().find(slot => slot.slot === 1); }
function omni() { return $('transport').value === 'wifi' && $('wifi-mode').value === 'omni'; }
function bypassed() { return !!device?.masters?.find(row => row.slot === 0)?.selected; }
function saveEditor() {
  const draft={source:$('source').value,name:$('patch-name').value,binary};drafts[editorTarget]=draft;
  try { localStorage.setItem('synthdef-studio-draft-'+editorTarget,JSON.stringify(draft));
    if(editorTarget==='sound' && !binary)localStorage.setItem('synthdef-studio-source',draft.source);
  } catch (_) { /* Editing remains usable without browser storage. */ }
}
function loadEditor(target) {
  editorTarget=target;
  let draft=drafts[target];
  if(!draft){try{draft=JSON.parse(localStorage.getItem('synthdef-studio-draft-'+target));}catch(_){} }
  draft=draft || {source:target==='master'?config.master_example:localStorage.getItem('synthdef-studio-source') ?? config.example};
  binary=draft.binary || null;$('source').value=draft.source || '';$('patch-name').value=draft.name || '';
  $('file-mode').hidden=!binary;$('file-description').textContent='Compiled '+(target==='master'?'FX':'Main')+' patch';
  $('source-title').textContent=target==='master'?'FX code':'Main code';invalidate();
}
function renderBroadcast() {
  $('broadcast-panel').hidden=!omni();$('network-device').disabled=busy || !!device || omni();
  $('broadcast-nodes').replaceChildren();
  for(const row of broadcast?.recipients || []){
    const p=document.createElement('p');p.textContent=`${row.device_name} · ${row.device_id} · ${row.ready ? 'replace '+(row.expected.name || 'empty patch') : row.error}`;
    $('broadcast-nodes').append(p);
  }
  $('broadcast-status').textContent=broadcast?`${broadcast.recipients.filter(row=>row.ready).length} ready · ${broadcast.target==='master'?'FX':'Main'}. This replaces the listed patches.`:'Find modules, then review the broadcast recipients.';
}
function controls() {
  const locked = busy || volumeSending || volumeTimer !== null;
  $('cpu-peak-reset').disabled = locked || !canResetPeak();
  const entry = destination();
  $('compile').disabled = locked || (!binary && !config?.compiler_ready);
  $('compile').textContent = binary ? 'Check compiled file' : 'Compile';
  const wifi=$('transport').value==='wifi';
  const candidate=networkDevices.find(row=>row.device_id===$('network-device').value);
  $('connect').disabled = locked || (!device && (wifi ? !candidate?.online || !candidate?.paired : !$('port').value));
  $('connect').textContent = device ? 'Disconnect' : 'Connect';
  $('port').disabled = locked || !!device;
  $('transport').disabled=locked || !!device; $('network-device').disabled=locked || !!device || omni();
  $('usb-panel').hidden=wifi; $('wifi-panel').hidden=!wifi;
  $('wifi-setup').hidden=!device || device.connection?.transport==='wifi' || !device.hello.wifi_upload;
  for(const id of ['network-address','network-scan','module-name','wifi-ssid','wifi-password','wifi-save','wifi-pair','wifi-status','wifi-nearby','wifi-networks','wifi-mode','broadcast-review'])$(id).disabled=locked;
  $('slots-field').disabled = locked || !device;
  for (const id of ['example', 'open-file', 'source-mode', 'ports-refresh', 'file', 'read-active', 'slots-refresh', 'panic', 'patch-name', 'mapping', 'target']) $(id).disabled = locked;
  for (let i = 0; i < 4; i++) $('label-' + i).disabled = locked;
  $('source').readOnly = locked;
  const ready=broadcast?.recipients.some(row=>row.ready);
  $('upload').disabled=locked || !artifact || !$('patch-name').value.trim() || !artifact.admitted ||
    (omni()? !ready || broadcast.target!==$('target').value : !device || !entry);
  $('upload').textContent=omni()?'Broadcast '+(isMaster()?'FX':'Main')+' over Wi-Fi':'Upload '+(isMaster()?'FX':'Main');
  $('destination').textContent=omni()?'Sends the same compiled graph and source to every reviewed recipient.':entry?
    `${entry.name?'Replaces “'+entry.name+'”.':'Saves '+(isMaster()?'FX':'Main')+'.'} Module: ${device.hello.device_name} · ${device.hello.device_id}.`:
    'Compile Main or FX, then connect to a module.';
  $('read-active').textContent=isMaster()?'Read FX':'Read Main';
  $('read-active').disabled=locked || !entry?.name;
  $('main-load').disabled=locked || !device?.slots?.find(row=>row.slot===1)?.name;
  $('master-load').disabled=locked || !device || !device.masters?.find(row=>row.slot===1)?.name;
  $('master-load').textContent=bypassed()?'Enable FX':'Bypass FX';
  $('master-load').setAttribute('aria-pressed',String(bypassed()));
  $('fx-status').textContent=device?(bypassed()?'FX bypassed · Main goes straight to output.':'FX enabled · Main passes through FX.'):'FX state appears after connecting.';
  renderBroadcast();
  $('volume-control').hidden = !device?.hello.global_volume;
  $('volume').disabled = busy || !device?.hello.global_volume || !Number.isInteger(device?.volume_percent);
}
async function task(action) {
  if (busy || volumeSending || volumeTimer !== null) return;
  busy = true; controls(); message();
  try { await action(); }
  catch (error) { message(error.message); }
  finally { busy = false; controls(); }
}
function invalidate() {
  artifact = null; $('result').hidden = true;
  const size = encoder.encode($('source').value).length;
  $('source-size').textContent = size.toLocaleString() + ' / 65,536 bytes';
  $('compile-status').textContent = size > 65536 ? 'Source is too large' : binary ? 'Ready to check compiled file' : 'Source changed · compile to upload';
  saveEditor();
  controls();
}
function sourceMode() {
  binary = null; $('file-mode').hidden = true;
  $('source-help').textContent = 'Use a SynthDef or { sound } block; a trailing .play is accepted without host playback. Source runs locally; use code you trust.';
  invalidate();
}
function renderDevice(result) {
  audioEpoch++;
  const nextId = result?.connected ? result.hello.device_id : null;
  if (nextId !== device?.hello.device_id) {
    volumeEpoch++; volumePending = null; clearTimeout(volumeTimer); volumeTimer = null;
  }
  device = result?.connected ? result : null;
  renderAudio(device?.audio);
  if (!volumeSending && !volumePending && Number.isInteger(device?.volume_percent)) {
    showVolume(device.volume_percent, 'Drag to adjust this module only. Release to save across restarts.');
  }
  if(device?.connection?.transport==='wifi'){
    const current={device_id:device.hello.device_id,device_name:device.hello.device_name,address:device.port,port:80,paired:true,online:true};
    const row=networkDevices.find(entry=>entry.device_id===current.device_id);
    if(row)Object.assign(row,current);else networkDevices.push(current);
    renderNetworks();$('network-device').value=current.device_id;
  }
  $('connection-indicator').textContent = device ? 'CONNECTED' : 'OFFLINE';
  $('connection-indicator').classList.toggle('online', !!device);
  $('connected-tools').hidden = !device;
  $('device-status').textContent = device ? `${device.hello.device_name || device.hello.model} · ${device.hello.device_id || device.port} · ${device.connection?.transport==='wifi'?'Wi-Fi':'USB'} ${device.port}` : 'Choose USB or a paired Wi-Fi module, then connect.';
  if(device){
    $('transport').value=device.connection?.transport==='wifi'?'wifi':'usb';
    if(device.connection?.transport!=='wifi')$('port').value=device.port;
    $('setup-identity').textContent=`Configuring only ${device.hello.device_name} · ${device.hello.device_id}`;
    if($('module-name').dataset.deviceId!==device.hello.device_id){$('module-name').value=device.hello.device_name || '';$('module-name').dataset.deviceId=device.hello.device_id || '';}
  }
  $('slots').replaceChildren();
  if(!device){const p=document.createElement('p');p.className='hint';p.textContent='Connect to see Main and FX.';$('slots').append(p);}
  else for(const target of ['sound','master']){
    const entry=(target==='master'?device.masters:device.slots)?.find(row=>row.slot===1);
    const button=document.createElement('button');button.type='button';button.className='slot';
    button.classList.toggle('selected',$('target').value===target);button.setAttribute('aria-pressed',String($('target').value===target));
    const label=document.createElement('span');label.textContent=target==='master'?'FX'+(bypassed()?' · BYPASSED':' · ENABLED'):'MAIN';
    const name=document.createElement('strong');name.textContent=entry?.name || 'Empty';button.append(label,name);
    button.addEventListener('click',()=>{if($('target').value!==target){$('target').value=target;$('target').dispatchEvent(new Event('change'));}});
    $('slots').append(button);
  }
  controls();
}
function canResetPeak() {
  const audio=audioLatest?.data;
  return !!device && audio?.connected && audio.device_id===device.hello.device_id && audio.source==='usb' && audio.peak_tracking===true;
}
function renderAudio(audio, receivedAt = Date.now()) {
  audioLatest = {data: audio, receivedAt};
  $('audio-resources').hidden = !device;
  const matches = !!device && audio?.connected && audio.device_id === device.hello.device_id;
  const fresh = key => matches && audio.source === 'usb' && Number.isFinite(audio.ages?.[key]) &&
    audio.ages[key] >= 0 && audio.ages[key] + (Date.now() - receivedAt) / 1000 <= 5 &&
    Number.isInteger(audio[key]) && audio[key] >= 0 && audio[key] < 0xffffffff;
  for (const [id, key, cpu] of [['cpu-average','average_x10',true],
    ['ram-free','internal_free',false],['psram-free','psram_free',false]]) {
    $(id).textContent = fresh(key) ? cpu ? `${(audio[key] / 10).toFixed(1)}%` : `${(audio[key] / 1024).toFixed(1)} KiB` : '—';
  }
  const peak=audio?.peak_since_reset_x10;
  const peakReady=fresh('peak_x10') && Number.isInteger(peak) && peak>=0 && peak<0xffffffff;
  $('cpu-peak').textContent=peakReady?`${(peak/10).toFixed(1)}%`:'—';
  $('cpu-peak-reset').disabled=busy || volumeSending || volumeTimer!==null || !canResetPeak();
  $('audio-resources').classList.toggle('overloaded', peakReady && peak>=1000);
  $('audio-status').textContent = !device ? '' : matches && audio.source === 'usb' ?
    fresh('average_x10') && fresh('peak_x10') ? audio.peak_waiting ?
      'Waiting for a full CPU window… start your test when the peak appears.' :
      'Live USB diagnostics · peak retained until reset. RAM is free memory for the whole module.' :
      'Diagnostics paused or not received yet. Stale values are hidden.' :
    device.connection?.transport === 'wifi' ? 'Live diagnostics currently need a USB log connection. Wi-Fi control still works.' :
      'Waiting for USB diagnostics. Restart Studio if it is running an older version.';
}
async function pollAudio() {
  if (audioLatest) renderAudio(audioLatest.data, audioLatest.receivedAt);
  if (!device || busy || volumeSending || audioPolling || document.hidden) return;
  const epoch = audioEpoch;
  audioPolling = true;
  try {
    const audio = await api('audio');
    if (epoch === audioEpoch) {
      if(audio.connected===false)renderDevice(null);
      else renderAudio(audio);
    }
  } catch (_) {
    if (epoch === audioEpoch) {
      renderAudio(null);
      $('audio-status').textContent = 'Diagnostics unavailable or Studio is busy. Waiting for the next update…';
    }
  } finally { audioPolling = false; }
}
setInterval(pollAudio, 2000);
$('cpu-peak-reset').addEventListener('click',()=>task(async()=>{
  if(!canResetPeak())return;
  const epoch=++audioEpoch,id=device.hello.device_id;
  const audio=await api('audio/reset-peak',{device_id:id});
  if(epoch===audioEpoch && device?.hello.device_id===id)renderAudio(audio);
}));
function showVolume(percent, status) {
  const db = percent === 0 ? '−∞' : (20 * Math.log10(percent / 100)).toFixed(1).replace('-', '−');
  $('volume').value = String(percent);
  $('volume-value').textContent = `${percent}% · ${db} dB`;
  $('volume').setAttribute('aria-valuetext', `${percent} percent, ${percent === 0 ? 'muted' : `${db} decibels relative to full volume`}`);
  $('volume-status').textContent = status;
}
async function sendVolume() {
  clearTimeout(volumeTimer); volumeTimer = null;
  if (volumeSending || !volumePending) return;
  volumeSending = true; controls();
  try {
    while (volumePending) {
      const request = volumePending; volumePending = null;
      if (request.epoch !== volumeEpoch) break;
      try {
        const result = await api('volume', {device_id: request.id, percent: request.percent, save: request.save});
        if (request.epoch !== volumeEpoch || device?.hello.device_id !== request.id) break;
        if (result.device_id !== request.id || result.percent !== request.percent || (request.save && !result.saved)) {
          throw new Error('The module did not confirm its volume. Refresh before retrying.');
        }
        device.volume_percent = result.percent;
        if (!volumePending) showVolume(result.percent, result.saved ? 'Saved on this module.' : 'Live level applied. Release to save.');
      } catch (error) {
        if (request.epoch === volumeEpoch) {
          volumePending = null;
          showVolume(device.volume_percent, 'Volume not confirmed. Refresh before retrying.');
          message(error.message);
        }
        break;
      }
      if (volumePending) await new Promise(resolve => setTimeout(resolve, 100));
    }
  } finally {
    volumeSending = false;
    if (volumePending) volumeTimer = setTimeout(sendVolume, 0);
    controls();
  }
}
function queueVolume(save) {
  if (busy || !device?.hello.global_volume) return;
  const percent = Number($('volume').value);
  if (!Number.isInteger(percent) || percent < 0 || percent > 100) return;
  volumePending = {id: device.hello.device_id, epoch: volumeEpoch, percent, save};
  showVolume(percent, save ? 'Saving volume…' : 'Adjusting volume…');
  clearTimeout(volumeTimer); volumeTimer = null;
  if (!volumeSending) volumeTimer = setTimeout(sendVolume, save ? 0 : 100);
  controls();
}
$('volume').addEventListener('input', () => queueVolume(false));
$('volume').addEventListener('change', () => queueVolume(true));
async function ports() {
  config = await api('config');
  const previous = $('port').value; $('port').replaceChildren();
  for (const port of config.ports) {
    const option = document.createElement('option'); option.value = port.port; option.textContent = `${port.name} · ${port.port}`; $('port').append(option);
  }
  if (!config.ports.length) { const option = document.createElement('option'); option.value = ''; option.textContent = 'No USB devices found'; $('port').append(option); }
  const selected=device && device.connection?.transport!=='wifi'?device.port:previous;
  if (config.ports.some(p => p.port === selected)) $('port').value = selected;
  if (!config.serial_ready) $('device-status').textContent = 'USB support needs pyserial. Launch with sh host/studio.sh.';
  controls();
}
function nameDefault(name) { return name.replace(/[^\x20-\x7e]|["\\]/g, '_').slice(0, 31) || 'My SynthDef'; }
function showArtifact(result) {
  artifact = result; $('result').hidden = false; $('result-title').textContent = `${result.name} · graph checked`;
  $('result-facts').replaceChildren();
  const facts = [`${result.nodes} UGens`, `${result.graph_bytes.toLocaleString()} graph bytes`, `${result.source_bytes.toLocaleString()} source bytes`, `${(result.delay_samples * 4 / 1024).toFixed(1)} KiB synth arena`];
  for (const fact of facts) { const span = document.createElement('span'); span.textContent = fact; $('result-facts').append(span); }
  $('result-note').textContent = !result.admitted ? 'Compatibility: ' + result.admission_error : result.source_pairing === 'compiled_from_source' ? 'Original source is paired with this compiled graph. The device checks compatibility before activation.' : result.source_bytes ? 'Attached source is preserved; it has not been recompiled to prove it matches this binary.' : 'No original source attached. The device will have no source code to display.';
  if (result.input_kind === 'sound_block' && result.admitted && result.target !== 'master') $('result-note').textContent = 'Starts automatically when loaded, independently of touch. Panic stops it; reload the slot to restart. The original code is preserved; .play was not executed on the computer.';
  if (result.target === 'master' && result.admitted) $('result-note').textContent = 'Master processor: stereo In.ar(0,2) → processing → stereo Out.ar(0). Independent of the sound slot; the original source is preserved.';
  $('diagnostics').textContent = `Graph SHA-256: ${result.graph_sha256}\nSource SHA-256: ${result.source_sha256}\nUGens: ${result.ugens.join(', ')}\nControls: ${result.controls.map(c => c.name + ' = ' + c.default).join(', ')}\n\n${result.compiler_log}`;
  if (!$('patch-name').value.trim()) $('patch-name').value = nameDefault(result.name);
  $('download-source').disabled = !result.source_bytes;
  $('compile-status').textContent = result.admitted ? 'Checked · ready to upload' : 'Compiled · interface needs changes'; controls();
}
$('source').addEventListener('input', invalidate);
$('source').addEventListener('keydown', event => {
  if (event.key !== 'Tab' || busy) return;
  event.preventDefault(); const field = $('source'); field.setRangeText('    ', field.selectionStart, field.selectionEnd, 'end'); invalidate();
});
$('patch-name').addEventListener('input', () => {saveEditor();controls();});
$('port').addEventListener('change', controls);
$('example').addEventListener('click', () => { $('source').value = isMaster() ? config.master_example : config.example; $('patch-name').value = isMaster() ? 'Master FX' : 'Main'; sourceMode(); });
$('target').addEventListener('change', () => {saveEditor();broadcast=null;loadEditor($('target').value);renderDevice(device);});
$('source-mode').addEventListener('click', sourceMode);
$('open-file').addEventListener('click', () => $('file').click());
$('file').addEventListener('change', async event => {
  const file = event.target.files[0]; event.target.value = ''; if (!file) return;
  await task(async () => {
    if (file.size > 65536) throw new Error('Files must fit in 64 KiB');
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (file.name.toLowerCase().endsWith('.scsyndef') || new TextDecoder().decode(bytes.slice(0, 4)) === 'SCgf') {
      let encoded = ''; for (let offset = 0; offset < bytes.length; offset += 8192) encoded += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
      binary = btoa(encoded); $('source').value = '';
      $('file-description').textContent = `${file.name} · compiled file`; $('file-mode').hidden = false;
      $('source-help').textContent = 'Optional: paste the original source to display on the device. Attached source is not recompiled in this mode.';
      invalidate();
    } else {
      $('source').value = new TextDecoder('utf-8', {fatal: true}).decode(bytes); sourceMode();
    }
    $('patch-name').value = ''; controls();
  });
});
$('compile').addEventListener('click', () => task(async () => {
  artifact = null; $('result').hidden = true; $('compile-status').textContent = binary ? 'Checking graph…' : 'Compiling locally…';
  try { showArtifact(await api('compile', {source: $('source').value,target:$('target').value, ...(binary ? {graph: binary} : {})})); }
  catch (error) { $('compile-status').textContent = 'Compile/check failed'; throw error; }
}));
$('ports-refresh').addEventListener('click', () => task(ports));
$('transport').addEventListener('change',()=>{broadcast=null;controls();});
$('wifi-mode').addEventListener('change',()=>{broadcast=null;controls();});
$('network-device').addEventListener('change',controls);
function renderNetworks(){
  const previous=$('network-device').value;$('network-device').replaceChildren();
  for(const row of networkDevices){const option=document.createElement('option');option.value=row.device_id;option.textContent=`${row.device_name} · ${row.device_id} · ${row.online?row.address:'offline'}${row.paired?'':' · pair over USB'}`;$('network-device').append(option);}
  if(!networkDevices.length){const option=document.createElement('option');option.value='';option.textContent='No modules found';$('network-device').append(option);}
  if(networkDevices.some(row=>row.device_id===previous))$('network-device').value=previous;
  $('network-hint').textContent=networkDevices.length?'Select the specific name and permanent ID. Unpaired modules must be paired over USB first.':'No modules found. Check 2.4 GHz Wi-Fi, or enter the module’s IP and try again.';controls();
}
$('network-scan').addEventListener('click',()=>task(async()=>{const result=await api('network/scan',{address:$('network-address').value.trim()});networkDevices=result.devices;broadcast=null;renderNetworks();}));
$('wifi-save').addEventListener('click',()=>task(async()=>{
  if(!$('wifi-ssid').value)throw new Error('Enter the Wi-Fi network name');
  const result=await api('network/setup',{name:$('module-name').value.trim(),ssid:$('wifi-ssid').value,password:$('wifi-password').value});
  $('wifi-password').value='';renderDevice(await api('refresh',{}));
  $('wifi-status-text').textContent=`Saved and paired ${result.device_name} · ${result.device_id}. Wait a few seconds, then Check Wi-Fi.`;
}));
$('wifi-pair').addEventListener('click',()=>task(async()=>{const result=await api('network/setup',{});$('wifi-status-text').textContent=`Paired ${result.device_name} · ${result.device_id}.`;renderDevice(await api('refresh',{}));}));
$('wifi-status').addEventListener('click',()=>task(async()=>{const result=await api('network/status',{});$('wifi-status-text').textContent=result.online?`${result.device_name} is online at ${result.address}. Disconnect USB in the uploader, choose Wi-Fi and Find modules.`:`${result.configured?'Connecting':'Not configured'} · ${result.error} · connection reason ${result.reason}`;}));
$('wifi-nearby').addEventListener('click',()=>task(async()=>{
  const result=await api('network/nearby',{});$('wifi-networks').replaceChildren();
  const choose=document.createElement('option');choose.value='';choose.textContent='Choose a visible network…';$('wifi-networks').append(choose);
  const seen=new Set();for(const row of result.networks){if(!row.ssid || seen.has(row.ssid))continue;seen.add(row.ssid);const option=document.createElement('option');option.value=row.ssid;option.textContent=`${row.ssid} · ${row.rssi} dBm · channel ${row.channel}`;$('wifi-networks').append(option);}
  $('wifi-networks').hidden=false;$('wifi-status-text').textContent=`Found ${seen.size} named networks. ${result.configured_visible?'The saved network is visible.':'The saved network was not detected; choose a visible 2.4 GHz network.'}`;
}));
$('wifi-networks').addEventListener('change',()=>{if($('wifi-networks').value)$('wifi-ssid').value=$('wifi-networks').value;});
$('connect').addEventListener('click', () => task(async () => {
  const wifi=$('transport').value==='wifi';
  renderDevice(await api(device?'disconnect':wifi?'network/connect':'connect',device?{}:wifi?{device_id:$('network-device').value}:{port:$('port').value}));
}));
$('broadcast-review').addEventListener('click',()=>task(async()=>{broadcast=await api('network/broadcast-prepare',{target:$('target').value});renderBroadcast();}));
$('slots-refresh').addEventListener('click', () => task(async () => renderDevice(await api('refresh', {}))));
$('read-active').addEventListener('click', () => task(async () => {
  const entry = destination();
  const patch = await api('read-active', {...(isMaster()?{slot:1}:{}),target:$('target').value});
  binary = patch.graph; $('source').value = patch.source; $('patch-name').value = patch.name;
  for (let i = 0; i < 4; i++) $('label-' + i).value = patch.labels[i];
  $('mapping').value = String(patch.mapping);
  renderDevice(await api('refresh',{}));
  $('file-description').textContent = `${isMaster()?'FX':'Main'} · ${patch.name}`;
  $('file-mode').hidden = false;
  $('source-help').textContent = 'The device graph and attached source have been read back. Choose Use source instead to edit and recompile.';
  invalidate(); message('Current patch read back. Choose Use source instead to recompile, or Check compiled file to reuse the binary.', true);
}));
$('panic').addEventListener('click', () => task(async () => { await api('panic', {}); message('Instrument stopped.', true); }));
$('master-load').addEventListener('click', () => task(async () => {renderDevice(await api('master-load',{slot:bypassed()?1:0}));message(bypassed()?'FX bypassed.':'FX enabled.',true);}));
$('main-load').addEventListener('click',()=>task(async()=>{renderDevice(await api('main-load',{}));message(device.status.continuous?'Main restarted; playing without touch.':'Main reloaded; this SynthDef uses its own controls.',true);}));
$('upload').addEventListener('click', () => task(async () => {
  const entry = destination(); if (!artifact) throw new Error('Compile Main or FX first');
  if(omni()){
    if(!broadcast)throw new Error('Review the broadcast recipients first');
    $('broadcast-status').textContent='Uploading concurrently and verifying each module…';
    const result=await api('network/broadcast-upload',{artifact:artifact.artifact,plan:broadcast.plan,name:$('patch-name').value.trim(),
      labels:Array.from({length:4},(_,i)=>$('label-'+i).value),mapping:Number($('mapping').value)});
    const lines=result.results.map(row=>`${row.device_name} · ${row.device_id}: ${row.verified?'saved and verified':row.error}`);
    broadcast=null;renderBroadcast();
    if(device){try{renderDevice(await api('refresh',{}));}catch(error){lines.push('Connection refresh: '+error.message);}}
    message(lines.join('\n'),result.verified);return;
  }
  if(!entry)throw new Error('Connect to the target module first');
  $('device-status').textContent = `Transferring, saving and verifying ${isMaster()?'FX':'Main'}…`;
  const labels = Array.from({length: 4}, (_, i) => $('label-' + i).value);
  try {
    const result = await api('upload', {artifact: artifact.artifact, slot: entry.slot, expected: entry, replace: !!entry.name,
      name: $('patch-name').value.trim(), labels, mapping: Number($('mapping').value)});
    renderDevice(result); message(`Saved and verified “${result.name}” in ${result.target==='master'?'FX':'Main'}. ${result.target==='master'?'Master FX active; sound playback continues.':result.continuous ? 'Playing continuously. Panic stops it; Restart Main starts it again.' : 'Touch the instrument to play.'}`, true);
  } catch (error) { $('device-status').textContent = 'Upload did not finish. Refresh and check the module before retrying.'; throw error; }
}));
async function download(extension) {
  if (!artifact) return;
  try {
    const response = await fetch(`/api/artifact/${artifact.artifact}.${extension}`, {headers: {'X-Studio-Token': token}});
    if (!response.ok) { const error = await response.json(); throw new Error(error.error); }
    const url = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href = url;
    a.download = nameDefault(artifact.name) + '.' + extension; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { message(error.message); }
}
$('download-graph').addEventListener('click', () => download('scsyndef'));
$('download-source').addEventListener('click', () => download('scd'));
task(async () => {
  await ports();
  networkDevices=(config.paired_devices || []).map(row=>({...row,paired:true,online:false}));renderNetworks();
  if (config.connected) renderDevice(await api('refresh', {}));
  loadEditor('sound'); $('compile-status').textContent = config.compiler_ready ? 'Ready to compile' : 'SuperCollider not found · compiled files can still be checked';
  if (!token) message('Open the full session URL printed by sh host/studio.sh.');
});
