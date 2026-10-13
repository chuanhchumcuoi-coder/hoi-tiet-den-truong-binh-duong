'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname,'../templates/index.html'),'utf8');
function extract(name) {
  const re = new RegExp('^    (?:async )?function ' + name + '\\(', 'm');
  const match = re.exec(html);
  assert.ok(match, 'Missing function: ' + name);
  const end = html.indexOf('\n    }\n', match.index);
  assert.notEqual(end,-1, 'Missing end: ' + name);
  return html.slice(match.index, end+7);
}
const s={
  homePosition:{lat:11.1111,lon:106.2222},studentPosition:null,
  selectedId:'school-a',schoolById:new Map([['school-a',{id:'school-a',name:'Trường A'}]]),
  weatherData:null,weatherPendingRequests:new Map(),weatherStudentSerial:0,
  weatherSchoolSerial:0,weatherLastCompletedStudentKey:null,weatherLastCompletedSchoolKey:null
};
const el={routeDirection:{value:'home_to_school'},weatherContent:{hidden:false},weatherEmpty:{hidden:true}};
const urls=[];
const context=vm.createContext({
  state:s,el,Number,Math,Date,console,URLSearchParams,AbortController,setTimeout,clearTimeout,
  window:{setTimeout,clearTimeout},
  currentFiveMinuteWindow:()=>({update:new Date('2026-10-10T00:05:00Z')}),
  updateWeatherReadiness:()=>true,
  renderWeatherCardsFromState:()=>{},setWeatherStatus:()=>{},
  fetchJson:async url=>{
    urls.push(new URL(url,'https://example.test'));
    return {student:{weather:{current:{temperature_c:30}}},school:{weather:{current:{temperature_c:29}}}};
  },
  renderWeather:()=>{}
});
vm.runInContext(['isValidCoordinate','hasSavedHome','weatherDeparture','selectedSchool','refreshWeatherIfReady'].map(extract).join('\n')+ '\nthis.f={weatherDeparture,refreshWeatherIfReady};',context);
(async()=>{
  await context.f.refreshWeatherIfReady('school');
  assert.equal(urls.length,1);
  assert.equal(urls[0].searchParams.get('user_lat'),'11.1111');
  assert.equal(urls[0].searchParams.get('user_lon'),'106.2222');
  assert.equal(urls[0].searchParams.get('school_id'),'school-a');
  assert.equal(s.weatherPendingRequests.size,0);
  console.log('PASS: selecting a school fetches weather for both saved home and school');

  // Switching to GPS switches the weather source; no stale home can masquerade as GPS.
  s.studentPosition={lat:11.5555,lon:106.6666};
  el.routeDirection.value='current_to_school';
  await context.f.refreshWeatherIfReady('direction');
  assert.equal(urls.length,2);
  assert.equal(urls[1].searchParams.get('user_lat'),'11.5555');
  assert.equal(urls[1].searchParams.get('user_lon'),'106.6666');
  console.log('PASS: GPS mode uses GPS for weather instead of the home coordinate');

  // A saved home is not described as a current GPS location.
  el.routeDirection.value='home_to_school';
  assert.equal(context.f.weatherDeparture().kind,'home');
  assert.match(context.f.weatherDeparture().description, /không phải GPS hiện tại/);
  console.log('PASS: saved home is explicitly labeled as stored coordinates');
})().catch(e=>{console.error(e);process.exitCode=1});
