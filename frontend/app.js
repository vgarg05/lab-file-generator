/* ============================================================
   app.js — AI Lab Assistant | Real-Time Agent Execution Engine
   ============================================================ */

// ── DOM refs ──────────────────────────────────────────────────
const form            = document.getElementById('lab-form');
const generateBtn     = document.getElementById('generate-btn');
const agentPanel      = document.getElementById('agent-panel');
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

// Real-time Agent UI refs
const agentStatusMsg     = document.getElementById('agent-status-msg');
const agentLiveBadge     = document.getElementById('agent-live-badge');
const terminalOutput     = document.getElementById('live-terminal-output');
const browserPreviewCard = document.getElementById('browser-preview-card');
const liveBrowserImg     = document.getElementById('live-browser-img');
const codeText           = document.getElementById('agent-code-text');
const logsText           = document.getElementById('agent-logs-text');

let currentActiveStepId = null;

// ── Character counter & validation ──────────────────────────────
aimInput.addEventListener('input', () => {
  charCount.textContent = `${aimInput.value.length} / 500`;
  validateForm();
});

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
validateForm();

// ── Step Timeline Helper ──────────────────────────────────────
const TIMELINE_STEPS = ['step-task', 'step-code', 'step-sandbox', 'step-exec', 'step-playwright', 'step-docx'];

function setTimelineStep(stepId, state) {
  const item = document.getElementById(stepId);
  if (!item) return;
  const icon = item.querySelector('.step-icon');
  item.className = `timeline-item ${state}`;

  switch (state) {
    case 'running':
      icon.innerHTML = '<div class="timeline-spin"></div>';
      currentActiveStepId = stepId;
      break;
    case 'completed':
      icon.innerHTML = '✓';
      break;
    case 'failed':
      icon.innerHTML = '✕';
      break;
    default:
      icon.innerHTML = '○';
      break;
  }
}

function resetTimeline() {
  TIMELINE_STEPS.forEach(id => setTimelineStep(id, 'pending'));
  currentActiveStepId = null;
}

// ── Terminal & Log Streaming Helpers ─────────────────────────
function appendTerminalLine(text, isPrompt = false) {
  if (!text) return;
  const line = document.createElement('div');
  line.className = isPrompt ? 'term-line prompt' : 'term-line';
  line.textContent = text;
  terminalOutput.appendChild(line);
  terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

function typeTerminalCommand(cmdText, callback) {
  const line = document.createElement('div');
  line.className = 'term-line prompt';
  line.innerHTML = `<span class="term-prefix">(.venv) PS /app> </span><span class="typed-text"></span><span class="term-cursor">█</span>`;
  terminalOutput.appendChild(line);

  const typedSpan = line.querySelector('.typed-text');
  const cursorSpan = line.querySelector('.term-cursor');
  let idx = 0;

  const interval = setInterval(() => {
    if (idx < cmdText.length) {
      typedSpan.textContent += cmdText[idx];
      idx++;
      terminalOutput.scrollTop = terminalOutput.scrollHeight;
    } else {
      clearInterval(interval);
      setTimeout(() => {
        if (cursorSpan) cursorSpan.style.display = 'none';
        if (callback) callback();
      }, 200);
    }
  }, 20);
}

function animateVirtualMouse(callback) {
  const mouse = document.getElementById('virtual-mouse');
  if (!mouse) { if (callback) callback(); return; }

  mouse.style.display = 'block';
  mouse.className = 'virtual-mouse glide';
  setTimeout(() => {
    mouse.style.display = 'none';
    if (callback) callback();
  }, 1000);
}

function appendLogLine(timestamp, msg) {
  logsText.textContent += `\n[${timestamp}] ${msg}`;
  logsText.scrollTop = logsText.scrollHeight;
}

function resetAgentPanel() {
  resetTimeline();
  agentStatusMsg.textContent = 'Initializing AI Agent...';
  agentLiveBadge.className = 'agent-badge';
  agentLiveBadge.innerHTML = '<span class="pulse-dot"></span> LIVE';
  terminalOutput.innerHTML = '';
  browserPreviewCard.style.display = 'none';
  liveBrowserImg.src = '';
  codeText.textContent = 'Generating code...';
  logsText.textContent = 'Agent session started...';
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorToast.style.display = 'flex';
  errorToast.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function hideError() { errorToast.style.display = 'none'; }

function setLoading(on) {
  generateBtn.disabled = on;
  generateBtn.innerHTML = on
    ? '<div class="btn-spin"></div><span>Executing Agent…</span>'
    : '✦ Generate Lab File →';
}

function resetUI() {
  agentPanel.style.display     = 'none';
  successSection.style.display  = 'none';
  hideError();
  setLoading(false);
  resetAgentPanel();
  validateForm();
}

// ── Form Submit with Server-Sent Events (SSE) ────────────────
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideError();

  const experimentNumber = parseInt(expInput.value, 10);
  const aim              = aimInput.value.trim();
  const language         = langSelect.value;

  if (!experimentNumber || experimentNumber < 1) return showError('Please enter a valid experiment number (≥ 1).');
  if (!aim) return showError('Please enter the experiment aim.');
  if (!language) return showError('Please select a programming language.');

  const codeInstructions   = codeInstInput.value.trim();
  const theoryInstructions = theoryInstInput.value.trim();

  setLoading(true);
  resetAgentPanel();
  agentPanel.style.display = 'block';
  successSection.style.display = 'none';
  agentPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  typeTerminalCommand(`python runner.py --target=${language.toLowerCase()}`);

  try {
    const response = await fetch('/generate-stream', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        experiment_number: experimentNumber,
        aim,
        language,
        code_instructions: codeInstructions,
        theory_instructions: theoryInstructions,
        api_key: (document.getElementById('api-key-input')?.value || '').trim(),
      }),
    });

    if (!response.ok) {
      let detail = `Server error (${response.status})`;
      try {
        const err = await response.json();
        detail = err.detail || detail;
      } catch { /* ignore */ }
      throw new Error(detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();

      for (const chunk of parts) {
        const line = chunk.trim();
        if (!line.startsWith('data: ')) continue;
        
        try {
          const payload = JSON.parse(line.substring(6));
          handleAgentEvent(payload, experimentNumber);
        } catch (err) {
          console.error('Failed to parse SSE event:', err);
        }
      }
    }

    setLoading(false);

  } catch (err) {
    if (currentActiveStepId) setTimelineStep(currentActiveStepId, 'failed');
    agentLiveBadge.className = 'agent-badge error';
    agentLiveBadge.textContent = 'FAILED';
    setLoading(false);
    showError(err.message || 'Generation failed. Please try again.');
  }
});

// ── Event Router for Backend SSE Messages ─────────────────────
function handleAgentEvent(payload, experimentNumber) {
  const { type, message, timestamp, data } = payload;
  if (message) {
    agentStatusMsg.textContent = message;
    appendLogLine(timestamp || '00:00:00', message);
  }

  switch (type) {
    case 'agent_started':
      setTimelineStep('step-task', 'running');
      break;

    case 'generating_code':
      setTimelineStep('step-task', 'completed');
      setTimelineStep('step-code', 'running');
      break;

    case 'code_generated':
      setTimelineStep('step-code', 'completed');
      if (data && data.code) {
        codeText.textContent = data.code;
      }
      break;

    case 'sandbox_starting':
      setTimelineStep('step-sandbox', 'running');
      break;

    case 'execution_started':
      setTimelineStep('step-sandbox', 'completed');
      setTimelineStep('step-exec', 'running');
      break;

    case 'terminal_output':
      if (data !== undefined) appendTerminalLine(String(data));
      else if (message) appendTerminalLine(message);
      break;

    case 'execution_completed':
      setTimelineStep('step-exec', 'completed');
      setTimelineStep('step-playwright', 'running');
      break;

    case 'playwright_starting':
      setTimelineStep('step-playwright', 'running');
      break;

    case 'browser_screenshot':
      setTimelineStep('step-playwright', 'completed');
      setTimelineStep('step-docx', 'running');
      if (data && data.image) {
        browserPreviewCard.style.display = 'block';
        animateVirtualMouse(() => {
          liveBrowserImg.src = `data:image/png;base64,${data.image}`;
        });
        browserPreviewCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      break;

    case 'document_generation':
      setTimelineStep('step-docx', 'running');
      break;

    case 'completed':
      setTimelineStep('step-docx', 'completed');
      agentLiveBadge.className = 'agent-badge success';
      agentLiveBadge.textContent = 'DONE';
      agentStatusMsg.textContent = 'Experiment generated successfully!';

      if (data && data.download_url) {
        downloadBtn.href = data.download_url;
        downloadBtn.download = data.filename || `Experiment_${experimentNumber}.docx`;
        successSection.style.display = 'flex';
        successSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      break;

    case 'error':
      if (currentActiveStepId) setTimelineStep(currentActiveStepId, 'failed');
      agentLiveBadge.className = 'agent-badge error';
      agentLiveBadge.textContent = 'FAILED';
      showError(message || 'An error occurred during execution.');
      break;
  }
}

// ── Reset Button ──────────────────────────────────────────────
resetBtn.addEventListener('click', () => {
  resetUI();
  form.reset();
  charCount.textContent = '0 / 500';
  validateForm();
});
