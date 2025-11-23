// main.js - handles UI interactions and API calls

// helper: update live word count
const txtEl = document.getElementById('transcript');
const wcEl = document.getElementById('live_wordcount');
function updateWordCount(){
  const t = txtEl.value.trim();
  const tokens = t.length ? t.match(/\b\w+\b/g) || [] : [];
  wcEl.textContent = tokens.length;
}
txtEl.addEventListener('input', updateWordCount);
updateWordCount();

async function postForm(path, formData){
  const res = await fetch(path, { method: "POST", body: formData });
  return res;
}

function showStatus(msg, isError){
  // small ephemeral status: you can enhance to toasts
  const s = document.getElementById('status') || document.createElement('div');
  if (!s.id) { s.id = 'status'; document.body.appendChild(s); }
  s.textContent = msg;
  s.style.color = isError ? '#b91c1c' : '#0b1220';
  setTimeout(()=>{ if(!isError) s.textContent = ''; }, 4500);
}

document.getElementById('scoreBtn').addEventListener('click', async ()=>{
  showStatus('Scoring…');
  const transcript = document.getElementById('transcript').value;
  const duration = document.getElementById('duration_seconds').value;
  const fileInput = document.getElementById('file');
  const form = new FormData();
  form.append('transcript', transcript);
  if (duration) form.append('duration_seconds', duration);
  if (fileInput.files.length) form.append('file', fileInput.files[0]);

  try{
    const res = await postForm('/score', form);
    if (!res.ok){
      const err = await res.json().catch(()=>({error:res.statusText}));
      showStatus('Error: ' + (err.error||res.statusText), true);
      return;
    }
    const data = await res.json();
    showStatus('Scored successfully');
    renderResults(data);
  }catch(e){
    showStatus('Network error: ' + e.message, true);
  }
});

document.getElementById('scoreExcelBtn').addEventListener('click', async ()=>{
  showStatus('Preparing Excel…');
  const transcript = document.getElementById('transcript').value;
  const duration = document.getElementById('duration_seconds').value;
  const fileInput = document.getElementById('file');
  const form = new FormData();
  form.append('transcript', transcript);
  if (duration) form.append('duration_seconds', duration);
  if (fileInput.files.length) form.append('file', fileInput.files[0]);

  try{
    const res = await fetch('/score_excel', { method: "POST", body: form });
    if (!res.ok){
      const err = await res.json().catch(()=>({error:res.statusText}));
      showStatus('Error: ' + (err.error||res.statusText), true);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'scoring_results.xlsx';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showStatus('Excel downloaded');
  }catch(e){
    showStatus('Download error: ' + e.message, true);
  }
});

// render results into the right panel
function renderResults(data){
  document.getElementById('overall_score').textContent = data.overall_score ?? '—';
  document.getElementById('metric_words').textContent = data.word_count ?? 0;
  document.getElementById('metric_sentences').textContent = data.sentence_count ?? 0;
  document.getElementById('metric_duration').textContent = (data.duration_seconds_used === null || data.duration_seconds_used === undefined) ? 'Not provided' : data.duration_seconds_used;

  const tbody = document.querySelector('#resultTable tbody');
  tbody.innerHTML = '';
  (data.per_criterion || []).forEach(r=>{
    const tr = document.createElement('tr');
    const crit = document.createElement('td'); crit.textContent = r.criterion;
    const score = document.createElement('td'); score.textContent = r.score;
    const max = document.createElement('td'); max.textContent = r.max_score ?? '';
    tr.appendChild(crit); tr.appendChild(score); tr.appendChild(max);
    tbody.appendChild(tr);

    // add small feedback row
    const fr = document.createElement('tr');
    const fcell = document.createElement('td');
    fcell.colSpan = 3;
    fcell.className = 'feedback';
    fcell.style.background = '#fbfdff';
    fcell.style.fontSize = '13px';
    fcell.style.padding = '8px 12px';
    fcell.textContent = r.feedback || '';
    fr.appendChild(fcell);
    tbody.appendChild(fr);
  });

  // totals and summary
  const detail = document.getElementById('detail_feedback');
  detail.innerHTML = `<div class="muted">Total: ${data.totals?.attained ?? ''} / ${data.totals?.possible ?? ''} — Words: ${data.word_count ?? 0} — Sentences: ${data.sentence_count ?? 0}</div>`;
}
