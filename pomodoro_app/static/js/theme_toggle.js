(function() {
  'use strict';
  const toggleBtn = document.getElementById('theme-toggle');
  if (!toggleBtn) return;

  function applyTheme(theme) {
    if (theme === 'dark') {
      document.body.classList.add('dark-theme');
      toggleBtn.textContent = 'Light Mode';
    } else {
      document.body.classList.remove('dark-theme');
      toggleBtn.textContent = 'Dark Mode';
    }
  }

  const stored = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(stored ? stored : (prefersDark ? 'dark' : 'light'));

  toggleBtn.addEventListener('click', () => {
    const newTheme = document.body.classList.contains('dark-theme') ? 'light' : 'dark';
    applyTheme(newTheme);
    localStorage.setItem('theme', newTheme);
  });
})();
