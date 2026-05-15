/**
 * OncoTriage AI — Service Worker
 * Offline symptom logging with Background Sync API.
 *
 * Strategy:
 *  - App shell (HTML, CSS, manifest) → Cache-First (stale-while-revalidate on first load)
 *  - /api/triage/assess → Network-First with offline fallback to queue
 *  - Queued submissions → replayed via Background Sync when connectivity returns
 */

const CACHE_NAME = "oncotriage-v2";
const SYNC_TAG = "triage-sync";
const IDB_NAME = "oncotriage-offline";
const IDB_STORE = "pending_submissions";

const PRECACHE_URLS = [
  "/",
  "/dashboard",
  "/static/css/main.css",
  "/static/manifest.json",
];

// ─── Install: precache app shell ──────────────────────────────────────────────

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting()),
  );
});

// ─── Activate: purge stale caches ─────────────────────────────────────────────

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== CACHE_NAME)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

// ─── Fetch: network-first for API, cache-first for assets ─────────────────────

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only intercept same-origin requests
  if (url.origin !== self.location.origin) return;

  if (url.pathname === "/api/triage/assess" && request.method === "POST") {
    event.respondWith(handleTriageAssess(request));
    return;
  }

  // Static assets + pages: stale-while-revalidate
  event.respondWith(
    caches.match(request).then((cached) => {
      const networkFetch = fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => cached);
      return cached || networkFetch;
    }),
  );
});

// ─── Background Sync: replay queued triage submissions ────────────────────────

self.addEventListener("sync", (event) => {
  if (event.tag === SYNC_TAG) {
    event.waitUntil(replayPendingSubmissions());
  }
});

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function handleTriageAssess(request) {
  try {
    const response = await fetch(request.clone());
    return response;
  } catch {
    // Network unavailable — queue the submission
    const body = await request.clone().text();
    await queueSubmission({ url: request.url, body, timestamp: Date.now() });

    // Register background sync if available
    if ("sync" in self.registration) {
      await self.registration.sync.register(SYNC_TAG);
    }

    // Return an offline acknowledgement so the UI can inform the user
    return new Response(
      JSON.stringify({
        offline: true,
        message:
          "You are offline. Your triage request has been saved and will be submitted automatically when your connection is restored.",
      }),
      {
        status: 202,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
}

async function queueSubmission(entry) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, "readwrite");
    tx.objectStore(IDB_STORE).add(entry);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

async function replayPendingSubmissions() {
  const db = await openDB();
  const entries = await getAllEntries(db);

  for (const entry of entries) {
    try {
      await fetch(entry.url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: entry.body,
      });
      await deleteEntry(db, entry.id);
    } catch {
      // Still offline — leave in queue; sync will retry
    }
  }
}

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(IDB_STORE)) {
        db.createObjectStore(IDB_STORE, { keyPath: "id", autoIncrement: true });
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = () => reject(req.error);
  });
}

function getAllEntries(db) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, "readonly");
    const req = tx.objectStore(IDB_STORE).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function deleteEntry(db, id) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, "readwrite");
    const req = tx.objectStore(IDB_STORE).delete(id);
    req.onsuccess = resolve;
    req.onerror = () => reject(req.error);
  });
}
