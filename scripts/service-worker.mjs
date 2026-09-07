import { readdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const files = (await readdir('dist', { recursive: true })).filter(
  (f) => /\.(html|js|css|svg|webmanifest)$/.test(f) && f !== 'sw.js',
);
const hash = createHash('sha256');
hash.update(await readFile(new URL(import.meta.url)));
for (const file of files.sort()) hash.update(await readFile(`dist/${file}`));
const cache = `pomodoro-shell-${hash.digest('hex').slice(0, 12)}`;
await writeFile(
  'dist/sw.js',
  `
const CACHE = ${JSON.stringify(cache)};
const FILES = ${JSON.stringify(files.map((f) => './' + f))};
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES))); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('pomodoro-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(event.request).catch(async () => {
    const cache = await caches.open(CACHE);
    // These are our immutable, same-origin build files. Preview hosts may add
    // Vary: Origin, even though a module and its preload have identical content.
    const cached = await cache.match(event.request, { ignoreVary: true });
    if (cached) return cached;
    if (event.request.mode === 'navigate') return await cache.match(new URL('./index.html', self.registration.scope), { ignoreVary: true }) || Response.error();
    return Response.error();
  }));
});
`,
);
console.log(`Offline shell: ${files.length} files, ${cache}`);
