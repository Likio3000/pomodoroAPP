(function(){
  'use strict';
  const display = document.getElementById('global-timer-display');
  if(!display) return;
  // if full timer page is loaded, skip to avoid duplicate logic
  if(document.getElementById('timer-component')) return;

  const apiUrls = window.pomodoroApiUrls || {};
  const csrfMeta = document.querySelector('meta[name=csrf-token]');
  const csrf = csrfMeta ? csrfMeta.content : null;

  let phase = 'idle';
  let endTimeMs = null;
  let intervalId = null;

  function formatTime(sec){
    const m = Math.floor(sec/60).toString().padStart(2,'0');
    const s = Math.floor(sec%60).toString().padStart(2,'0');
    return `${m}:${s}`;
  }

  async function fetchState(){
    try{
      const resp = await fetch(apiUrls.getState, {credentials:'same-origin'});
      const data = await resp.json();
      if(resp.ok && data.active){
        phase = data.phase;
        endTimeMs = new Date(data.end_time).getTime();
        startTicker();
      } else {
        display.textContent = '';
      }
    }catch(e){
      console.error('Global timer state error', e);
    }
  }

  function startTicker(){
    update();
    clearInterval(intervalId);
    intervalId = setInterval(update, 1000);
  }

  async function handleCompletion(){
    if(!csrf) return;
    try{
      const resp = await fetch(apiUrls.complete, {
        method:'POST',
        headers:{'Content-Type':'application/json','X-CSRFToken':csrf},
        credentials:'same-origin',
        body: JSON.stringify({phase_completed: phase})
      });
      const data = await resp.json();
      if(resp.ok){
        if(data.status === 'break_started' || data.status === 'work_started'){
          phase = data.status === 'break_started' ? 'break' : 'work';
          endTimeMs = new Date(data.end_time).getTime();
          startTicker();
          return;
        }
      }
      phase = 'idle';
      display.textContent = '';
    }catch(e){
      console.error('Global timer completion error', e);
    }
  }

  function update(){
    if(endTimeMs==null){ display.textContent=''; return; }
    const remaining = Math.max(0, Math.floor((endTimeMs - Date.now())/1000));
    display.textContent = formatTime(remaining);
    if(remaining<=0){
      clearInterval(intervalId);
      handleCompletion();
    }
  }

  document.addEventListener('visibilitychange', function(){
    if(!document.hidden && phase!=='idle'){
      fetchState();
    }
  });

  fetchState();
})();
