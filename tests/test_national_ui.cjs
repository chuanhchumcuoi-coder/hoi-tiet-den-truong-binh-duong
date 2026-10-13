const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(__dirname + '/../templates/index.html', 'utf8');
const start = html.indexOf('    function renderNationalWeather(payload) {');
const end = html.indexOf('    async function refreshNationalWeather()', start);
assert(start > 0 && end > start);
const code = html.slice(start, end);
const host = { innerHTML: '', className: '' };
const sandbox = {
  document: { getElementById: id => id === 'nationalWeatherBody' ? host : null },
  vietnamDate: input => input ? new Date(input) : null,
  formatVietnamTime: () => '12:00 10/10/2026',
  escapeHtml: str => String(str ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;'),
  Date, Number, String, Math,
};
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const now = new Date();
const payload = { status:'fresh', temperature_c:32, humidity_pct:65, condition:'Ít mây, trời nắng', wind_text:'Gió đông đông nam', observed_at:new Date(now-3600000).toISOString() };
sandbox.renderNationalWeather(payload);
assert(host.className.includes('fresh'));
assert(host.innerHTML.includes('32°C'));
assert(host.innerHTML.includes('Ít mây'));
sandbox.renderNationalWeather({...payload, observed_at:new Date(now-12*3600000).toISOString()});
assert(host.className.includes('stale'));
assert(host.innerHTML.includes('đã quá cũ'));
sandbox.renderNationalWeather({status:'unavailable'});
assert(host.className.includes('unavailable'));
assert(host.innerHTML.includes('Chưa thể lấy dữ liệu'));
sandbox.renderNationalWeather({...payload, condition:'<script>alert(1)</script>'});
assert(!host.innerHTML.includes('<script>'));
console.log('National UI: fresh, stale, unavailable, HTML escaping — PASS');
