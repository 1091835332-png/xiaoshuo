// 小说分析工具 - 前端交互
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const dimensionsPanel = document.getElementById('dimensions-panel');
const resultSection = document.getElementById('result-section');
const loadingIndicator = document.getElementById('loading-indicator');
const resultContent = document.getElementById('result-content');
const progressArea = document.getElementById('progress-area');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');

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

  const analyzeBtn = document.getElementById('analyze-btn');
  analyzeBtn.disabled = true;
  resultSection.classList.remove('hidden');
  resultContent.innerHTML = '';

  // 显示进度条
  progressArea.classList.remove('hidden');
  progressBar.style.width = '0%';
  progressText.textContent = '正在准备...';

  try {
    const resp = await fetch('/analyze-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dimensions: checked })
    });

    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.error || '请求失败');
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          // 更新进度
          const pct = Math.round((data.done / data.total) * 100);
          progressBar.style.width = pct + '%';
          progressText.textContent = '正在分析：' + data.label + '（' + data.done + '/' + data.total + '）';

          // 追加结果卡片
          resultContent.innerHTML +=
            '<div class="result-card fade-in"><h2>' + data.label +
            '</h2><div class="markdown-body">' + markdownToHtml(data.content) + '</div></div>';
        }
      }
    }

    progressText.textContent = '✓ 分析完成';
    progressBar.style.width = '100%';
    setTimeout(() => { progressArea.classList.add('hidden'); }, 2000);

  } catch (err) {
    progressArea.classList.add('hidden');
    resultContent.innerHTML += '<p class="error">分析失败: ' + err.message + '</p>';
  } finally {
    analyzeBtn.disabled = false;
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