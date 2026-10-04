// Exercise the blind annotator's editing/review workflow without a browser.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const template = fs.readFileSync(new URL('./tracking_annotation.html', import.meta.url), 'utf8');
const dataset = {schema_version:1,dataset_id:'a'.repeat(64),frames:[1,2,3],width:100,height:100,fps:30,source_start_frame:50};
const html = template.replace('__DATASET_JSON__', JSON.stringify(dataset));
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
function fakeElement(id) {
  return {id,value:id==='identity'?'1':'',disabled:false,textContent:'',tagName:'BUTTON',
    style:{},className:'',files:[],children:[],replaceChildren(){this.children=[];},appendChild(item){this.children.push(item);},
    click(){this.onclick?.();},getBoundingClientRect(){return {left:0,top:0,width:100,height:100};},setPointerCapture(){},
    getContext(){return {clearRect(){},drawImage(){},strokeRect(){},fillRect(){},fillText(){},measureText(text){return {width:text.length*8};}};}
  };
}
const document = {getElementById(id){if(!elements.has(id))elements.set(id,fakeElement(id));return elements.get(id);},createElement(tag){return fakeElement(tag);}};
const storage = new Map(), alerts=[];
const sandbox = {document,localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
  Image:class {set src(value){this._src=value;this.onload?.();}get src(){return this._src;}},
  alert:message=>alerts.push(message),confirm:()=>true,Blob,URL:{createObjectURL:()=> 'blob:backup',revokeObjectURL(){}},setTimeout:fn=>fn()};
const context = vm.createContext(sandbox);
vm.runInContext(code,context);
const read = expression => vm.runInContext(expression,context);
const call = expression => vm.runInContext(expression,context);
const element = id=>document.getElementById(id);
const event=(x,y)=>({clientX:x,clientY:y,pointerId:1});
const canvas=element('stage');
function draw(x,y,right,bottom){canvas.onpointerdown(event(x,y));canvas.onpointermove(event(right,bottom));canvas.onpointerup(event(right,bottom));}

draw(10,10,30,30);
assert.equal(read('state.rows.length'),1);
assert.equal(read('state.rows[0][1]'),1);
element('review').click();assert.equal(read('state.reviewed_frames.includes(1)'),true);
element('uncertainty').value='Identity is unclear at this encounter';element('uncertainty').oninput();
assert.equal(read('state.reviewed_frames.includes(1)'),false);
element('next').click();assert.equal(read('state.unresolved_annotations[0].frame'),1);
assert.match(read('state.unresolved_annotations[0].reason'),/unclear/);
console.log('PASS uncertainty is preserved across navigation and invalidates review');

element('copy').click();assert.equal(read('currentRows()[0][1]'),1);
assert.equal(read('state.reviewed_frames.includes(2)'),false);
canvas.onpointerdown(event(12,12));canvas.onpointermove(event(22,22));canvas.onpointerup(event(22,22));
assert.equal(read('currentRows()[0][2]'),20);assert.equal(read('currentRows()[0][3]'),20);
element('review').click();assert.equal(read('state.reviewed_frames.includes(2)'),true);
canvas.onpointerdown(event(39,39));canvas.onpointermove(event(49,49));canvas.onpointerup(event(49,49));
assert.equal(read('currentRows()[0][4]'),30);assert.equal(read('state.reviewed_frames.includes(2)'),false);
console.log('PASS copied boxes can be corrected and every edit invalidates review');

element('newId').click();draw(25,25,35,35);
assert.equal(read('currentRows().length'),2);assert.equal(read('currentRows()[1][1]'),2);
element('identity').value='1';element('identity').onchange();
assert.equal(read('currentRows()[1][1]'),2);assert.match(alerts.at(-1),/unique/);
element('delete').click();assert.equal(read('currentRows().length'),1);assert.equal(read('state.rows.filter(row=>row[0]===1).length'),1);
console.log('PASS distinct overlapping fruit can be labelled and duplicate IDs are rejected');

element('newId').click();draw(60,60,61,61);
assert.equal(read('currentRows()[1][4]'),1);assert.equal(read('currentRows()[1][5]'),1);
assert.equal(read('state.reviewed_frames.includes(2)'),false);
console.log('PASS thin identifiable edge boxes are retained');

element('export').click();assert.match(alerts.at(-1),/name or initials/);
element('annotator').value='Independent reviewer';element('export').click();
const saved=JSON.parse(storage.values().next().value);
assert.equal(saved.annotator,'Independent reviewer');assert.equal(saved.rows.length,3);
assert.equal(saved.unresolved_annotations.length,1);
assert.equal(code.includes('predictions.csv'),false);
assert.equal(code.includes('raw_track_id'),false);
console.log('PASS exported backup contains independent labels and unresolved issues, without predictions');
