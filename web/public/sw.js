/* Golf Edge service worker — push reminders only, no caching games.
 * The payload is JSON: { title, body, url }. */

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { /* defaults below */ }
  event.waitUntil(
    self.registration.showNotification(data.title || "Golf Edge", {
      body: data.body || "Picks lock soon.",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: data.url || "/friends" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/friends";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if ("focus" in w) { w.navigate(url); return w.focus(); }
      }
      return clients.openWindow(url);
    })
  );
});
