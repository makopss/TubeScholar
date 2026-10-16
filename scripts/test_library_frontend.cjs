// Offline library request/selection regressions. Run: node --test scripts/test_library_frontend.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../frontend/library.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function result(title = 'First note', id = 'one', extra = {}) {
  return {notes: [{note_id:id, title, video_type:'local', learning_status:'unread', tags:[], collection_ids:[], ...extra}],
    total:1, active_count:1, trash_count:0, collections:[], smart_groups:[], ...extra.page};
}
const response = body => ({ok:true, json:async()=>body});

function setup(fetch, loadNote) {
  const elements = new Map(), timers = new Map(), calls = [], docHandlers = {}, loads = [], drawerCalls = [];
  let ready;
  const element = id => {
    if (elements.has(id)) return elements.get(id);
    const classes = new Set(['library-folders','library-create-form','library-selection-bar','library-destination-menu','library-note-menu','library-toolbar-menu'].includes(id) ? ['hidden'] : []);
    const node = {id, value:'', textContent:'', innerHTML:'', checked:false, disabled:false, dataset:{}, handlers:{},
      classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c, force) {
        const enabled = force === undefined ? !classes.has(c) : force;
        enabled ? classes.add(c) : classes.delete(c); return enabled;
      }},
      addEventListener(type, handler) { this.handlers[type] = handler; },
      setAttribute(name, value) { this[name] = value; }, getAttribute(name) { return this[name] ?? null; },
      focus() {}, contains:()=>false, style:{}, offsetHeight:140,
      getBoundingClientRect:()=>({top:0,bottom:30,height:720}),
      querySelectorAll:()=>[],
    };
    elements.set(id, node); return node;
  };
  const context = vm.createContext({
    window:{}, document:{getElementById:element, addEventListener:(type, fn)=>{if(type==='DOMContentLoaded') ready=fn;else docHandlers[type]=fn;}, activeElement:null},
    t:(key, params)=>key+(params ? JSON.stringify(params) : ''),
    fetch:(url, options)=>{calls.push({url, options});return fetch(url, options);},
    AbortController, URLSearchParams, console, currentNoteId:null, resetTtsPlayerState(){},
    confirm:()=>true, toggleDrawer(open,options){drawerCalls.push({open,options});element('library-drawer').setAttribute('aria-hidden',String(!open));},
    async loadSingleSavedNote(id) { loads.push(id); if(loadNote) await loadNote(id,context);else context.currentNoteId=id; },
    setTimeout:(fn)=>{const id=Symbol();timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),
  });
  context.window.addEventListener=()=>{};
  vm.runInContext(source, context); ready();
  return {context, calls, loads, drawerCalls, element, refresh:()=>context.window.StudyLibrary.refresh(),
    documentClick(path) {docHandlers.click({composedPath:()=>path});},
    async fire(id,type,event={}) {element(id).handlers[type](event);await tick();},
    async click(data,detail=1) {const target=element('clicked-button');target.dataset=data;
      element('library-drawer').handlers.click({target:{closest:()=>target},detail});await tick();},
    async doubleClick(id) {await this.fire('library-drawer','dblclick',{
      target:{closest:()=>({dataset:{libraryOpen:id}})},preventDefault(){}});},
    async select(id,checked=true) {await this.fire('library-drawer','change',{target:{dataset:{librarySelect:id},checked}});},
    async timers() {for(const fn of timers.values()) fn();timers.clear();await tick();},
  };
}

test('a late list response cannot overwrite a newer list', async()=>{
  const pending=[];
  const env=setup(()=>new Promise(resolve=>pending.push(resolve)));
  const old=env.refresh(), next=env.refresh();
  pending[1](response(result('New note')));await next;
  pending[0](response(result('Old note')));await old;
  assert.match(env.element('library-list').innerHTML,/New note/);
  assert.doesNotMatch(env.element('library-list').innerHTML,/Old note/);
  assert.equal(env.calls[0].options.signal.aborted,true);
});

test('typing invalidates an old request before the debounce expires', async()=>{
  let release;
  const env=setup(()=>new Promise(resolve=>release=resolve));
  const old=env.refresh();
  await env.fire('library-search','input',{target:{value:'new query'}});
  release(response(result('Old response')));await old;
  assert.equal(env.element('library-list').innerHTML,'');
  assert.equal(env.calls[0].options.signal.aborted,true);
});

test('search and simple group views reach the server using encoded parameters', async()=>{
  const env=setup(async()=>response(result()));
  await env.fire('library-search','input',{target:{value:'수학 & math'}});await env.timers();
  await env.click({libraryCollection:'manual-group'});
  const params=new URL(env.calls.at(-1).url,'http://127.0.0.1').searchParams;
  assert.equal(params.get('q'),'수학 & math');
  assert.equal(params.get('collection_id'),'manual-group');
  assert.equal(params.has('source'),false);
  assert.equal(params.has('status'),false);
  await env.click({libraryTopic:'math'});
  const topic=new URL(env.calls.at(-1).url,'http://127.0.0.1').searchParams;
  assert.equal(topic.get('topic'),'math');
  assert.equal(topic.get('collection_id'),'');
});

test('untrusted titles, tags, collection names and body snippets are escaped', async()=>{
  const body=result('<img src=x onerror=alert(1)>','one',{
    snippet:'<script>bad()</script>',tags:['<b>tag</b>'],collection_ids:['group'],
    page:{collections:[{id:'group',name:'<svg onload=bad()>',count:1,note_ids:['one']}]},
  });
  const env=setup(async()=>response(body));await env.refresh();
  const html=env.element('library-list').innerHTML;
  assert.doesNotMatch(html,/<script>|<img src=x|<svg onload|<b>tag/);
  assert.match(html,/&lt;script&gt;bad/);
  assert.match(html,/&lt;b&gt;tag/);
  assert.match(env.element('library-collections').innerHTML,/&lt;svg onload/);
});

test('selections survive pagination and bulk requests include only those selected', async()=>{
  const env=setup(async(url, options)=>{
    if(options.method==='POST') return response({success:true});
    const offset=new URL(url,'http://127.0.0.1').searchParams.get('offset');
    return response(result(offset==='20'?'Second':'First',offset==='20'?'two':'one',{
      page:{total:21,collections:[{id:'group',name:'Course',count:0}]}}));
  });
  await env.refresh();await env.select('one');
  await env.fire('library-next','click');await env.select('two');
  assert.match(env.element('library-selection-count').textContent,/"count":2/);
  await env.click({libraryDestination:'group'});
  const request=env.calls.find(call=>call.options.method==='POST');
  assert.deepEqual(JSON.parse(request.options.body).note_ids,['one','two']);
  assert.match(env.element('library-selection-count').textContent,/"count":0/);
});

test('a rejected mutation keeps the selection and displays its error', async()=>{
  const env=setup(async(url, options)=>options.method==='POST'?
    {ok:false,status:409,json:async()=>({detail:'The selected note changed'})}:response(result()));
  await env.refresh();await env.select('one');await env.click({libraryAction:'trash'});
  assert.match(env.element('library-selection-count').textContent,/"count":1/);
  assert.match(env.element('library-feedback').textContent,/selected note changed/);
});

test('a cancelled permanent delete does not send a mutation', async()=>{
  const env=setup(async()=>response(result()));
  env.context.confirm=()=>false;
  await env.refresh();await env.select('one');await env.click({libraryAction:'purge'});
  assert.equal(env.calls.filter(call=>call.options.method==='POST').length,0);
});

test('trash changes view, clears selection and never renders openable trashed titles', async()=>{
  const env=setup(async()=>response(result('Trashed','one',{trashed_at:'2026-10-16'})));
  await env.refresh();await env.select('one');await env.click({libraryView:'trash'});
  const params=new URL(env.calls.at(-1).url,'http://127.0.0.1').searchParams;
  assert.equal(params.get('trash'),'true');
  assert.match(env.element('library-selection-count').textContent,/"count":0/);
  assert.match(env.element('library-list').innerHTML,/data-library-open="one" disabled/);
});

test('an invalid collection falls back to all notes without an infinite retry', async()=>{
  const env=setup(async(url)=>new URL(url,'http://127.0.0.1').searchParams.get('collection_id')?
    {ok:false,status:404,json:async()=>({detail:'Missing collection'})}:response(result()));
  await env.click({libraryCollection:'gone'});
  assert.equal(env.calls.length,2);
  assert.match(env.element('library-list').innerHTML,/First note/);
});

const dragType='application/x-tubescholar-notes';
function transfer(payload, types=[dragType]) {
  return {types, values:{[dragType]:payload}, setData(type,value){this.values[type]=value;}, getData(type){return this.values[type]||'';}};
}
function dragEvent(node,dataTransfer) {
  return {target:{closest:()=>node},dataTransfer,preventDefault(){this.prevented=true;}};
}
const groupPage={collections:[{id:'group',name:'Course',count:0}],smart_groups:[{id:'math',count:1}]};

test('folders start collapsed and thumbnails replace the management table',async()=>{
  const env=setup(async()=>response(result('Lesson','one',{thumbnail:'https://example.com/thumb.jpg',page:groupPage})));
  await env.refresh();
  assert.equal(env.element('library-folders').classList.contains('hidden'),true);
  assert.match(env.element('library-list').innerHTML,/class="library-thumb"/);
  assert.match(env.element('library-list').innerHTML,/img src="https:\/\/example.com\/thumb.jpg"/);
  const html=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
  assert.doesNotMatch(html,/id="library-(manage|source|status|sort|filters|tag-filter)"/);
  await env.fire('library-groups-toggle','click');
  assert.equal(env.element('library-folders').classList.contains('hidden'),false);
  assert.match(env.element('library-smart-groups').innerHTML,/data-library-topic="math"/);
  assert.doesNotMatch(env.element('library-smart-groups').innerHTML,/data-library-drop/);
  await env.fire('library-close-groups','click');
  assert.equal(env.element('library-folders').classList.contains('hidden'),true);
  assert.equal(env.element('library-groups-toggle')['aria-expanded'],'false');
  assert.equal(env.element('library-toolbar-menu').classList.contains('hidden'),true);
});

test('dragging selected notes keeps the compact layout and exposes group chip targets',async()=>{
  const env=setup(async()=>response(result('Lesson','one',{page:groupPage})));
  await env.refresh();await env.select('one');await env.select('two');
  const dt=transfer('');
  await env.fire('library-drawer','dragstart',dragEvent({dataset:{libraryNote:'one'}},dt));
  await env.timers();
  assert.deepEqual(JSON.parse(dt.getData(dragType)).note_ids,['one','two']);
  assert.equal(dt.effectAllowed,'copy');
  assert.equal(env.element('library-folders').classList.contains('hidden'),true);
  assert.match(env.element('library-group-shortcuts').innerHTML,/data-library-collection="group" data-library-drop="group"/);
  await env.fire('library-drawer','dragstart',dragEvent({dataset:{libraryNote:'three'}},dt));
  assert.deepEqual(JSON.parse(dt.getData(dragType)).note_ids,['three']);
});

test('dropping selected notes adds one deduplicated membership request',async()=>{
  const env=setup(async(url,options)=>response(options.method==='POST'?{success:true}:result('Lesson','one',{page:groupPage})));
  await env.refresh();
  const folder=env.element('drop-folder');folder.dataset.libraryDrop='group';
  const dt=transfer(JSON.stringify({note_ids:['one','two','one']}));
  const over=dragEvent(folder,dt);await env.fire('library-drawer','dragover',over);
  assert.equal(over.prevented,true);assert.equal(folder.classList.contains('is-drop-target'),true);
  await env.fire('library-drawer','drop',dragEvent(folder,dt));
  const mutations=env.calls.filter(call=>call.options.method==='POST');
  assert.equal(mutations.length,1);
  assert.deepEqual(JSON.parse(mutations[0].options.body),{note_ids:['one','two'],action:'collection_add',collection_id:'group'});
  assert.equal(folder.classList.contains('is-drop-target'),false);
});

test('invalid or external drops cannot mutate group membership',async()=>{
  const env=setup(async()=>response(result('Lesson','one',{page:groupPage})));await env.refresh();
  const folder=env.element('drop-folder');folder.dataset.libraryDrop='group';
  for(const payload of ['{bad',JSON.stringify({note_ids:['../outside']}),JSON.stringify({note_ids:[]})]) {
    await env.fire('library-drawer','drop',dragEvent(folder,transfer(payload)));
    assert.ok(env.element('library-feedback').textContent);
  }
  const external=dragEvent(folder,transfer('', ['Files']));await env.fire('library-drawer','drop',external);
  assert.equal(external.prevented,undefined);
  assert.equal(env.calls.filter(call=>call.options.method==='POST').length,0);
});

test('trash cannot start a drag and a group removal uses only the current group',async()=>{
  const env=setup(async(url,options)=>response(options.method==='POST'?{success:true}:result('Lesson','one',{page:groupPage})));
  await env.refresh();await env.click({libraryCollection:'group'});await env.select('one');
  await env.click({libraryAction:'collection_remove'});
  assert.deepEqual(JSON.parse(env.calls.find(call=>call.options.method==='POST').options.body),
    {note_ids:['one'],action:'collection_remove',collection_id:'group'});
  await env.click({libraryView:'trash'});
  const dt=transfer(''),event=dragEvent({dataset:{libraryNote:'one'}},dt);
  await env.fire('library-drawer','dragstart',event);
  assert.equal(event.prevented,true);assert.equal(dt.getData(dragType),'');
});

test('each note exposes a collapsed ellipsis menu and Escape closes only the menu',async()=>{
  const env=setup(async()=>response(result('Lesson','one',{page:groupPage})));await env.refresh();
  assert.match(env.element('library-list').innerHTML,/data-library-menu="one" aria-haspopup="menu" aria-expanded="false"/);
  await env.click({libraryMenu:'one'});
  const menu=env.element('library-note-menu');
  assert.equal(menu.classList.contains('hidden'),false);
  assert.match(menu.innerHTML,/data-library-choose-group="one"/);
  assert.match(menu.innerHTML,/data-library-note-action="trash" data-library-note-id="one"/);
  assert.doesNotMatch(menu.innerHTML,/collection_remove/);
  await env.click({libraryChooseGroup:'one'});
  env.documentClick([{id:'detached-item'},env.element('library-note-menu')]);
  assert.equal(menu.classList.contains('hidden'),false);
  assert.match(menu.innerHTML,/data-library-destination="group" data-library-note-id="one"/);
  await env.fire('library-drawer','keydown',{key:'Escape'});
  assert.equal(menu.classList.contains('hidden'),true);
});

test('a note menu changes only that note even when others are selected',async()=>{
  const env=setup(async(url,options)=>response(options.method==='POST'?{success:true}:result('Lesson','one',{page:groupPage})));
  await env.refresh();await env.select('two');
  await env.click({libraryDestination:'group',libraryNoteId:'one'});
  assert.deepEqual(JSON.parse(env.calls.find(call=>call.options.method==='POST').options.body),
    {note_ids:['one'],action:'collection_add',collection_id:'group'});
  await env.click({libraryView:'trash'});await env.click({libraryMenu:'one'});
  assert.match(env.element('library-note-menu').innerHTML,/data-library-note-action="restore"/);
  assert.match(env.element('library-note-menu').innerHTML,/data-library-note-action="purge"/);
  assert.doesNotMatch(env.element('library-note-menu').innerHTML,/data-library-choose-group|data-library-open/);
});

test('one toolbar menu contains all three actions and closes on Escape or outside click',async()=>{
  const env=setup(async()=>response(result('Lesson','one',{page:groupPage})));await env.refresh();
  const html=fs.readFileSync(require('node:path').join(__dirname,'../frontend/index.html'),'utf8');
  const menuMarkup=html.match(/<div id="library-toolbar-menu"[\s\S]*?<\/div>/)[0];
  for(const id of ['library-groups-toggle','library-new-group-btn','library-trash-view']) assert.match(menuMarkup,new RegExp(`id="${id}"`));
  const search=html.match(/<div class="library-search-row">[\s\S]*?<\/div>/)[0];
  assert.equal((search.match(/<button /g)||[]).length,1);
  await env.fire('library-more-btn','click');
  assert.equal(env.element('library-toolbar-menu').classList.contains('hidden'),false);
  assert.equal(env.element('library-more-btn')['aria-expanded'],'true');
  env.documentClick([env.element('library-more-btn')]);
  assert.equal(env.element('library-toolbar-menu').classList.contains('hidden'),false);
  await env.fire('library-drawer','keydown',{key:'Escape'});
  assert.equal(env.element('library-toolbar-menu').classList.contains('hidden'),true);
  await env.fire('library-more-btn','click');env.documentClick([{id:'outside'}]);
  assert.equal(env.element('library-toolbar-menu').classList.contains('hidden'),true);
  await env.fire('library-more-btn','click');await env.fire('library-new-group-btn','click');
  assert.equal(env.element('library-create-form').classList.contains('hidden'),false);
  assert.equal(env.element('library-toolbar-menu').classList.contains('hidden'),true);
});

test('text-only group chips navigate directly and reflect the active group',async()=>{
  const env=setup(async()=>response(result('Lesson','one',{page:groupPage})));await env.refresh();
  const chips=()=>env.element('library-group-shortcuts').innerHTML;
  assert.doesNotMatch(chips(),/<svg|<img/);
  assert.match(chips(),/>Course<\/span><span class="library-group-count">0<\/span>/);
  assert.match(chips(),/>lib_topic_math<\/span><span class="library-group-count">1<\/span>/);
  await env.select('one');await env.click({libraryCollection:'group'});
  assert.match(chips(),/is-active" aria-pressed="true"[^>]*data-library-collection="group"/);
  assert.match(env.element('library-selection-count').textContent,/"count":0/);
  await env.click({libraryTopic:'math'});
  assert.match(chips(),/is-active" aria-pressed="true"[^>]*data-library-topic="math"/);
  await env.click({libraryView:'trash'});
  assert.match(chips(),/aria-pressed="true"[^>]*data-library-view="trash"/);
  await env.click({libraryView:'all'});
  assert.match(chips(),/aria-pressed="true"[^>]*data-library-view="all"/);
  assert.doesNotMatch(chips(),/data-library-view="trash"/);
});

test('group creation supports consecutive entries, preserves failed names, and closes explicitly',async()=>{
  const env=setup(async(url,options)=>{
    if(options.method==='POST') {
      return JSON.parse(options.body).name==='Duplicate' ?
        {ok:false,status:409,json:async()=>({detail:'Group already exists'})} : response({id:'new-group'});
    }
    return response(result('Lesson','one',{page:groupPage}));
  });
  await env.refresh();await env.fire('library-new-group-btn','click');
  for(const name of ['Course one','Course two','Duplicate']) {
    env.element('library-new-name').value=name;
    await env.fire('library-create-form','submit',{preventDefault(){}});
    assert.equal(env.element('library-create-form').classList.contains('hidden'),false);
    assert.equal(env.element('library-new-name').value,name==='Duplicate'?name:'');
  }
  assert.match(env.element('library-feedback').textContent,/already exists/);
  assert.deepEqual(env.calls.filter(call=>call.options.method==='POST').map(call=>JSON.parse(call.options.body).name),
    ['Course one','Course two','Duplicate']);
  await env.fire('library-cancel-create','click');
  assert.equal(env.element('library-create-form').classList.contains('hidden'),true);
});

test('selection checkboxes precede thumbnails and group counts include All and Trash',async()=>{
  const env=setup(async()=>response(result('Lesson','one',{page:{...groupPage,active_count:9,trash_count:2}})));
  await env.refresh();
  const html=env.element('library-list').innerHTML;
  assert.ok(html.indexOf('class="library-note-select"')<html.indexOf('class="library-thumb-wrap"'));
  assert.match(env.element('library-group-shortcuts').innerHTML,/>lib_all<\/span><span class="library-group-count">9<\/span>/);
  await env.click({libraryView:'trash'});
  assert.match(env.element('library-group-shortcuts').innerHTML,/>lib_trash<\/span><span class="library-group-count">2<\/span>/);
});

test('single clicks browse notes without closing, while double click closes without reloading',async()=>{
  const env=setup(async()=>response(result()));await env.refresh();
  await env.click({libraryOpen:'one'});await env.click({libraryOpen:'two'});
  assert.deepEqual(env.loads,['one','two']);
  assert.equal(env.drawerCalls.length,0);
  assert.equal(env.context.currentNoteId,'two');
  await env.doubleClick('two');
  assert.deepEqual(env.loads,['one','two']);
  assert.equal(env.drawerCalls.length,1);assert.equal(env.drawerCalls[0].open,false);
  assert.equal(env.calls.filter(call=>/\/opened$/.test(call.url)).length,2);
});

test('a fast double click reuses a pending load and closes immediately',async()=>{
  let release;
  const env=setup(async()=>response(result()),(id,ctx)=>new Promise(resolve=>{
    release=()=>{ctx.currentNoteId=id;resolve();};
  }));
  await env.refresh();await env.click({libraryOpen:'one'});await env.click({libraryOpen:'one'},2);
  await env.doubleClick('one');
  assert.deepEqual(env.loads,['one']);
  assert.equal(env.drawerCalls.length,1);assert.equal(env.context.currentNoteId,null);
  release();await tick();
  assert.equal(env.context.currentNoteId,'one');
  assert.equal(env.calls.filter(call=>/\/opened$/.test(call.url)).length,1);
  assert.equal(env.drawerCalls.length,1);
});

test('only outside clicks close the drawer without stealing outside focus',async()=>{
  const env=setup(async()=>response(result()));await env.refresh();
  const root=env.element('library-drawer');root.setAttribute('aria-hidden','false');
  env.documentClick([root]);env.documentClick([{id:'library-toggle-btn'}]);
  await env.fire('library-drawer','keydown',{key:'Escape'});
  assert.equal(env.drawerCalls.length,0);
  env.documentClick([{id:'note-editor-textarea'}]);
  assert.equal(env.drawerCalls.length,1);assert.equal(env.drawerCalls[0].open,false);
  assert.equal(env.drawerCalls[0].options.restoreFocus,false);
});

test('trash clicks cannot open notes or close the drawer',async()=>{
  const env=setup(async()=>response(result()));await env.refresh();await env.click({libraryView:'trash'});
  await env.click({libraryOpen:'one'});await env.doubleClick('one');
  assert.equal(env.loads.length,0);assert.equal(env.drawerCalls.length,0);
});
