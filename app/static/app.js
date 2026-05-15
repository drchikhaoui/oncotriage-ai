// OncoTriage — Patient intake & result display

const SEVERITY_OPTIONS = ['mild','moderate','severe'];
const SYMPTOM_DETAIL_CONFIG = {
  fever: [
    { id: 'temperature_celsius', label: 'Temperature (°C)', type: 'number', placeholder: '38.5', min: 35, max: 42, step: 0.1 },
    { id: 'duration_hours', label: 'Duration (hours)', type: 'number', placeholder: '4', min: 0 },
  ],
  pain: [
    { id: 'pain_nrs', label: 'Pain score (0–10)', type: 'range', min: 0, max: 10 },
    { id: 'uncontrolled', label: 'Unresponsive to current pain medications?', type: 'checkbox' },
  ],
  vomiting: [
    { id: 'episodes_per_24h', label: 'Episodes in last 24 hours', type: 'number', placeholder: '4', min: 0 },
  ],
  diarrhea: [
    { id: 'stools_above_baseline', label: 'Extra stools per day above normal', type: 'number', placeholder: '5', min: 0 },
  ],
  dyspnea: [
    { id: 'at_rest', label: 'Occurs even at rest (not just with exertion)?', type: 'checkbox' },
  ],
  default: [
    { id: 'severity_descriptor', label: 'Severity', type: 'select', options: SEVERITY_OPTIONS },
    { id: 'duration_hours', label: 'Duration (hours)', type: 'number', placeholder: '12', min: 0 },
  ],
};

function buildDetailField(symptom, field) {
  const fieldId = `detail-${symptom}-${field.id}`;
  if (field.type === 'checkbox') {
    return `<div class="form-group" style="display:flex;align-items:center;gap:8px;">
      <input type="checkbox" id="${fieldId}" data-symptom="${symptom}" data-key="${field.id}" style="width:auto;">
      <label for="${fieldId}" style="margin:0;font-weight:400;">${field.label}</label>
    </div>`;
  }
  if (field.type === 'select') {
    return `<div class="form-group">
      <label for="${fieldId}">${field.label}</label>
      <select id="${fieldId}" data-symptom="${symptom}" data-key="${field.id}">
        <option value="">Select…</option>
        ${field.options.map(o => `<option value="${o}">${o.charAt(0).toUpperCase() + o.slice(1)}</option>`).join('')}
      </select>
    </div>`;
  }
  if (field.type === 'range') {
    return `<div class="form-group">
      <label for="${fieldId}">${field.label}: <strong id="${fieldId}-val">5</strong></label>
      <input type="range" id="${fieldId}" min="${field.min}" max="${field.max}" value="5"
        data-symptom="${symptom}" data-key="${field.id}"
        oninput="document.getElementById('${fieldId}-val').textContent=this.value"
        style="width:100%;margin-top:4px;">
    </div>`;
  }
  return `<div class="form-group">
    <label for="${fieldId}">${field.label}</label>
    <input type="${field.type}" id="${fieldId}" placeholder="${field.placeholder || ''}"
      min="${field.min ?? ''}" max="${field.max ?? ''}" step="${field.step ?? ''}"
      data-symptom="${symptom}" data-key="${field.id}">
  </div>`;
}

function renderSymptomDetails(selectedSymptoms) {
  const container = document.getElementById('symptom-details');
  if (!selectedSymptoms.length) { container.innerHTML = ''; return; }
  let html = '';
  for (const sym of selectedSymptoms) {
    const config = SYMPTOM_DETAIL_CONFIG[sym] || SYMPTOM_DETAIL_CONFIG.default;
    const label = document.querySelector(`input[value="${sym}"]`)?.parentElement?.textContent?.trim() || sym;
    html += `<div class="card" style="margin-bottom:12px;padding:16px;">
      <div style="font-weight:600;margin-bottom:12px;font-size:14px;">${label}</div>
      <div class="form-row">
        ${config.map(f => buildDetailField(sym, f)).join('')}
      </div>
    </div>`;
  }
  container.innerHTML = html;
}

// Symptom checkbox listeners
document.querySelectorAll('input[name="symptom"]').forEach(cb => {
  cb.addEventListener('change', () => {
    const sel = [...document.querySelectorAll('input[name="symptom"]:checked')].map(x => x.value);
    renderSymptomDetails(sel);
    cb.closest('.symptom-item').classList.toggle('selected', cb.checked);
  });
});

function collectStructuredSymptoms() {
  const selected = [...document.querySelectorAll('input[name="symptom"]:checked')].map(x => x.value);
  return selected.map(sym => {
    const fields = document.querySelectorAll(`[data-symptom="${sym}"]`);
    const obj = { name: sym };
    fields.forEach(f => {
      const key = f.dataset.key;
      if (f.type === 'checkbox') obj[key] = f.checked;
      else if (f.value !== '' && f.value !== null) {
        const num = parseFloat(f.value);
        obj[key] = isNaN(num) ? f.value : num;
      }
    });
    return obj;
  });
}

// Session management
let currentSessionId = null;
async function getSession() {
  const res = await fetch('/api/intake/session');
  const data = await res.json();
  return data.session_id;
}

// Form submit
document.getElementById('intake-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errEl = document.getElementById('form-error');
  errEl.style.display = 'none';

  const freeText = document.getElementById('free-text').value.trim();
  const structuredSymptoms = collectStructuredSymptoms();

  if (!freeText && !structuredSymptoms.length) {
    errEl.textContent = 'Please describe your symptoms or select at least one from the list.';
    errEl.style.display = 'block';
    return;
  }

  const btn = document.getElementById('submit-btn');
  btn.disabled = true;
  btn.textContent = 'Assessing…';

  if (!currentSessionId) currentSessionId = await getSession();

  const payload = {
    session_id: currentSessionId,
    free_text: freeText || null,
    structured_symptoms: structuredSymptoms,
    last_chemo_date: document.getElementById('last-chemo').value || null,
    cancer_type: document.getElementById('cancer-type').value || null,
    treatment_status: document.getElementById('treatment-status').value || null,
    thrombocytopenia_history: document.getElementById('thrombocytopenia').checked,
    current_medications: [],
  };

  try {
    const res = await fetch('/api/triage/assess', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Triage assessment failed');
    }
    const result = await res.json();
    renderResult(result);
    currentSessionId = null; // reset for next assessment
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Assess Symptoms';
  }
});

function renderResult(result) {
  // Triage card
  const levelColors = { EMERGENCY: '#dc2626', URGENT: '#ea580c', ROUTINE: '#ca8a04', SELF_CARE: '#16a34a' };
  document.getElementById('triage-card-container').innerHTML = `
    <div class="triage-card ${result.triage_level}">
      <div class="triage-level-badge">
        ${result.emoji} ${result.triage_level.replace('_', ' ')}
      </div>
      <div class="triage-action">${result.action}</div>
      <div class="triage-timeframe">${result.timeframe}</div>
      ${result.llm_used ? '<div style="margin-top:10px;font-size:11px;color:var(--color-text-secondary);">✓ AI-powered symptom extraction</div>' : ''}
    </div>`;

  // Reasoning
  const list = document.getElementById('reasoning-list');
  list.innerHTML = result.reasoning_steps.map(s => `
    <li>
      <div class="step-num">${s.step}</div>
      <div class="step-content">
        ${s.finding}
        ${s.source ? `<span class="step-source">${s.source}</span>` : ''}
      </div>
    </li>`).join('');

  // CTCAE summary
  const gradeColors = { 1: '#16a34a', 2: '#ca8a04', 3: '#ea580c', 4: '#dc2626', 5: '#7c2d12' };
  document.getElementById('ctcae-summary').innerHTML = result.symptoms_graded.length ?
    `<table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead><tr>
        <th style="text-align:left;padding:8px;border-bottom:2px solid var(--color-border);">Symptom</th>
        <th style="text-align:left;padding:8px;border-bottom:2px solid var(--color-border);">CTCAE Grade</th>
        <th style="text-align:left;padding:8px;border-bottom:2px solid var(--color-border);">Description</th>
      </tr></thead>
      <tbody>
        ${result.symptoms_graded.map(g => `
          <tr>
            <td style="padding:8px;border-bottom:1px solid #f1f5f9;font-weight:500;">${g.term}</td>
            <td style="padding:8px;border-bottom:1px solid #f1f5f9;">
              <span style="color:${gradeColors[g.ctcae_grade]};font-weight:700;">Grade ${g.ctcae_grade}</span>
              <span style="color:var(--color-text-secondary);font-size:11px;margin-left:4px;">(${g.severity})</span>
            </td>
            <td style="padding:8px;border-bottom:1px solid #f1f5f9;color:var(--color-text-secondary)">${g.ctcae_description}</td>
          </tr>`).join('')}
      </tbody>
    </table>` : '<p style="color:var(--color-text-secondary);font-size:13px;">No structured grading available.</p>';

  // Citations
  if (result.citations && result.citations.length) {
    document.getElementById('citations-section').style.display = 'block';
    document.getElementById('citations-container').innerHTML =
      result.citations.map(c => `<span class="citation-tag">${c}</span>`).join('');
  }

  // Disclaimer
  document.getElementById('disclaimer-text').textContent = result.disclaimer;

  // Switch views
  document.getElementById('intake-view').style.display = 'none';
  document.getElementById('result-view').style.display = 'block';
  window.scrollTo(0, 0);
}

function showIntake() {
  document.getElementById('result-view').style.display = 'none';
  document.getElementById('intake-view').style.display = 'block';
  window.scrollTo(0, 0);
}

function toggleSection(name) {
  const body = document.getElementById(`${name}-body`);
  const toggle = document.getElementById(`${name}-toggle`);
  const hidden = body.style.display === 'none';
  body.style.display = hidden ? 'block' : 'none';
  toggle.textContent = hidden ? '▼' : '▶';
}
