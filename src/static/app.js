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
  $('main-empty').style.display = '';
  fileInput.value = '';
}

// ── SSE 流式分析 ──
function startAnalyze(){
  var checked = Array.from(document.querySelectorAll('.dim-chip input:checked')).map(function(cb){ return cb.value; });
  if (!checked.length) { alert('\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u4e2a\u5206\u6790\u7ef4\u5ea6'); return; }

  var btn = $('analyze-btn'); btn.disabled = true;
  resultSec.style.display = 'block';
  $('main-empty').style.display = 'none';
  resultContent.innerHTML = '';
  progressArea.style.display = 'block';
  progressBar.style.width = '0%';
  progressLabel.textContent = '\u6b63\u5728\u51c6\u5907\u2026';

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
            resultContent.innerHTML += '<div class="result-card"><div class="result-card-head"><span class="result-card-icon">' +
              {worldview:'\ud83c\udf0d',characters:'\ud83d\udc64',plot:'\ud83d\udcc8',themes:'\ud83d\udca1'}[d.dim] +
              '</span><h2>' + d.label + '</h2></div><div class="result-card-body">' + md(d.content) + '</div></div>';
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

// ── V2 三层递进分析法 ──
function startAnalyzeV2(){
  var granularity = $('granularity-select').value;
  var btn = $('analyze-btn'); btn.disabled = true;
  resultSec.style.display = 'block';
  $('main-empty').style.display = 'none';
  resultContent.innerHTML = '';
  progressArea.style.display = 'block';
  progressBar.style.width = '0%';
  progressLabel.textContent = '\u6b63\u5728\u51c6\u5907\u2026';

  var stageIcons = {chunking:'\ud83d\udce6',skeleton:'\ud83c\udfd7',meso:'\u2699',
    meso_task:'\u27a1',aggregation:'\ud83d\udd17',done:'\u2705'};

  fetch('/analyze-stream-v2', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({granularity: granularity})
  }).then(function(resp){
    if (!resp.ok) return resp.json().then(function(e){ throw new Error(e.error); });
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    function pump(){
      return reader.read().then(function(_a){
        var done = _a.done, value = _a.value;
        if (done) { btn.disabled = false; return; }
        buffer += decoder.decode(value, {stream: true});
        var lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(function(line){
          if (line.indexOf('data: ') === 0) {
            var ev = JSON.parse(line.slice(6));
            progressBar.style.width = (ev.progress_pct * 100) + '%';
            var icon = stageIcons[ev.stage] || '\u25cf';
            var stageTag = ev.stage ? '<span class="stage-badge">' + icon + ' ' + ev.stage + '</span>' : '';
            progressLabel.innerHTML = stageTag + ev.label;

            // 骨架层完成 → 渲染4个分析卡片
            if (ev.data && ev.stage === 'skeleton_done') {
              var d = ev.data;
              var dims = {worldview:'\ud83c\udf0d 世界观',plot:'\ud83d\udcc5 剧情时间轴',characters:'\ud83d\udc64 人物名录',mysteries:'\ud83d\udd2e 悬念与伏笔'};
              for (var key in d) {
                if (d[key] && dims[key] && d[key].length > 20) {
                  resultContent.innerHTML += '<div class="result-card"><div class="result-card-head">' +
                    '<span class="result-card-icon">\ud83d\udcdd</span><h2>' + dims[key] + '</h2></div>' +
                    '<div class="result-card-body">' + md(d[key]) + '</div></div>';
                }
              }
            }

            // 中观层块完成
            if (ev.data && ev.stage === 'meso_done' && ev.data.lexicon_stats) {
              var st = ev.data.lexicon_stats;
              resultContent.innerHTML += '<div class="result-card"><div class="result-card-head">' +
                '<span class="result-card-icon">\u2699</span><h2>\u4e2d\u89c2\u5c42\u5b8c\u6210</h2></div>' +
                '<div class="result-card-body"><p>\u8bcd\u5178: ' + (st.total_terms||0) +
                '\u6761 | \u5df2\u5904\u7406 ' + (st.blocks_processed||0) + '\u5757</p></div></div>';
            }

            // 最终汇总
            if (ev.data && ev.stage === 'done') {
              var dd = ev.data;
              var summary = '';
              if (dd.foreshadow_count !== undefined) summary += '\u2728 ' + dd.foreshadow_count + '\u6761\u4f0f\u7b14 | ';
              if (dd.tier_entries !== undefined) summary += '\ud83d\udcca ' + dd.tier_entries + '\u7ea7\u6218\u529b\u68af\u961f | ';
              if (dd.character_count !== undefined) summary += '\ud83d\udc64 ' + dd.character_count + '\u4eba | ';
              if (dd.setting_categories) summary += '\ud83d\udcd6 ' + dd.setting_categories.length + '\u7c7b\u8bbe\u5b9a | ';
              if (dd.validation_gaps && dd.validation_gaps.length) {
                summary += '\u26a0 ' + dd.validation_gaps.length + '\u4e2a\u5f85\u6838\u5b9e\u7f3a\u53e3';
              }
              resultContent.innerHTML += '<div class="result-card"><div class="result-card-head">' +
                '<span class="result-card-icon">\u2705</span><h2>\u5206\u6790\u5b8c\u6210</h2></div>' +
                '<div class="result-card-body"><p>' + summary + '</p></div></div>';
            }
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