(function() {
  'use strict';
  const toggleBtn = document.getElementById('theme-toggle');
  if (!toggleBtn) return;

  function applyTheme(theme) {
    if (theme === 'dark') {
      document.body.classList.add('dark-theme');
      toggleBtn.textContent = '☀️';
    } else {
      document.body.classList.remove('dark-theme');
      toggleBtn.textContent = '🌙';
    }
    // Notify listeners of the theme change
    document.body.dispatchEvent(new CustomEvent('themechange', { detail: theme }));
  }

  const stored = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(stored ? stored : (prefersDark ? 'dark' : 'light'));

  toggleBtn.addEventListener('click', () => {
    const newTheme = document.body.classList.contains('dark-theme') ? 'light' : 'dark';
    applyTheme(newTheme);
    localStorage.setItem('theme', newTheme);
  });

  const logoutLink = document.getElementById('logout-link');
  if (logoutLink) {
    logoutLink.addEventListener('click', () => {
      sessionStorage.removeItem('pomodoroAgentChatHistory_v1');
      sessionStorage.removeItem('pomodoroAgentSelected_v1');
    });
  }
})();
