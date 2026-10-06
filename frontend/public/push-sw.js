/**
 * Push handling, pulled into the Workbox-generated service worker via
 * `workbox.importScripts` in vite.config.ts.
 *
 * A separate file on purpose. vite-plugin-pwa's `generateSW` strategy writes the whole
 * service worker, and the alternative — switching to `injectManifest` to add these two
 * listeners — would hand us ownership of the precache setup and the deliberate caching
 * exclusions that live alongside it. `importScripts` is the documented way to add your
 * own handlers without taking that on, and push is the example the Workbox docs give
 * for it.
 *
 * Kept in `public/` rather than `src/`: it must ship as-is at a stable URL, with no
 * bundling and no content hash, because the generated service worker imports it by path.
 */

self.addEventListener("push", (event) => {
  // A push with no payload is still worth showing — better a generic nudge than a
  // silent no-op, and Chrome will surface its own "site updated in the background"
  // notice if we show nothing at all.
  let payload = { title: "Swolemates", body: "Time to plan your week.", url: "/plan" };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch {
    // Not JSON. Keep the default.
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      // Collapses with any previous unread reminder rather than stacking a week's worth
      // in the shade.
      tag: "weekly-reminder",
      data: { url: payload.url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/plan", self.location.origin).href;

  // Focus an already-open tab instead of opening a second one. `includeUncontrolled`
  // matters because a tab opened before this service worker took control isn't
  // controlled by it, and would otherwise be invisible here.
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        for (const client of clients) {
          if (new URL(client.url).origin === self.location.origin && "focus" in client) {
            return client.navigate(target).then((c) => c?.focus());
          }
        }
        return self.clients.openWindow(target);
      }),
  );
});
