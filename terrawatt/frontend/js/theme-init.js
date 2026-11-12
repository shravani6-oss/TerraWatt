// Runs before first paint: apply the saved or system colour theme (external file because CSP forbids inline scripts).
try { document.documentElement.dataset.theme = localStorage.getItem('tw-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); } catch (e) { /* default light */ }
