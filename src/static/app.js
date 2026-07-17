// 小说分析工具 - 前端交互
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const dimensionsPanel = document.getElementById('dimensions-panel');
const resultSection = document.getElementById('result-section');
const loadingIndicator = document.getElementById('loading-indicator');
const resultContent = document.getElementById('result-content');

// ── API Key 设置 ──
const btnSettings = document.getElementById('btnSettings');
const settingsPanel = document.getElementById('settingsPanel');
const apiKeyInput = document.getElementById('apiKeyInput');
const btnToggleKey = document.getElementById('btnToggleKey');
const btnSaveKey = document.getElementById('btnSaveKey');
const keyStatus = document.getElementById('keyStatus');

btnSettings.addEventListener('click', () => {
  settingsPanel.classList.toggle('hidden');
});

btnToggleKey.addEventListener('click', () => {
  apiKeyInput.type = apiKeyInput.type === 'password' ? 'text' : 'password';
});

btnSaveKey.addEventListener('click', () => {
  const key = apiKeyInput.value.trim();
  fetch('/api/set-key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: key })
  }).then(r => r.json()).then(data => {
    if (data.has_key) {
      keyStatus.textContent = '✓ 已保存';
      keyStatus.className = 'key-status saved';
      apiKeyInput.value = '';
    } else {
      keyStatus.textContent = '✗ 已清除';
      keyStatus.className = 'key-status cleared';
    }
  });
});

// 启动时检查是否已有 key
fetch('/api/has-key').then(r => r.json()).then(data => {
  if (data.has_key) {
    keyStatus.textContent = '✓ 已设置';
    keyStatus.className = 'key-status saved';
  }
});

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) uploadFile(fileInput.files[0]);
});

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  try {
    const resp = await fetch('/upload', { method: 'POST', body: formData });
    const data = await resp.json();
    if (data.error) { alert(data.error); return; }
    document.getElementById('file-name').textContent = data.filename;
    document.getElementById('file-meta').textContent =
      data.chapter_count + ' 章 \u00b7 ' + data.total_chars.toLocaleString() + ' 字';
    dropZone.classList.add('hidden');
    fileInfo.classList.remove('hidden');
    dimensionsPanel.classList.remove('hidden');
    resultSection.classList.add('hidden');
  } catch (err) {
    alert('上传失败: ' + err.message);
  }
}

function resetFile() {
  dropZone.classList.remove('hidden');
  fileInfo.classList.add('hidden');
  dimensionsPanel.classList.add('hidden');
  resultSection.classList.add('hidden');
  fileInput.value = '';
}

async function startAnalyze() {
  const checked = Array.from(document.querySelectorAll('.dim-check input:checked')).map(cb => cb.value);
  if (!checked.length) { alert('请至少选择一个分析维度'); return; }
  document.getElementById('analyze-btn').disabled = true;
  resultSection.classList.remove('hidden');
  loadingIndicator.classList.remove('hidden');
  resultContent.innerHTML = '';
  try {
    const resp = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dimensions: checked })
    });
    const data = await resp.json();
    if (data.error) { alert(data.error); return; }
    loadingIndicator.classList.add('hidden');
    renderResults(data.results);
  } catch (err) {
    loadingIndicator.classList.add('hidden');
    resultContent.innerHTML = '<p class="error">分析失败: ' + err.message + '</p>';
  } finally {
    document.getElementById('analyze-btn').disabled = false;
  }
}

var DIM_LABELS = { worldview: '世界观', characters: '人物性格转变', plot: '关键情节', themes: '主题思想' };

function renderResults(results) {
  var html = '';
  for (var key in results) {
    var label = DIM_LABELS[key] || key;
    html += '<div class="result-card"><h2>' + label + '</h2><div class="markdown-body">' + markdownToHtml(results[key]) + '</div></div>';
  }
  resultContent.innerHTML = html;
}

function markdownToHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^/, '<p>').replace(/$/, '</p>');
}