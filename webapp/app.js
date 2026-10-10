const tbody = document.getElementById('tbody');
const selInfo = document.getElementById('selInfo');
const statusEl = document.getElementById('status');
const copyNidBtn = document.getElementById('copyNid');
const copyDobBtn = document.getElementById('copyDob');
let records = [];
let selected = -1;

function maskNid(nid) {
  if (nid.length <= 4) return '*'.repeat(nid.length);
  return '*'.repeat(nid.length - 4) + nid.slice(-4);
}
function isValidDate(y, m, d) {
  const dt = new Date(Number(y), Number(m) - 1, Number(d));
  return dt.getFullYear() === Number(y) && (dt.getMonth() + 1) === Number(m) && dt.getDate() === Number(d);
}
function render() {
  tbody.innerHTML = '';
  records.forEach((r, i) => {
    const tr = document.createElement('tr');
    if (i === selected) tr.className = 'selected';
    tr.innerHTML = `<td>${i + 1}</td><td>${maskNid(r.nid)}</td><td>${r.day}/${r.month}/${r.year}</td>`;
    tr.style.cursor = 'pointer';
    tr.onclick = () => { selected = i; updateSel(); render(); };
    tbody.appendChild(tr);
  });
  updateSel();
}
function updateSel() {
  if (selected < 0 || selected >= records.length) {
    selInfo.textContent = 'Kono row select kora hoyni.';
    copyNidBtn.disabled = true; copyDobBtn.disabled = true; return;
  }
  const r = records[selected];
  selInfo.textContent = `Selected: NID ${maskNid(r.nid)} | DOB ${r.day}/${r.month}/${r.year} — Copy kore official page-e nije paste koro.`;
  copyNidBtn.disabled = false; copyDobBtn.disabled = false;
}
async function copyText(t, label) {
  try { await navigator.clipboard.writeText(t); statusEl.textContent = `${label} clipboard-e copy hoyeche. Securely handle koro.`; }
  catch { statusEl.textContent = 'Clipboard copy fail — browser permission daw.'; }
}
function parseCSV(text) {
  const lines = text.replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  if (lines.length < 2) throw new Error('CSV-te header + minimum 1 ta data row lagbe.');
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
  const need = ['nid', 'day', 'month', 'year'];
  for (const f of need) if (!headers.includes(f)) throw new Error('CSV header-te nid,day,month,year thakte hobe.');
  const idx = Object.fromEntries(headers.map((h, i) => [h, i]));
  const out = [];
  for (let ln = 2; ln <= lines.length; ln++) {
    const line = lines[ln - 1].trim();
    if (!line) continue;
    const cols = line.split(',').map(c => c.trim());
    const v = { nid: cols[idx['nid']] || '', day: cols[idx['day']] || '', month: cols[idx['month']] || '', year: cols[idx['year']] || '' };
    if (!v.nid || !v.day || !v.month || !v.year) throw new Error(`Row ${ln}: NID, day, month, year sob lagbe.`);
    if (!/^\d+$/.test(v.nid)) throw new Error(`Row ${ln}: NID numeric hote hobe.`);
    if (!/^\d+$/.test(v.day) || !/^\d+$/.test(v.month) || !/^\d+$/.test(v.year)) throw new Error(`Row ${ln}: day/month/year numeric hote hobe.`);
    if (!isValidDate(v.year, v.month, v.day)) throw new Error(`Row ${ln}: invalid date of birth.`);
    out.push(v);
  }
  if (!out.length) throw new Error('Kono valid data row pai ni.');
  return out;
}
document.getElementById('csvFile').addEventListener('change', async (e) => {
  const f = e.target.files[0]; if (!f) return;
  try { records = parseCSV(await f.text()); selected = -1; render(); statusEl.textContent = `${records.length} ta record load hoyeche (memory only).`; }
  catch (err) { alert(err.message); }
});
document.getElementById('clearBtn').onclick = () => { records = []; selected = -1; render(); statusEl.textContent = 'List clear kora hoyeche.'; };
document.getElementById('sampleBtn').onclick = () => {
  records = [{ nid: '1234567890', day: '01', month: '01', year: '1990' }, { nid: '9876543210', day: '15', month: '08', year: '1985' }];
  selected = -1; render(); statusEl.textContent = 'Demo sample load hoyeche (real data na).';
};
copyNidBtn.onclick = () => { if (selected >= 0) copyText(records[selected].nid, 'NID'); };
copyDobBtn.onclick = () => { if (selected >= 0) { const r = records[selected]; copyText(`${r.day}/${r.month}/${r.year}`, 'Date of birth'); } };
render();
