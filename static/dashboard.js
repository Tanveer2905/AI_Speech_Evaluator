// static/dashboard.js
// Renders donut, bars, table and hooks up UI to /score and /score_excel
// Updated: responsive DPR-aware breakdown canvas, removed progress card references

// ----- DOM references (guarded) -----
const transcriptEl = document.getElementById('transcript');
const fileEl = document.getElementById('file');
const durationEl = document.getElementById('duration_seconds');
const scoreBtn = document.getElementById('scoreBtn');
const scoreExcelBtn = document.getElementById('scoreExcelBtn');
const downloadReportBtn = document.getElementById('downloadReport');

const donutArc = document.getElementById('donut-arc');
const donutText = document.getElementById('donut-text');
const metricWords = document.getElementById('metric_words');
const metricSentences = document.getElementById('metric_sentences');
const metricDuration = document.getElementById('metric_duration');
const resultsBody = document.getElementById('results_body');

const breakdownCanvas = document.getElementById('breakdownChart');

// Set avatar image to the uploaded local file if present
try {
  const avatarImg = document.querySelector('.avatar img');
  if (avatarImg) {
    avatarImg.src = '/mnt/data/ChatGPT Image Nov 23, 2025, 03_53_13 PM.png';
  }
} catch (e) { /* ignore */ }

// ----- Donut drawing (SVG) -----
function drawDonut(percent) {
  if (!donutArc || !donutText) return;
  const radius = 40;
  const circ = 2 * Math.PI * radius;
  const visible = Math.max(0, Math.min(1, percent/100)) * circ;
  donutArc.setAttribute('stroke-dasharray', `${visible} ${circ - visible}`);
  donutText.textContent = (Number.isFinite(percent) ? Math.round(percent) : '--');
}

// ----- Canvas helpers -----
function resizeBreakdownCanvas(canvas, displayedHeightPx = 200) {
  if (!canvas) return null;
  canvas.style.height = displayedHeightPx + "px";
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(100, rect.width);
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(displayedHeightPx * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
}

function drawRoundedRect(ctx, x, y, w, h, r) {
  const radius = Math.min(r, h/2, w/2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
  ctx.fill();
}

function drawBreakdown(bands) {
  const canvas = document.getElementById('breakdownChart');
  if (!canvas || !Array.isArray(bands)) return;
  const displayedHeight = 200;
  const ctx = resizeBreakdownCanvas(canvas, displayedHeight);
  if (!ctx) return;

  const cssWidth = canvas.getBoundingClientRect().width;
  const leftLabelX = 12;
  const barLeft = 180;
  const barRightPadding = 28;
  const barFullWidth = Math.max(120, cssWidth - barLeft - barRightPadding);
  const barHeight = 18;
  const gap = 18;
  const topPadding = 20;
  const labelFont = '13px Inter, Arial, sans-serif';
  const valueFont = '12px Inter, Arial, sans-serif';

  ctx.clearRect(0, 0, cssWidth, displayedHeight);
  ctx.textBaseline = 'middle';

  bands.forEach((b, i) => {
    const y = topPadding + i * (barHeight + gap);

    ctx.fillStyle = '#49626b';
    ctx.font = labelFont;
    let label = String(b.label || '');
    const maxLabelWidth = barLeft - 24;
    if (ctx.measureText(label).width > maxLabelWidth) {
      while (label.length && ctx.measureText(label + '…').width > maxLabelWidth) {
        label = label.slice(0, -1);
      }
      label += '…';
    }
    ctx.fillText(label, leftLabelX, y + barHeight / 2);

    const bgX = barLeft;
    const bgY = y;
    const bgW = barFullWidth;
    ctx.fillStyle = '#eef6f8';
    drawRoundedRect(ctx, bgX, bgY, bgW, barHeight, barHeight / 2);

    const value = Number(b.value || 0);
    const maxv = Number(b.max || 1);
    const frac = (maxv > 0) ? Math.max(0, Math.min(1, value / maxv)) : 0;
    const fgW = Math.round(bgW * frac);

    const grad = ctx.createLinearGradient(bgX, 0, bgX + Math.max(1, fgW), 0);
    grad.addColorStop(0, '#66d3c9'); grad.addColorStop(1, '#2b97c9');
    ctx.fillStyle = grad;
    drawRoundedRect(ctx, bgX, bgY, fgW, barHeight, barHeight / 2);

    ctx.font = valueFont;
    const valueText = (b.displayValue !== undefined) ? String(b.displayValue) : String(b.value);
    const valueTextWidth = ctx.measureText(valueText).width;
    if (fgW > valueTextWidth + 12) {
      ctx.fillStyle = '#ffffff';
      ctx.fillText(valueText, bgX + fgW - valueTextWidth - 8, y + barHeight / 2);
    } else {
      ctx.fillStyle = '#0b1220';
      ctx.fillText(valueText, bgX + fgW + 8, y + barHeight / 2);
    }
  });

  window.__lastBreakdownBands = bands;
}

// simple debounce
function debounce(fn, wait=100){ let t; return (...args)=>{ clearTimeout(t); t = setTimeout(()=>fn(...args), wait); }; }
window.addEventListener('resize', debounce(()=> { if (window.__lastBreakdownBands) drawBreakdown(window.__lastBreakdownBands); }, 120));

// helper: POST form
async function postForm(path, form) {
  const res = await fetch(path, { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json().catch(()=>({error: res.statusText}));
    throw new Error(err.error || res.statusText);
  }
  return res;
}

// Score button behavior
if (scoreBtn) {
  scoreBtn.addEventListener('click', async () => {
    scoreBtn.disabled = true;
    const prevText = scoreBtn.textContent;
    scoreBtn.textContent = 'Scoring…';
    try {
      const form = new FormData();
      form.append('transcript', transcriptEl ? transcriptEl.value || '' : '');
      if (durationEl && durationEl.value) form.append('duration_seconds', durationEl.value);
      if (fileEl && fileEl.files && fileEl.files.length) form.append('file', fileEl.files[0]);
      const res = await postForm('/score', form);
      const data = await res.json();
      renderData(data);
    } catch (e) {
      alert('Scoring error: ' + (e.message || e));
    } finally {
      scoreBtn.disabled = false;
      scoreBtn.textContent = prevText || 'Score';
    }
  });
}

// Excel download
if (scoreExcelBtn) {
  scoreExcelBtn.addEventListener('click', async () => {
    try {
      const form = new FormData();
      form.append('transcript', transcriptEl ? transcriptEl.value || '' : '');
      if (durationEl && durationEl.value) form.append('duration_seconds', durationEl.value);
      if (fileEl && fileEl.files && fileEl.files.length) form.append('file', fileEl.files[0]);
      const res = await fetch('/score_excel', { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json().catch(()=>({error: res.statusText}));
        throw new Error(err.error || res.statusText);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'scoring_results.xlsx';
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) {
      alert('Download error: ' + (e.message || e));
    }
  });
}

if (downloadReportBtn) {
  downloadReportBtn.addEventListener('click', () => scoreExcelBtn && scoreExcelBtn.click());
}

// Render server data into UI
function renderData(data) {
  const overall = Number(data?.overall_score) || 0;
  drawDonut(overall);

  if (metricWords) metricWords.textContent = data?.word_count ?? 0;
  if (metricSentences) metricSentences.textContent = data?.sentence_count ?? 0;
  if (metricDuration) metricDuration.textContent = (data?.duration_seconds_used === null || data?.duration_seconds_used === undefined) ? 'Not provided' : data?.duration_seconds_used;

  const bands = (data?.per_criterion || []).map(p => ({
    label: p.criterion,
    value: Number(p.score || 0),
    max: Number(p.max_score || 1),
    displayValue: (p.score !== undefined ? p.score : '')
  }));
  if (bands.length) {
    window.__lastBreakdownBands = bands;
    drawBreakdown(bands);
  }

  if (resultsBody) {
    resultsBody.innerHTML = '';
    (data?.per_criterion || []).forEach(p => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${escapeHtml(p.criterion)}</td><td style="font-weight:700">${escapeHtml(String(p.score))}</td><td>${escapeHtml(String(p.max_score))}</td><td class="feedback">${escapeHtml(p.feedback || '')}</td>`;
      resultsBody.appendChild(tr);
    });

    const foot1 = document.createElement('tr');
    foot1.innerHTML = `<td>Sentence Count</td><td>${escapeHtml(String(data?.sentence_count ?? ''))}</td><td></td><td></td>`;
    const foot2 = document.createElement('tr');
    foot2.innerHTML = `<td>Duration (seconds)</td><td>${escapeHtml(String(data?.duration_seconds_used ?? ''))}</td><td></td><td></td>`;
    resultsBody.appendChild(foot1);
    resultsBody.appendChild(foot2);
  }
}

function escapeHtml(s){
  if (s === null || s === undefined) return '';
  return String(s)
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
    .replaceAll('"','&quot;')
    .replaceAll("'",'&#39;');
}

// If the server injected initial data, render it
if (window.__initialScoringData) {
  try { renderData(window.__initialScoringData); } catch(e) {}
}
