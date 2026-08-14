/* ============================================================
   app.js — AI Lab Assistant | Dashboard UI
   ============================================================ */

// ── DOM refs ──────────────────────────────────────────────────
const form            = document.getElementById('lab-form');
const generateBtn     = document.getElementById('generate-btn');
const progressSection = document.getElementById('progress-section');
const successSection  = document.getElementById('success-section');
const downloadBtn     = document.getElementById('download-btn');
const resetBtn        = document.getElementById('reset-btn');
const errorToast      = document.getElementById('error-toast');
const errorMsg        = document.getElementById('error-msg');
const charCount       = document.getElementById('char-count');
const aimInput        = document.getElementById('aim');
const expInput        = document.getElementById('exp-number');
const langSelect      = document.getElementById('language');
const codeInstInput   = document.getElementById('code-instructions');
const theoryInstInput = document.getElementById('theory-instructions');

const steps = [
  document.getElementById('step-1'),
  document.getElementById('step-2'),
  document.getElementById('step-3'),
  document.getElementById('step-4'),
];

// Fake progress: each step becomes active after these delays (ms)
const STEP_DELAYS = [0, 8000, 14000, 17000];

let stepTimers = [];
let blobUrl    = null;

// ── Character counter ─────────────────────────────────────────
aimInput.addEventListener('input', () => {
  const len = aimInput.value.length;
  charCount.textContent = `${len} / 500`;
  validateForm();
});

// ── Form validity → enable / disable generate button ─────────
function validateForm() {
  const expVal  = parseInt(expInput.value, 10);
  const aimVal  = aimInput.value.trim();
  const langVal = langSelect.value;
  const valid   = !isNaN(expVal) && expVal >= 1 && aimVal.length > 0 && langVal !== '';
  generateBtn.disabled = !valid;
}

expInput.addEventListener('input',  validateForm);
expInput.addEventListener('change', validateForm);
langSelect.addEventListener('change', validateForm);

// Run once on load
validateForm();

// ── Component card toggle ─────────────────────────────────────
document.querySelectorAll('.comp-card').forEach(card => {
  card.addEventListener('click', () => {
    card.classList.toggle('selected');
  });
});

// ── Step state helper ─────────────────────────────────────────
function setStepState(index, state) {
  const el  = steps[index];
  if (!el) return;
  const ind = el.querySelector('.step-ind');
  el.className = 'step ' + state;

  switch (state) {
    case 'active':
      ind.innerHTML = '<div class="step-spin"></div>';
      break;
    case 'done':
      ind.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
      break;
    case 's-error':
      ind.innerHTML = '✕';
      break;
    default:
      ind.textContent = String(index + 1);
      break;
  }
}

function resetAllSteps() {
  steps.forEach((_, i) => setStepState(i, 'pending'));
}

function clearStepTimers() {
  stepTimers.forEach(clearTimeout);
  stepTimers = [];
}

// ── Fake progress animation ───────────────────────────────────
function startFakeProgress() {
  setStepState(0, 'active');

  STEP_DELAYS.forEach((delay, i) => {
    if (i === 0) return;
    const t = setTimeout(() => {
      setStepState(i - 1, 'done');
      setStepState(i, 'active');
    }, delay);
    stepTimers.push(t);
  });
}

// ── Error helper ──────────────────────────────────────────────
function showError(msg) {
  errorMsg.textContent = msg;
  errorToast.style.display = 'flex';
  errorToast.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function hideError() { errorToast.style.display = 'none'; }

// ── Loading state ─────────────────────────────────────────────
function setLoading(on) {
  generateBtn.disabled = on;
  generateBtn.innerHTML = on
    ? '<div class="btn-spin"></div><span>Generating…</span>'
    : '✦ Generate Lab File →';
}

// ── Show progress / success ───────────────────────────────────
function showProgressCard() {
  progressSection.style.display = 'block';
  successSection.style.display  = 'none';
  progressSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showSuccessCard(blob, experimentNumber) {
  steps.forEach((_, i) => setStepState(i, 'done'));

  if (blobUrl) URL.revokeObjectURL(blobUrl);
  blobUrl = URL.createObjectURL(blob);
  downloadBtn.href     = blobUrl;
  downloadBtn.download = `Experiment_${experimentNumber}.docx`;
  downloadBtn.click();

  progressSection.style.display = 'none';
  successSection.style.display  = 'flex';
  successSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Full reset ────────────────────────────────────────────────
function resetUI() {
  clearStepTimers();
  resetAllSteps();
  progressSection.style.display = 'none';
  successSection.style.display  = 'none';
  hideError();
  setLoading(false);
  validateForm();

  if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
}

// ── Form submit ───────────────────────────────────────────────
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideError();

  const experimentNumber = parseInt(expInput.value, 10);
  const aim              = aimInput.value.trim();
  const language         = langSelect.value;

  if (!experimentNumber || experimentNumber < 1) {
    showError('Please enter a valid experiment number (≥ 1).');
    return;
  }
  if (!aim) {
    showError('Please enter the experiment aim.');
    return;
  }
  if (!language) {
    showError('Please select a programming language.');
    return;
  }

  const codeInstructions   = codeInstInput.value.trim();
  const theoryInstructions = theoryInstInput.value.trim();

  setLoading(true);
  showProgressCard();
  startFakeProgress();

  try {
    const response = await fetch('/generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        experiment_number: experimentNumber,
        aim,
        language,
        code_instructions: codeInstructions,
        theory_instructions: theoryInstructions
      }),
    });

    clearStepTimers();

    if (!response.ok) {
      let detail = `Server error (${response.status})`;
      try {
        const err = await response.json();
        detail = err.detail || detail;
      } catch { /* ignore */ }
      throw new Error(detail);
    }

    const blob = await response.blob();
    setLoading(false);
    showSuccessCard(blob, experimentNumber);

  } catch (err) {
    clearStepTimers();

    const activeIdx = steps.findIndex(s => s.classList.contains('active'));
    if (activeIdx !== -1) setStepState(activeIdx, 's-error');

    setLoading(false);
    showError(err.message || 'Something went wrong. Please try again.');
  }
});

// ── Reset button ──────────────────────────────────────────────
resetBtn.addEventListener('click', () => {
  resetUI();
  form.reset();
  charCount.textContent = '0 / 500';
  document.querySelectorAll('.comp-card').forEach(c => c.classList.add('selected'));
  validateForm();
});
