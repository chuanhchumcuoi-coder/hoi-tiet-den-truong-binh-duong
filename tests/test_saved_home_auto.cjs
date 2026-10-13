'use strict';
// Zero-dependency behavioral checks against the actual function bodies in index.html.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');
const functions = [
  'isValidCoordinate', 'hasSavedHome', 'schoolSelectionHint', 'updateJourneySummary',
  'updateHomeControls', 'loadSavedHome', 'saveCurrentAsHome', 'deleteSavedHome',
  'weatherDeparture', 'hasDeparturePosition', 'selectedSchool', 'refreshRoute', 'selectSchool'
];
function extract(name) {
  const regex = new RegExp('^    (?:async )?function ' + name + '\\(', 'm');
  const match = regex.exec(html);
  assert.ok(match, `Missing function ${name}`);
  const end = html.indexOf('\n    }\n', match.index);
  assert.ok(end !== -1, `Missing end of ${name}`);
  return html.slice(match.index, end + 7);
}
const st = {
  homePosition: null, studentPosition: null, selectedId: null,
  schoolById: new Map([['school-a', {id:'school-a',name:'Trường kiểm tra',short_name:'THPT Thử',address:'Trường A'}]]),
  markers:new Map(),routeLastKey:null,routeData:null,routeController:null,
  routeRequestSerial:0, routeClientCache:new Map(),routeCacheTtlMs:600000,
  routeLayer:null, homeMarker:null
};
const storage = new Map();
const calls = [];
const cl = {toggle(){},add(){},remove(){}};
const element = () => ({classList:cl,textContent:'',disabled:false,hidden:false,title:'',value:'',innerHTML:''});
const el = {
  routeDirection:{value:'current_to_school',options:[
    {value:'current_to_school',disabled:false},
    {value:'home_to_school',disabled:true},
    {value:'school_to_home',disabled:true}
  ]},
  routeMode:{value:'motorbike'}, routeStatus:{textContent:'',classList:cl},
  routeMetrics:{hidden:true},routeJourneySummary:{innerHTML:''},
  mapTitle:element(),mapSubtitle:element(),
  homeButton:element(),homeManageButton:element(),homeMenu:{hidden:true},
  homeMenuStatus:element(), homeUpdateMenuButton:element(),
  homeFocusMenuButton:element(),homeDeleteMenuButton:element()
};
const ctx = vm.createContext({
  state:st, el, JSON, Number, Math, Date, console, URLSearchParams, AbortController,
  setTimeout, clearTimeout,
  localStorage:{getItem:k=>storage.get(k) ?? null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  renderHomeMarker(){}, closeHomeMenu(){el.homeMenu.hidden=true},
  formatAccuracy: x=>String(x), formatSavedAt:()=>'',
  escapeHtml: s=>String(s),
  showToast: msg=>calls.push(['toast',msg]),
  invalidateDepartureWeather:()=>calls.push(['invalidate']),
  resetRoute:msg=>{calls.push(['reset',msg]);st.routeRequestSerial++;st.routeLastKey=null;st.routeData=null;},
  getClientRouteCache:()=>null, putClientRouteCache:()=>{},
  applyRouteData:(data)=>{st.routeData=data;calls.push(['routeData',data])},
  renderSchoolList:()=>{},updateSelectedMarkerIcons:()=>{},
  updateWeatherReadiness:()=>{},refreshWeatherIfReady:reason=>calls.push(['weather',reason]),
  map:{flyTo(){}},
  fetch:async url=>{
    calls.push(['fetch',url]);
    return {ok:true,json:async()=>({ok:true,coordinates:[[11.12,106.65],[11.2,106.7]],
      provider:'test',distance_km:5,duration_minutes:10})};
  }
});
const code = "const HOME_STORAGE_KEY = 'duong_den_truong_home_gps_v10';\n" + functions.map(extract).join('\n') +
  '\nthis.f = {' + functions.join(',') + '};';
vm.runInContext(code,ctx);
const f=ctx.f;
function routeCalls() {return calls.filter(x=>x[0]==='fetch').map(x=>new URL(x[1],'https://example.com'));}
function clearCalls(){calls.length=0}
async function tick(){await new Promise(resolve=>setTimeout(resolve,5));}

(async()=>{
  // 1. No saved home: GPS stays the default.
  f.loadSavedHome();
  assert.equal(el.routeDirection.value,'current_to_school');
  assert.equal(f.weatherDeparture(),null);

  // 2. Return visit with saved home and no GPS: school selection alone creates route.
  storage.set('duong_den_truong_home_gps_v10',JSON.stringify({lat:11.12345,lon:106.65432,accuracy:8}));
  f.loadSavedHome();
  assert.equal(el.routeDirection.value,'home_to_school');
  assert.equal(el.routeDirection.options[1].disabled,false);
  assert.equal(f.weatherDeparture().kind,'home');
  assert.ok(f.schoolSelectionHint().includes('chỉ cần chọn trường'));
  f.selectSchool('school-a');
  await tick();
  assert.equal(routeCalls().length,1);
  assert.equal(routeCalls()[0].searchParams.get('direction'),'home_to_school');
  assert.equal(routeCalls()[0].searchParams.get('home_lat'),'11.12345');
  assert.equal(routeCalls()[0].searchParams.get('school_id'),'school-a');
  assert.equal(routeCalls()[0].searchParams.get('user_lat'),null);
  assert.ok(calls.some(x=>x[0]==='weather' && x[1]==='school'));
  console.log('PASS: saved home + school selection triggers a route without GPS');

  // 3. User explicitly chooses current location: must require GPS.
  clearCalls();el.routeDirection.value='current_to_school';
  await f.refreshRoute(true);
  assert.equal(routeCalls().length,0);
  assert.equal(f.weatherDeparture(),null);
  st.studentPosition={lat:11.3333,lon:106.7777,accuracy:15};
  await f.refreshRoute(true);
  assert.equal(routeCalls().length,1);
  assert.equal(routeCalls()[0].searchParams.get('direction'),'current_to_school');
  assert.equal(routeCalls()[0].searchParams.get('user_lat'),'11.3333');
  console.log('PASS: current-location mode stays separate and demands GPS');

  // 4. Saving home sets home route by default and recalculates automatically.
  clearCalls();st.studentPosition={lat:11.4444,lon:106.8888,accuracy:8};
  f.saveCurrentAsHome();await tick();
  assert.equal(el.routeDirection.value,'home_to_school');
  assert.equal(JSON.parse(storage.get('duong_den_truong_home_gps_v10')).lat,11.4444);
  assert.equal(routeCalls()[0].searchParams.get('direction'),'home_to_school');
  assert.equal(f.weatherDeparture().kind,'home');
  console.log('PASS: saving home automatically enables home origin');

  // 5. Deleting home falls back to current GPS; no old home remains.
  clearCalls();f.deleteSavedHome();await tick();
  assert.equal(storage.has('duong_den_truong_home_gps_v10'),false);
  assert.equal(el.routeDirection.value,'current_to_school');
  assert.equal(f.hasSavedHome(),false);
  assert.equal(f.weatherDeparture().kind,'gps');
  assert.equal(routeCalls()[0].searchParams.get('direction'),'current_to_school');
  console.log('PASS: deleting home invalidates it and falls back to GPS');
})().catch(err=>{console.error(err);process.exitCode=1;});
