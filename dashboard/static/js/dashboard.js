// Lightweight status poll for live badge updates
(function () {
  async function ping() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const data = await res.json();
      document.body.dataset.dryRun = data.dry_run ? "1" : "0";
    } catch (_) {
      /* offline dashboard is fine */
    }
  }
  setInterval(ping, 30000);
})();
