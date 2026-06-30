var qCounter = 0;

/* ── Per-type option block renderers ─────────────────────────────────────── */
function _mcqOptRows() {
  return '<div class="fl" style="margin-bottom:8px;margin-top:4px">Answer Options</div>' +
    ['A','B','C','D'].map(function(l) {
      return '<div class="opt-row"><span class="opt-lbl">' + l + '</span>' +
        '<input class="fi fi-noi opt-text" placeholder="Option ' + l + '">' +
        '<div class="correct-dot" onclick="markCorrect(this)" title="Mark as correct"></div></div>';
    }).join('');
}

function _tfOptRows() {
  return '<div class="fl" style="margin-bottom:8px;margin-top:4px">Correct Answer</div>' +
    [['A','True'],['B','False']].map(function(pair) {
      return '<div class="opt-row"><span class="opt-lbl">' + pair[0] + '</span>' +
        '<input class="fi fi-noi opt-text" value="' + pair[1] + '" readonly ' +
        'style="opacity:.75;cursor:default;pointer-events:none">' +
        '<div class="correct-dot" onclick="markCorrect(this)" title="Mark as correct"></div></div>';
    }).join('');
}

function _shortNote() {
  return '<div style="padding:14px 16px;background:rgba(45,91,227,.06);border:1px dashed ' +
    'rgba(45,91,227,.3);border-radius:10px;color:var(--muted);font-size:13px;margin-top:6px">' +
    '✏️ Students will type a short text answer. Grading is manual.</div>';
}

function _multiSingleRow(label, value) {
  return '<div class="opt-row">' +
    '<span class="opt-lbl">' + label + '</span>' +
    '<input class="fi fi-noi opt-text" placeholder="Option ' + label + '" value="' + (value || '') + '">' +
    '<div class="correct-dot" onclick="markCorrectMulti(this)" title="Toggle correct"></div>' +
    '<button type="button" class="rem-opt-btn" onclick="removeOptRow(this)" title="Remove">&#215;</button>' +
    '</div>';
}

function _multiOptRows(initialValues) {
  var vals = initialValues || ['', '', '', ''];
  return '<div class="fl" style="margin-bottom:8px;margin-top:4px">Answer Options ' +
    '<span style="font-size:11px;font-weight:400;color:var(--muted)">— check ALL correct answers</span></div>' +
    '<div class="multi-opts-list">' +
    vals.map(function(v, i) { return _multiSingleRow(String.fromCharCode(65 + i), v); }).join('') +
    '</div>' +
    '<button type="button" class="add-opt-btn" onclick="addOptRow(this)">+ Add Option</button>';
}

/* ── Update option block when type select changes ─────────────────────────── */
function updateQType(sel) {
  var block = sel.closest('.q-item').querySelector('.opts-block');
  if      (sel.value === 'truefalse') block.innerHTML = _tfOptRows();
  else if (sel.value === 'short')     block.innerHTML = _shortNote();
  else if (sel.value === 'multi')     block.innerHTML = _multiOptRows();
  else                                block.innerHTML = _mcqOptRows();
}

/* ── Multi-select helpers ────────────────────────────────────────────────── */
function markCorrectMulti(dot) { dot.classList.toggle('sel'); }

function addOptRow(btn) {
  var list = btn.closest('.q-item').querySelector('.multi-opts-list');
  var count = list.querySelectorAll('.opt-row').length;
  var label = count < 26 ? String.fromCharCode(65 + count) : String(count + 1);
  var tmp = document.createElement('div');
  tmp.innerHTML = _multiSingleRow(label, '');
  list.appendChild(tmp.firstChild);
}

function removeOptRow(btn) {
  var list = btn.closest('.multi-opts-list');
  if (list.querySelectorAll('.opt-row').length <= 2) return;
  btn.closest('.opt-row').remove();
  list.querySelectorAll('.opt-row').forEach(function(row, i) {
    row.querySelector('.opt-lbl').textContent = String.fromCharCode(65 + i);
    var inp = row.querySelector('.opt-text');
    if (!inp.value) inp.placeholder = 'Option ' + String.fromCharCode(65 + i);
  });
}

function addQ(prefill) {
  qCounter++;
  var ql = document.getElementById('qlist'); if (!ql) return;
  var type = (prefill && prefill.type) ? prefill.type : 'mcq';

  var d = document.createElement('div'); d.className = 'q-item';
  d.innerHTML =
    '<div class="q-num-lbl">Question ' + qCounter + '</div>' +
    '<div class="fg"><div class="fl">Question Text</div>' +
    '<textarea class="fi fi-noi" style="min-height:72px" placeholder="Enter your question here..."></textarea></div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:8px">' +
    '<div class="fg" style="margin-bottom:0"><div class="fl">Question Type</div>' +
    '<select class="fi fi-noi" onchange="updateQType(this)">' +
    '<option value="mcq"'       + (type==='mcq'       ?' selected':'') + '>Multiple Choice</option>' +
    '<option value="multi"'     + (type==='multi'      ?' selected':'') + '>Multiple Select</option>' +
    '<option value="truefalse"' + (type==='truefalse'  ?' selected':'') + '>True / False</option>' +
    '<option value="short"'     + (type==='short'      ?' selected':'') + '>Short Answer</option>' +
    '</select></div>' +
    '<div class="fg" style="margin-bottom:0"><div class="fl">Points</div>' +
    '<input class="fi fi-noi" type="number" value="2" min="1"></div></div>' +
    '<div class="q-extra-row">' +
      '<div class="q-timer-wrap">' +
        '<label class="q-toggle-label">' +
          '<input type="checkbox" class="q-timer-chk" onchange="toggleQTimer(this)">' +
          '<span class="q-toggle-track"><span class="q-toggle-thumb"></span></span>' +
          '<span class="q-toggle-text">Question Timer</span>' +
        '</label>' +
        '<div class="q-timer-input-wrap" style="display:none">' +
          '<input class="fi fi-noi q-timer-secs" type="number" min="5" max="600" value="60" placeholder="sec">' +
          '<span class="q-timer-unit">sec</span>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div class="opts-block">' +
      (type==='truefalse' ? _tfOptRows() :
       type==='short'     ? _shortNote() :
       type==='multi'     ? _multiOptRows() : _mcqOptRows()) +
    '</div>' +
    '<button class="del-q" onclick="delQ(this)" title="Delete">&#215;</button>';
  ql.appendChild(d);

  if (prefill) {
    d.querySelector('textarea').value = prefill.text || '';
    var pts = d.querySelector('input[type=number]');
    if (prefill.points) pts.value = prefill.points;

    if (type === 'multi' && (prefill.options || []).length) {
      var block = d.querySelector('.opts-block');
      block.innerHTML = _multiOptRows(prefill.options.map(function(o) { return o.text; }));
      block.querySelectorAll('.correct-dot').forEach(function(dot, i) {
        if (prefill.options[i] && prefill.options[i].correct) dot.classList.add('sel');
      });
    } else if (type !== 'short') {
      var optInputs = d.querySelectorAll('.opt-text');
      var dots = d.querySelectorAll('.correct-dot');
      (prefill.options || []).forEach(function(o, i) {
        if (type !== 'truefalse' && optInputs[i]) optInputs[i].value = o.text || '';
        if (o.correct && dots[i]) dots[i].classList.add('sel');
      });
    }
    if (prefill.timer_secs) {
      var chk = d.querySelector('.q-timer-chk');
      if (chk) {
        chk.checked = true;
        toggleQTimer(chk);
        d.querySelector('.q-timer-secs').value = prefill.timer_secs;
      }
    }
  }

  updateQCount();
}

/* ── Show / hide timer input when checkbox toggles ── */
function toggleQTimer(chk) {
  var wrap = chk.closest('.q-timer-wrap').querySelector('.q-timer-input-wrap');
  wrap.style.display = chk.checked ? 'flex' : 'none';
}

function delQ(btn) {
  var item = btn.closest('.q-item');
  if (document.querySelectorAll('#qlist .q-item').length > 1) {
    item.remove(); updateQCount();
  }
}

function markCorrect(dot) {
  var item = dot.closest('.q-item');
  item.querySelectorAll('.correct-dot').forEach(function(d) { d.classList.remove('sel'); });
  dot.classList.add('sel');
}

function updateQCount() {
  var n = document.querySelectorAll('#qlist .q-item').length;
  var el = document.getElementById('sumQ'); if (el) el.textContent = n;
}

function toggleObj(el) {
  var dot = el.querySelector('.obj-dot');
  if (el.classList.contains('allowed')) {
    el.classList.replace('allowed', 'forbidden'); dot.style.background = '#ff7675';
  } else {
    el.classList.replace('forbidden', 'allowed'); dot.style.background = '#5dde8a';
  }
}

/* ── Import questions from a past exam ───────────────────────────────────── */
function importQuestions() {
  var sel = document.getElementById('reuseSelect');
  if (!sel || !sel.value) return;
  fetch('/api/reuse-questions/' + sel.value)
    .then(function(r) { return r.json(); })
    .then(function(qs) {
      if (!qs.length) { alert('No questions found for that exam.'); return; }
      if (!confirm('Import ' + qs.length + ' question(s) from the selected exam? They will be added below existing questions.')) return;
      qs.forEach(function(q) { addQ(q); });
      showToast('Imported ' + qs.length + ' question(s)!', 'ok');
    })
    .catch(function() { alert('Failed to load questions.'); });
}

/* ── Collect all form data and POST to /save-exam ────────────────────────── */
function collectAndSave(action) {
  var title         = document.getElementById('inp-title')        ? document.getElementById('inp-title').value        : '';
  var course_code   = document.getElementById('inp-course')       ? document.getElementById('inp-course').value       : '';
  var department    = document.getElementById('inp-dept')         ? document.getElementById('inp-dept').value         : '';
  var level         = document.getElementById('inp-level')        ? document.getElementById('inp-level').value        : '1';
  var start_dt      = document.getElementById('inp-start')        ? document.getElementById('inp-start').value        : '';
  var duration      = document.getElementById('inp-duration')     ? document.getElementById('inp-duration').value     : '90';
  var total_marks   = document.getElementById('inp-marks')        ? document.getElementById('inp-marks').value        : '100';
  var passing_score = document.getElementById('inp-pass')         ? document.getElementById('inp-pass').value         : '60';
  var instructions  = document.getElementById('inp-instructions') ? document.getElementById('inp-instructions').value : '';
  var warning       = document.getElementById('inp-warning')      ? document.getElementById('inp-warning').value      : '';
  var exam_id       = document.getElementById('inp-exam-id')      ? document.getElementById('inp-exam-id').value      : null;

  // Proctoring toggles (added 'oneway' to the list)
  var procIds = ['webcam','face','gaze','audio','tab','phone','multiface','oneway'];
  var proctoring = {};
  procIds.forEach(function(key) {
    var el = document.getElementById('proc-' + key);
    proctoring[key] = el ? (el.classList.contains('on') ? 1 : 0) : 1;
  });

  // Objects
  var objects = [];
  document.querySelectorAll('#objGrid .obj-item').forEach(function(el) {
    var name = el.dataset.name;
    if (name) objects.push({ name: name, allowed: el.classList.contains('allowed') });
  });

  // Questions — now includes timer_secs and no_backtrack
  var questions = [];
  document.querySelectorAll('#qlist .q-item').forEach(function(item) {
    var text  = item.querySelector('textarea') ? item.querySelector('textarea').value : '';
    var type  = item.querySelector('select')   ? item.querySelector('select').value   : 'mcq';
    var pts   = item.querySelector('input[type=number]') ? item.querySelector('input[type=number]').value : '2';

    // Timer
    var timerChk  = item.querySelector('.q-timer-chk');
    var timerSecs = item.querySelector('.q-timer-secs');
    var timer_secs = (timerChk && timerChk.checked && timerSecs)
      ? parseInt(timerSecs.value) || 0
      : 0;

    // No-backtrack
    var nobackChk   = item.querySelector('.q-noback-chk');
    var no_backtrack = nobackChk ? (nobackChk.checked ? 1 : 0) : 0;

    var opts  = [];
    item.querySelectorAll('.opt-row').forEach(function(row) {
      var lbl = row.querySelector('.opt-lbl') ? row.querySelector('.opt-lbl').textContent.trim() : '';
      var inp = row.querySelector('.opt-text');
      var dot = row.querySelector('.correct-dot');
      if (inp) opts.push({ label: lbl, text: inp.value, correct: dot ? dot.classList.contains('sel') : false });
    });
    questions.push({
      text: text, type: type, points: parseInt(pts),
      timer_secs: timer_secs, no_backtrack: no_backtrack,
      options: opts
    });
  });

  var payload = {
    action: action,
    exam_id: exam_id || null,
    title: title, course_code: course_code, department: department,
    level: parseInt(level), start_datetime: start_dt,
    duration_mins: parseInt(duration), total_marks: parseInt(total_marks),
    passing_score: parseInt(passing_score), instructions: instructions,
    warning_message: warning, proctoring: proctoring,
    locking_mode: proctoring.oneway ? 1 : 0,  // ← NEW: Set locking_mode from oneway toggle
    objects: objects, questions: questions
  };

  fetch('/save-exam', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(function(r) { return r.json(); })
  .then(function(res) {
    if (res.ok) {
      var hiddenId = document.getElementById('inp-exam-id');
      if (hiddenId) hiddenId.value = res.exam_id;
      if (action === 'publish') {
        showToast('🚀 Exam published!', 'ok');
        setTimeout(function() { window.location = '/admin_dashboard'; }, 1200);
      } else {
        showToast('💾 Saved as draft.', 'ok');
      }
    } else {
      showToast('Error: ' + (res.error || 'Unknown'), 'err');
    }
  })
  .catch(function(e) { showToast('Network error.', 'err'); });
}

/* ── Toast helper ────────────────────────────────────────────────────────── */
function showToast(msg, type) {
  var t = document.createElement('div');
  t.textContent = msg;
  t.style.cssText = 'position:fixed;bottom:28px;right:28px;z-index:9999;padding:13px 22px;border-radius:10px;font-size:14px;font-weight:600;font-family:Poppins,sans-serif;color:#fff;box-shadow:0 8px 24px rgba(0,0,0,.4);animation:up .3s ease;';
  t.style.background = (type === 'ok') ? '#27ae60' : '#e74c3c';
  document.body.appendChild(t);
  setTimeout(function() { t.remove(); }, 2800);
}

/* ── Preview exam ─────────────────────────────────────────────────────────── */
function previewExam() {
  var examId = document.getElementById('inp-exam-id') ? document.getElementById('inp-exam-id').value : '';
  if (examId) {
    window.open('/exam/' + examId, '_blank');
  } else {
    alert('Please save as draft first before previewing.');
  }
}

document.addEventListener('DOMContentLoaded', function() {
  applyTheme(currentTheme); setLogos();
  if (document.querySelectorAll('#qlist .q-item').length === 0) addQ();
});