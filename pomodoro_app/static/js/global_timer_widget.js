(function(){
  'use strict';

  if (document.getElementById('timer-component')) return;

  var isLoggedIn = !!document.querySelector('.navbar .nav-links a[href*="/logout"]');
  if (!isLoggedIn) return;

  var api = window.pomodoroApiUrls || {};
  var urls = {
    getState: api.getState || '/api/timer/state',
    complete: api.complete || '/api/timer/complete_phase',
    pause: api.pause || '/api/timer/pause',
    resume: api.resume || '/api/timer/resume',
    reset: api.reset || '/api/timer/reset',
    timerPage: '/timer'
  };

  var csrfMeta = document.querySelector('meta[name=csrf-token]');
  var csrf = csrfMeta ? csrfMeta.content : null;

  var COLLAPSE_KEY = 'globalTimerWidgetCollapsed_v1';

  var phase = 'idle';
  var endTimeMs = null;
  var intervalId = null;
  var lastAnnouncePhase = null;
  var lastAriaUpdate = 0;
  var pausedAtMs = null;
  var pausedRemaining = 0;

  function buildWidget(){
    if (document.getElementById('global-timerbox')) return;
    var box = document.createElement('div');
    box.id = 'global-timerbox';
    box.setAttribute('role','complementary');
    box.setAttribute('aria-live','off');
    box.innerHTML = [
      '<div id="global-timerbox-header" tabindex="0" role="button" aria-expanded="true">',
      '  <span>Timer</span>',
      '  <span class="global-timer-phase" id="global-timerbox-phase"></span>',
      '  <span aria-hidden="true" id="global-timerbox-toggle">–</span>',
      '</div>',
      '<div id="global-timerbox-body">',
      '  <span id="global-timerbox-countdown" aria-live="polite" aria-atomic="true">--:--</span>',
      '  <div class="global-timer-actions">',
      '    <button type="button" id="global-timerbox-pause">Pause</button>',
      '    <button type="button" id="global-timerbox-resume" style="display:none;">Resume</button>',
      '    <button type="button" id="global-timerbox-reset">Reset</button>',
      '    <button type="button" id="global-timerbox-open">Open Timer</button>',
      '  </div>',
      '  <div id="global-timerbox-error"></div>',
      '</div>'
    ].join('');
    document.body.appendChild(box);

    var collapsed = localStorage.getItem(COLLAPSE_KEY) === '1';
    setCollapsed(collapsed);

    var header = document.getElementById('global-timerbox-header');
    header.addEventListener('click', toggleCollapsed);
    header.addEventListener('keydown', function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggleCollapsed(); }});

    document.getElementById('global-timerbox-open').addEventListener('click', function(){
      window.location.href = urls.timerPage;
    });
    document.getElementById('global-timerbox-pause').addEventListener('click', doPause);
    document.getElementById('global-timerbox-resume').addEventListener('click', doResume);
    document.getElementById('global-timerbox-reset').addEventListener('click', doReset);
  }

  function setCollapsed(collapsed){
    var box = document.getElementById('global-timerbox');
    var toggle = document.getElementById('global-timerbox-toggle');
    if(!box) return;
    if(collapsed){
      box.classList.add('global-timer-collapsed');
      toggle.textContent = '+';
      box.setAttribute('aria-expanded','false');
      localStorage.setItem(COLLAPSE_KEY,'1');
    } else {
      box.classList.remove('global-timer-collapsed');
      toggle.textContent = '–';
      box.setAttribute('aria-expanded','true');
      localStorage.setItem(COLLAPSE_KEY,'0');
    }
  }
  function toggleCollapsed(){
    var box = document.getElementById('global-timerbox');
    setCollapsed(!box.classList.contains('global-timer-collapsed'));
  }

  function fmt(sec){
    var m = Math.floor(sec/60).toString().padStart(2,'0');
    var s = Math.floor(sec%60).toString().padStart(2,'0');
    return m+':'+s;
  }
  function showBox(show){
    var box = document.getElementById('global-timerbox');
    if(!box) return; box.style.display = show ? 'block' : 'none';
  }
  function setPhaseText(p){
    var el = document.getElementById('global-timerbox-phase');
    if(!el) return;
    var txt = '';
    if(p==='work') txt='Work';
    else if(p==='break') txt='Break';
    else if(p==='paused') txt='Paused';
    else txt='';
    el.textContent = txt;
    if(p!==lastAnnouncePhase){
      lastAnnouncePhase = p;
      var now=Date.now();
      if(now-lastAriaUpdate>1000){
        el.setAttribute('aria-live','assertive');
        lastAriaUpdate=now;
        setTimeout(function(){ el.removeAttribute('aria-live'); },500);
      }
    }
  }
  function setCountdownText(sec){
    var el = document.getElementById('global-timerbox-countdown');
    if(!el) return;
    el.textContent = fmt(sec);
    var now=Date.now();
    if(now-lastAriaUpdate>5000){
      el.setAttribute('aria-live','polite');
      lastAriaUpdate=now;
      setTimeout(function(){ el.removeAttribute('aria-live'); },500);
    }
  }
  function setError(msg){
    var el = document.getElementById('global-timerbox-error');
    if(!el) return;
    el.style.display = msg ? 'block' : 'none';
    el.textContent = msg || '';
  }
  function updateButtons(){
    var pauseBtn = document.getElementById('global-timerbox-pause');
    var resumeBtn = document.getElementById('global-timerbox-resume');
    var completeBtn = document.getElementById('global-timerbox-complete');
    var resetBtn = document.getElementById('global-timerbox-reset');
    if(!pauseBtn) return;
    if(phase==='work'||phase==='break'){
      pauseBtn.style.display='';
      pauseBtn.disabled=false;
      resumeBtn.style.display='none';
      if(completeBtn) completeBtn.disabled=false;
      resetBtn.disabled=false;
    } else if(phase==='paused'){
      pauseBtn.style.display='none';
      resumeBtn.style.display='';
      resumeBtn.disabled=false;
      if(completeBtn) completeBtn.disabled=true;
      resetBtn.disabled=false;
    } else {
      pauseBtn.style.display='';
      pauseBtn.disabled=true;
      resumeBtn.style.display='none';
      if(completeBtn) completeBtn.disabled=true;
      resetBtn.disabled=true;
    }
  }

  async function fetchState(){
    try{
      var resp = await fetch(urls.getState,{credentials:'same-origin'});
      var data = await resp.json();
      if(!resp.ok) throw new Error(data.error||'State error');
      if(!data.active){
        phase='idle';
        endTimeMs=null; pausedAtMs=null; pausedRemaining=0;
        showBox(false);
        return;
      }
      showBox(true);
      phase=data.phase||'work';
      endTimeMs=data.end_time? new Date(data.end_time).getTime():null;
      pausedAtMs=null; pausedRemaining=0;
      setPhaseText(phase);
      updateButtons();
      tick();
      startTicker();
      setError('');
    }catch(err){
      console.error('Global timer widget fetchState error',err);
      setError('Error syncing timer.');
      showBox(true);
    }
  }

  function startTicker(){ clearInterval(intervalId); intervalId=setInterval(tick,1000); }
  function stopTicker(){ clearInterval(intervalId); intervalId=null; }

  async function handleCompletion(){
    if(!csrf) return;
    try{
      var resp = await fetch(urls.complete, {
        method:'POST',
        headers:{'Content-Type':'application/json','X-CSRFToken':csrf},
        credentials:'same-origin',
        body: JSON.stringify({phase_completed: phase})
      });
      var data = await resp.json();
      if(!resp.ok) throw new Error(data.error||'Complete error');
      if(data.status==='break_started'){
        phase='break';
        endTimeMs=data.end_time? new Date(data.end_time).getTime():null;
      }else if(data.status==='work_started'){
        phase='work';
        endTimeMs=data.end_time? new Date(data.end_time).getTime():null;
      }else{
        phase='idle';
        endTimeMs=null;
      }
      pausedAtMs=null; pausedRemaining=0;
      setPhaseText(phase);
      updateButtons();
      tick();
    }catch(err){
      console.error('global timer widget completion error',err);
      setError(err.message||'Complete failed');
    }
  }

  async function doPause(){
    if(!csrf) return;
    try{
      var resp = await fetch(urls.pause,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},credentials:'same-origin'});
      var data = await resp.json();
      if(!resp.ok) throw new Error(data.error||'Pause error');
      pausedAtMs=Date.now();
      pausedRemaining=calcRemaining();
      phase='paused';
      stopTicker();
      setPhaseText(phase);
      setCountdownText(pausedRemaining);
      updateButtons();
      setError('');
    }catch(err){
      console.error('global timer widget pause error',err);
      setError(err.message||'Pause failed');
    }
  }

  async function doResume(){
    if(!csrf) return;
    try{
      var resp = await fetch(urls.resume,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},credentials:'same-origin',body: JSON.stringify({ pause_duration_ms: pausedAtMs ? (Date.now()-pausedAtMs):0 })});
      var data = await resp.json();
      if(!resp.ok) throw new Error(data.error||'Resume error');
      var newEnd=data.new_end_time||data.end_time;
      if(newEnd) endTimeMs=new Date(newEnd).getTime();
      await fetchState();
      setError('');
    }catch(err){
      console.error('global timer widget resume error',err);
      setError(err.message||'Resume failed');
    }
  }

  async function doComplete(){ await handleCompletion(); }

  async function doReset(){
    if(!csrf) return;
    try{
      var resp = await fetch(urls.reset,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},credentials:'same-origin'});
      var data = await resp.json();
      if(!resp.ok) throw new Error(data.error||'Reset error');
      phase='idle'; endTimeMs=null; pausedAtMs=null; pausedRemaining=0;
      showBox(false);
    }catch(err){
      console.error('global timer widget reset error',err);
      setError(err.message||'Reset failed');
    }
  }

  function calcRemaining(){
    if(endTimeMs==null) return 0;
    var sec=Math.max(0,Math.floor((endTimeMs-Date.now())/1000));
    return sec;
  }

  function tick(){
    var remaining = phase==='paused'? pausedRemaining : calcRemaining();
    setCountdownText(remaining);
    setPhaseText(phase);
    if(remaining<=0 && (phase==='work'||phase==='break')){
      stopTicker();
      handleCompletion();
    }
  }

  document.addEventListener('visibilitychange',function(){ if(!document.hidden){ fetchState(); }});

  setInterval(fetchState,30000);

  document.addEventListener('DOMContentLoaded',function(){ buildWidget(); fetchState(); });
})();
