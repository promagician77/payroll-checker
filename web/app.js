/* Payroll file check - the page. React without a build step, so there is
   nothing to compile: the files in this folder are exactly what runs. */
const { useState, useEffect, useMemo, useRef } = React;
const html = htm.bind(React.createElement);

const SAMPLES = [
  { label: 'Try the sample file', path: '/web/sample/payroll_sample.csv', name: 'payroll_sample.csv' },
  { label: 'Try an Excel-style export', path: '/web/sample/excel_export.csv', name: 'excel_export.csv' },
];
const SETTINGS_FIELDS = [
  ['overtime_max_hours', 'Flag overtime above (hours)'],
  ['overtime_max_pct_of_contracted', 'Or above this % of contracted hours'],
  ['minimum_hourly_rate', 'Minimum hourly rate (€)'],
  ['max_avg_weekly_hours', 'Average weekly hours limit'],
  ['unrecorded_hours_tolerance', 'Allowed hours over contract without overtime'],
];

function App() {
  const [file, setFile] = useState(null); // { blob, name }
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [settings, setSettings] = useState(null);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  useEffect(() => { fetch('/api/settings').then((r) => r.json()).then(setSettings).catch(() => {}); }, []);

  async function check(f = file, s = settings) {
    if (!f) return;
    setLoading(true); setError('');
    const body = new FormData();
    body.append('file', f.blob, f.name);
    if (s) body.append('settings', JSON.stringify(s));
    try {
      const res = await fetch('/api/validate', { method: 'POST', body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'The check failed.');
      setResult(data); setFilter('all'); setQuery('');
    } catch (e) { setError(e.message || 'The check failed.'); setResult(null); }
    setLoading(false);
  }
  function pick(blob, name) { const f = { blob, name }; setFile(f); check(f); }
  async function loadSample(s) {
    const blob = await (await fetch(s.path)).blob();
    pick(blob, s.name);
  }
  function download() {
    const blob = new Blob([result.issues_csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (file.name.replace(/\.csv$/i, '') || 'payroll') + '_issues.csv';
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return html`
    <header><div class="wrap">
      <h1>Payroll file check</h1>
      <p>Upload the monthly CSV, see what needs attention, and download the list.</p>
      <div class="privacy">Files are checked in memory and never saved. On this demo site, please use the samples or a copy without real names - the version you run on your own computer never sends data anywhere.</div>
    </div></header>
    <main class="wrap">
      <${Drop} onFile=${pick} loading=${loading} />
      <div class="row center" style=${{ marginTop: '10px' }}>
        ${SAMPLES.map((s) => html`<button class="link" key=${s.path} onClick=${() => loadSample(s)} disabled=${loading}>${s.label}</button>`)}
      </div>
      ${loading && html`<p class="fileline"><span class="spinner"></span>Checking ${file && file.name}...</p>`}
      ${error && html`<div class="alert red">${error}</div>`}
      ${result && !loading && html`<${Result} r=${result} filter=${filter} setFilter=${setFilter} query=${query} setQuery=${setQuery} onDownload=${download} />`}
      ${settings && html`<${Settings} settings=${settings} onApply=${(s) => { setSettings(s); check(file, s); }} hasFile=${!!file} />`}
      <${Notes} />
    </main>`;
}

function Drop({ onFile, loading }) {
  const [over, setOver] = useState(false);
  const input = useRef(null);
  const take = (f) => { if (f) onFile(f, f.name); };
  return html`
    <div class=${'drop' + (over ? ' over' : '')}
      onDragOver=${(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave=${() => setOver(false)}
      onDrop=${(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files[0]); }}>
      <b>Drop your payroll CSV here</b>
      <p>Comma or semicolon separated, straight from Excel or your payroll system.</p>
      <button class="btn pri" onClick=${() => input.current.click()} disabled=${loading}>Choose a file</button>
      <input ref=${input} type="file" accept=".csv,text/csv" hidden onChange=${(e) => { take(e.target.files[0]); e.target.value = ''; }} />
    </div>`;
}

function Result({ r, filter, setFilter, query, setQuery, onDownload }) {
  const s = r.summary, f = r.file;
  const rows = useMemo(() => r.rows.filter((row) => {
    if (filter === 'error' || filter === 'warning') { if (row.severity !== filter) return false; }
    else if (filter !== 'all' && !row.issues.some((i) => i.check === filter)) return false;
    const q = query.trim().toLowerCase();
    return !q || row.employee_id.toLowerCase().includes(q) || row.store.toLowerCase().includes(q);
  }), [r, filter, query]);
  const found = Object.keys(f.columns_found).length;

  return html`
    <p class="fileline"><b>${f.name}</b> - ${s.total_rows} rows, ${f.delimiter}-separated, ${f.encoding}, ${found} columns recognised${f.blank_rows_skipped ? `, ${f.blank_rows_skipped} blank row${f.blank_rows_skipped === 1 ? '' : 's'} skipped` : ''}.</p>
    ${f.problems.length > 0 && html`<div class="alert amber"><b>About the file itself</b><ul>${f.problems.map((p) => html`<li key=${p}>${p}</li>`)}</ul></div>`}
    <div class="cards">
      <div class="card"><span>Total rows</span><b>${s.total_rows}</b></div>
      <div class="card ok"><span>OK</span><b>${s.ok}</b></div>
      <div class=${'card' + (s.with_issues ? ' bad' : '')}><span>Need attention</span><b>${s.with_issues}</b><small>${s.errors} error${s.errors === 1 ? '' : 's'}, ${s.warnings} warning${s.warnings === 1 ? '' : 's'}</small></div>
      <div class="card dl">
        <button class="btn pri" onClick=${onDownload} disabled=${!s.with_issues}>Download issues CSV</button>
        <small>${s.with_issues ? `${s.with_issues} rows, original data plus an "Issue reason" column.` : 'Nothing to download - every row passed.'}</small>
      </div>
    </div>
    ${s.with_issues === 0 ? html`<div class="alert" style=${{ background: 'var(--greenbg)', color: 'var(--green)' }}>Every row passed the checks.</div>` : html`
    <div class="grid">
      <aside class="side">
        <h2>By check</h2>
        <ul class="checks">
          <li><button aria-pressed=${filter === 'all'} onClick=${() => setFilter('all')}>All issues<span>${s.with_issues}</span></button></li>
          ${r.checks.map((c) => html`<li key=${c.check}><button aria-pressed=${filter === c.check} onClick=${() => setFilter(c.check)}>${c.name}<span>${c.rows}</span></button></li>`)}
        </ul>
        <h2>By store</h2>
        <table class="stores"><thead><tr><th>Store</th><th>Rows</th><th>Issues</th></tr></thead><tbody>
          ${r.stores.map((st) => html`<tr key=${st.store}><td>${st.store}</td><td class="num">${st.rows}</td><td class="num">${st.issues}</td></tr>`)}
        </tbody></table>
      </aside>
      <section class="list">
        <div class="tools">
          <div class="seg">
            ${[['all', 'All'], ['error', 'Errors'], ['warning', 'Warnings']].map(([k, l]) => html`<button key=${k} aria-pressed=${filter === k} onClick=${() => setFilter(k)}>${l}</button>`)}
          </div>
          <input class="search" placeholder="Search employee ID or store" value=${query} onInput=${(e) => setQuery(e.target.value)} aria-label="Search" />
        </div>
        <div class="tablewrap"><table>
          <thead><tr><th>Row</th><th>Employee ID</th><th>Store</th><th>Status</th><th>What to check</th></tr></thead>
          <tbody>
            ${rows.length === 0 && html`<tr><td colspan="5" class="empty">No rows match.</td></tr>`}
            ${rows.map((row) => html`<tr key=${row.row}>
              <td class="num">${row.row}</td><td>${row.employee_id || '-'}</td><td>${row.store || '-'}</td>
              <td><span class=${'chip ' + row.severity}>${row.severity === 'error' ? 'Error' : 'Warning'}</span></td>
              <td><ul class="reasons">${row.issues.map((i, n) => html`<li key=${n} class=${i.severity}>${i.message}</li>`)}</ul></td>
            </tr>`)}
          </tbody>
        </table></div>
      </section>
    </div>`}`;
}

function Settings({ settings, onApply, hasFile }) {
  const [draft, setDraft] = useState(settings);
  useEffect(() => setDraft(settings), [settings]);
  const set = (k, v) => setDraft({ ...draft, [k]: v });
  return html`
    <details class="settings">
      <summary>Check settings</summary>
      <div class="sgrid">
        ${SETTINGS_FIELDS.map(([k, l]) => html`<label key=${k}>${l}<input type="number" step="0.01" value=${draft[k]} onInput=${(e) => set(k, parseFloat(e.target.value) || 0)} /></label>`)}
        <label class="tick"><input type="checkbox" checked=${draft.worked_includes_overtime} onChange=${(e) => set('worked_includes_overtime', e.target.checked)} /> Worked hours already include overtime</label>
        <label class="tick"><input type="checkbox" checked=${draft.blank_optional_means_zero} onChange=${(e) => set('blank_optional_means_zero', e.target.checked)} /> Blank overtime, sick, holiday, or bonus means 0</label>
        <div class="row"><button class="btn pri" onClick=${() => onApply(draft)}>${hasFile ? 'Apply and check again' : 'Apply'}</button></div>
      </div>
    </details>`;
}

function Notes() {
  return html`
    <section class="notes">
      <h2>A few notes from me</h2>
      <p>I built this first version from your post so you can try it before we talk. It covers every check you listed, plus a few that tend to catch real payroll mistakes. The two sample files have deliberate problems in them, so you can see each check fire.</p>
      <h3>Choices I made that you might want differently</h3>
      <ul>
        <li>"Unusually high overtime" means more than 40 hours, or more than 25% of contracted hours. Both are easy to change above.</li>
        <li>I assumed worked hours already include overtime. If your files list overtime on top, one tick box switches that.</li>
        <li>A blank overtime, sick, holiday, or bonus cell counts as 0, not as missing. Blank hours, store, ID, or rate is always an error.</li>
        <li>The minimum wage and 48-hour week checks are warnings, since youth rates and averaging periods can make them fine.</li>
      </ul>
      <h3>What I'd ask you</h3>
      <ul>
        <li>Could you share the column headers from a real file? The tool already accepts common spellings like "Holiday Hours" or "Emp No", but I'd match yours exactly.</li>
        <li>Is one row one employee for the month, or can someone appear once per store? That decides whether a repeated ID is always an error.</li>
      </ul>
      <p>On your own computer this runs with one double-click and only needs Python - no Node, no database, and your payroll data never leaves the machine. - Josinaldo</p>
    </section>`;
}

ReactDOM.createRoot(document.getElementById('root')).render(html`<${App} />`);
