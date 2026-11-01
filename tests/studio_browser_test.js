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
  let state={connected:true,port:entries[0].address,hello:{...entries[0],wifi_upload:true,policy:'fm1-compat-v1'},
    connection:{transport:'wifi'},status:{slot:1,continuous:true},slots:[{slot:0,name:'Factory'},{slot:1,name:'Main'}],
    masters:[{slot:0,name:'Bypass',selected:true},{slot:1,name:'FX',selected:false}]};
  let calls=[],failRefresh=false,partial=false;
  const storage=new Map([['synthdef-studio-source','{ SinOsc.ar(123) }.play']]);
  const context={TextEncoder,Event:class{constructor(type){this.type=type;}},setTimeout,clearTimeout,
    document:{getElementById:get,createElement:tag=>new Element(tag)},
    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},
    sessionStorage:{getItem:()=> 'token',setItem(){}},location:{hash:'',pathname:'/'},history:{replaceState(){}},
    fetch:async(path,options={})=>{
      const body=options.body?JSON.parse(options.body):null;calls.push({path,body});let result;
      switch(path){
        case '/api/config':result={ports:[],serial_ready:true,compiler_ready:true,connected:false,paired_devices:entries,example:'{0}.play',master_example:'{In.ar(0,2)}.play'};break;
        case '/api/network/scan':result={devices:entries};break;
        case '/api/network/broadcast-prepare':result={plan:'reviewed',target:body.target,recipients:entries.map(row=>({...row,ready:true,expected:{slot:1,name:'Existing'}}))};break;
        case '/api/compile':result={artifact:'compiled-once',name:'Main',admitted:true,input_kind:'sound_block',target:body.target,nodes:1,graph_bytes:100,source_bytes:100,delay_samples:0,ugens:['SinOsc'],controls:[],compiler_log:''};break;
        case '/api/network/broadcast-upload':result={verified:!partial,results:entries.map((row,i)=>({...row,verified:!partial || i===0,error:i===1?'Node unreachable':undefined}))};break;
        case '/api/network/connect':result=state;break;
        case '/api/refresh':if(failRefresh)return {ok:false,json:async()=>({error:'Disconnected'})};result=state;break;
        case '/api/master-load':state.masters.forEach(row=>row.selected=row.slot===body.slot);result=state;break;
        case '/api/main-load':result=state;break;
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
  console.log('PASS: Main/FX drafts, Wi-Fi Omni without a single connection, one compilation, recipient review, per-node failures, bypass and Main restart.');
})().catch(error=>{console.error(error);process.exitCode=1;});
