/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Browser logic exercised with a small DOM adapter; not layout/RF emulation. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tagName=tag;this.value='';this.textContent='';this.children=[];this.hidden=false;this.disabled=false;this.dataset={};this.events={};this.attributes={};this.classList={toggle(){}};}
  append(...children){this.children.push(...children);if(this.tagName==='select' && !this.value)this.value=children[0]?.value || '';}
  replaceChildren(...children){this.children=[];if(this.tagName==='select')this.value='';this.append(...children);}
  addEventListener(type,action){this.events[type]=action;}
  dispatchEvent(event){return this.events[event.type]?.(event);}
  setAttribute(key,value){this.attributes[key]=value;}
}
(async()=>{
  const html=fs.readFileSync('host/web/index.html','utf8'),elements=new Map();
  for(const match of html.matchAll(/<(\w+)\b[^>]*\bid="([^"]+)"[^>]*>/g)){
    const element=new Element(match[1]);elements.set(match[2],element);
    const value=match[0].match(/\bvalue="([^"]*)"/);if(value)element.value=value[1];
    if(element.tagName==='select')element.value=html.slice(match.index+match[0].length).match(/<option[^>]*value="([^"]*)"/)?.[1] || '';
  }
  const get=id=>{assert(elements.has(id),'Missing HTML element '+id);return elements.get(id);};
  const entries=[1,2].map(i=>({device_id:'esp32-'+String(i).padStart(12,'0'),device_name:'Node '+i,address:'192.168.0.'+i,paired:true,online:true,port:80}));
  let state={connected:true,volume_percent:20,port:entries[0].address,hello:{...entries[0],wifi_upload:true,global_volume:true,policy:'fm1-compat-v1'},
    connection:{transport:'wifi'},status:{slot:1,continuous:true},slots:[{slot:0,name:'Factory'},{slot:1,name:'Main'}],
    masters:[{slot:0,name:'Bypass',selected:true},{slot:1,name:'FX',selected:false}]};
  let calls=[],failRefresh=false,partial=false,holdVolume=null,failVolume=false;
  const storage=new Map([['synthdef-studio-source','{ SinOsc.ar(123) }.play']]);
  const context={TextEncoder,Event:class{constructor(type){this.type=type;}},setTimeout,clearTimeout,
    document:{getElementById:get,createElement:tag=>new Element(tag)},
    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},
    sessionStorage:{getItem:()=> 'token',setItem(){}},location:{hash:'',pathname:'/'},history:{replaceState(){}},
    fetch:async(path,options={})=>{
      const body=options.body?JSON.parse(options.body):null;calls.push({path,body});let result;
      switch(path){
        case '/api/config':result={ports:[{port:'/dev/cu.usbmodem101',name:'XIAO'},{port:'/dev/cu.usbmodem1101',name:'AMOLED'}],serial_ready:true,compiler_ready:true,connected:false,paired_devices:entries,example:'{0}.play',master_example:'{In.ar(0,2)}.play'};break;
        case '/api/network/scan':result={devices:entries};break;
        case '/api/network/broadcast-prepare':result={plan:'reviewed',target:body.target,recipients:entries.map(row=>({...row,ready:true,expected:{slot:1,name:'Existing'}}))};break;
        case '/api/compile':result={artifact:'compiled-once',name:'Main',admitted:true,input_kind:'sound_block',target:body.target,nodes:1,graph_bytes:100,source_bytes:100,delay_samples:0,ugens:['SinOsc'],controls:[],compiler_log:''};break;
        case '/api/network/broadcast-upload':result={verified:!partial,results:entries.map((row,i)=>({...row,verified:!partial || i===0,error:i===1?'Node unreachable':undefined}))};break;
        case '/api/network/connect':result=state;break;
        case '/api/refresh':if(failRefresh)return {ok:false,json:async()=>({error:'Disconnected'})};result=state;break;
        case '/api/master-load':state.masters.forEach(row=>row.selected=row.slot===body.slot);result=state;break;
        case '/api/main-load':result=state;break;
        case '/api/volume':
          if(holdVolume)await holdVolume;
          if(failVolume)return {ok:false,json:async()=>({error:'Volume link failed'})};
          result={device_id:body.device_id,percent:body.percent,saved:body.save};break;
        default:throw Error('Unexpected API request '+path);
      }
      return {ok:true,json:async()=>result};
    }};
  vm.createContext(context);vm.runInContext(fs.readFileSync('host/web/app.js','utf8'),context);
  const idle=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
  const event=async(id,type='click')=>{await get(id).dispatchEvent({type});await idle();};await idle();
  assert.equal(get('source').value,'{ SinOsc.ar(123) }.play');
  // Switching editors without a connected device preserves independent drafts.
  get('target').value='master';await event('target','change');assert.equal(get('source').value,'{In.ar(0,2)}.play');
  get('source').value='{ In.ar(0,2)*0.5 }.play';await event('source','input');
  get('target').value='sound';await event('target','change');assert.equal(get('source').value,'{ SinOsc.ar(123) }.play');
  get('transport').value='wifi';await event('transport','change');get('wifi-mode').value='omni';await event('wifi-mode','change');
  await event('network-scan');await event('broadcast-review');await event('compile');
  assert.equal(get('broadcast-nodes').children.length,2);assert.equal(get('upload').disabled,false);
  await event('upload');assert.equal(calls.filter(row=>row.path==='/api/compile').length,1);
  const upload=calls.find(row=>row.path==='/api/network/broadcast-upload');assert.equal(upload.body.artifact,'compiled-once');assert.equal(upload.body.plan,'reviewed');
  assert.match(get('message').textContent,/Node 1.*saved and verified/);assert.match(get('message').textContent,/Node 2.*saved and verified/);
  assert.equal(get('upload').disabled,true); // A used recipient review cannot be replayed.
  get('wifi-mode').value='single';await event('wifi-mode','change');await event('connect');
  assert.equal(get('slots').children.length,2);assert.equal(get('master-load').textContent,'Enable FX');
  await event('master-load');assert.equal(get('master-load').textContent,'Bypass FX');assert.equal(get('master-load').attributes['aria-pressed'],'false');
  await event('main-load');assert.match(get('message').textContent,/playing without touch/);
  // A selected-node refresh failure must not hide the per-node broadcast report.
  get('wifi-mode').value='omni';await event('wifi-mode','change');await event('broadcast-review');partial=true;failRefresh=true;
  await event('upload');assert.match(get('message').textContent,/Node 1.*saved and verified/);assert.match(get('message').textContent,/Node 2.*Node unreachable/);assert.match(get('message').textContent,/Connection refresh: Disconnected/);
  // A connection made by the host must select its actual USB port, even when
  // another board is first in the dropdown or the port list is refreshed.
  failRefresh=false;state={...state,port:'/dev/cu.usbmodem1101',connection:{transport:'usb'}};
  get('port').value='/dev/cu.usbmodem101';await event('slots-refresh');
  assert.equal(get('port').value,'/dev/cu.usbmodem1101');
  get('port').value='/dev/cu.usbmodem101';await event('ports-refresh');
  assert.equal(get('port').value,'/dev/cu.usbmodem1101');
  assert.equal(get('volume-value').textContent,'20%');assert.equal(get('volume').disabled,false);
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const volumeCalls=()=>calls.filter(row=>row.path==='/api/volume');
  // Rapid pointer movement sends only the latest level, then saves on release.
  for(const level of [0,10,25,37]){get('volume').value=String(level);await event('volume','input');}
  await event('volume','change');await delay(160);
  assert.equal(volumeCalls().length,1);assert.equal(volumeCalls()[0].body.percent,37);assert.equal(volumeCalls()[0].body.save,true);
  assert.equal(get('volume-value').textContent,'37%');assert.match(get('volume-status').textContent,/Saved/);
  // Keep one request in flight; new inputs collapse into one final saved level.
  let release;holdVolume=new Promise(resolve=>{release=resolve;});
  get('volume').value='0';await event('volume','change');await delay(20);
  for(const level of [60,75,100]){get('volume').value=String(level);await event('volume','input');}
  await event('volume','change');assert.equal(volumeCalls().length,2);
  holdVolume=null;release();await delay(250);
  assert.equal(volumeCalls().length,3);assert.equal(volumeCalls()[2].body.percent,100);assert.equal(volumeCalls()[2].body.save,true);
  assert.equal(get('volume-value').textContent,'100%');assert.equal(get('volume').disabled,false);
  failVolume=true;get('volume').value='15';await event('volume','change');await delay(30);
  assert.equal(get('volume-value').textContent,'100%');assert.match(get('volume-status').textContent,/not confirmed/);assert.match(get('message').textContent,/Volume link failed/);failVolume=false;
  // An old response cannot overwrite a different module selected by the host.
  holdVolume=new Promise(resolve=>{release=resolve;});get('volume').value='30';await event('volume','change');await delay(20);
  context.nextState={...state,volume_percent:42,hello:{...state.hello,...entries[1]}};
  vm.runInContext('renderDevice(nextState)',context);
  get('volume').value='45';await event('volume','change');holdVolume=null;release();await delay(150);
  assert.equal(volumeCalls().at(-1).body.device_id,entries[1].device_id);assert.equal(get('volume-value').textContent,'45%');
  // Pending gestures are discarded on disconnect; unsupported firmware hides it.
  const count=volumeCalls().length;get('volume').value='55';await event('volume','input');
  vm.runInContext('renderDevice(null)',context);await delay(150);assert.equal(volumeCalls().length,count);assert.equal(get('volume').disabled,true);
  context.nextState={...state,hello:{...state.hello,global_volume:false}};vm.runInContext('renderDevice(nextState)',context);
  assert.equal(get('volume-control').hidden,true);
  console.log('PASS: Main/FX drafts, Wi-Fi Omni without a single connection, one compilation, recipient review, per-node failures, bypass, Main restart and connected USB port selection.');
  console.log('PASS: module volume, rapid gesture coalescing, in-flight changes, release save, mute/full level, failed replies, target changes and disconnect.');
})().catch(error=>{console.error(error);process.exitCode=1;});
