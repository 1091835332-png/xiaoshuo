// NovelScope - JS
var $ = function(id){ return document.getElementById(id); };

var dropZone = $('drop-zone');
var fileInput = $('file-input');
var fileInfo = $('file-info');
var dimPanel = $('dimensions-panel');
var resultSec = $('result-section');
var resultContent = $('resultContent');
var progressArea = $('progress-area');
var progressBar = $('progressBar');
var progressLabel = $('progressLabel');
var progressPct = $('progressPct');

// ── API Key ──
var btnSettings = $('btnSettings');
var settingsPanel = $('settingsPanel');
var apiKeyInput = $('apiKeyInput');
var keyStatus = $('keyStatus');

btnSettings.addEventListener('click', function(){
  settingsPanel.style.display = settingsPanel.style.display === 'none' ? 'block' : 'none';
});

$('btnToggleKey').addEventListener('click', function(){
  apiKeyInput.type = apiKeyInput.type === 'password' ? 'text' : 'password';
});

$('btnSaveKey').addEventListener('click', function(){
  var key = apiKeyInput.value.trim();
  fetch('/api/set-key', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({api_key: key})
  }).then(function(r){ return r.json(); }).then(function(d){
    keyStatus.textContent = d.has_key ? '\u2713 已保存' : '\u2717 已清除';
    keyStatus.className = 'key-badge ' + (d.has_key ? 'saved' : '');
    apiKeyInput.value = '';
  });
});

fetch('/api/has-key').then(function(r){ return r.json(); }).then(function(d){
  if (d.has_key) { keyStatus.textContent = '\u2713 已设置'; keyStatus.className = 'key-badge saved'; }
});

// ── 上传 ──
dropZone.addEventListener('dragover', function(e){ e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', function(){ dropZone.classList.remove('drag-over'); });
dropZone.addEventListener('drop', function(e){
  e.preventDefault(); dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', function(){
  if (fileInput.files.length) uploadFile(fileInput.files[0]);
});

function uploadFile(file){
  var fd = new FormData(); fd.append('file', file);
  fetch('/upload', {method:'POST', body:fd}).then(function(r){ return r.json(); }).then(function(d){
    if (d.error) { alert(d.error); return; }
    $('file-name').textContent = d.filename;
    $('file-meta').textContent = d.chapter_count + ' \u7ae0 \u00b7 ' + d.total_chars.toLocaleString() + ' \u5b57';
    dropZone.style.display = 'none';
    fileInfo.style.display = 'flex';
    dimPanel.style.display = 'block';
    resultSec.style.display = 'none';
  }).catch(function(e){ alert('\u4e0a\u4f20\u5931\u8d25: ' + e.message); });
}

function resetFile(){
  dropZone.style.display = '';
  fileInfo.style.display = 'none';
  dimPanel.style.display = 'none';
  resultSec.style.display = 'none';
  fileInput.value = '';
}

// ── SSE 流式分析 ──
function startAnalyze(){
  var checked = Array.from(document.querySelectorAll('.dim-chip input:checked')).map(function(cb){ return cb.value; });
  if (!checked.length) { alert('\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u4e2a\u5206\u6790\u7ef4\u5ea6'); return; }

  var btn = $('analyze-btn'); btn.disabled = true;
  resultSec.style.display = 'block';
  resultContent.innerHTML = '';
  progressArea.style.display = 'block';
  progressBar.style.width = '0%';
  progressLabel.textContent = '\u6b63\u5728\u51c6\u5907\u2026';
  progressPct.textContent = '0%';

  fetch('/analyze-stream', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({dimensions: checked})
  }).then(function(resp){
    if (!resp.ok) return resp.json().then(function(e){ throw new Error(e.error); });
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    function pump(){
      return reader.read().then(function(_a){
        var done = _a.done, value = _a.value;
        if (done) {
          progressLabel.textContent = '\u2713 \u5206\u6790\u5b8c\u6210';
          progressPct.textContent = '100%';
          progressBar.style.width = '100%';
          setTimeout(function(){ progressArea.style.display = 'none'; }, 2000);
          btn.disabled = false;
          return;
        }
        buffer += decoder.decode(value, {stream: true});
        var lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(function(line){
          if (line.indexOf('data: ') === 0) {
            var d = JSON.parse(line.slice(6));
            var pct = Math.round(d.done / d.total * 100);
            progressBar.style.width = pct + '%';
            progressLabel.textContent = '\u6b63\u5728\u5206\u6790\uff1a' + d.label;
            progressPct.textContent = pct + '% (' + d.done + '/' + d.total + ')';
            resultContent.innerHTML += '<div class="result-card fade-in"><div class="result-card-header"><span class="result-card-icon">' +
              {worldview:'\ud83c\udf0d',characters:'\ud83d\udc64',plot:'\ud83d\udcc8',themes:'\ud83d\udca1'}[d.dim] +
              '</span><h2>' + d.label + '</h2></div><div class="markdown-body">' + md(d.content) + '</div></div>';
          }
        });
        return pump();
      });
    }
    return pump();
  }).catch(function(err){
    progressArea.style.display = 'none';
    resultContent.innerHTML = '<div class="error-banner">\u5206\u6790\u5931\u8d25: ' + err.message + '</div>';
    btn.disabled = false;
  });
}

// ── Markdown ──
function md(text){
  if (!text) return '';
  return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/^### (.+)$/gm,'<h4>$1</h4>').replace(/^## (.+)$/gm,'<h3>$1</h3>').replace(/^# (.+)$/gm,'<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\n\n/g,'</p><p>').replace(/\n/g,'<br>')
    .replace(/^/,'<p>').replace(/$/,'</p>');
}