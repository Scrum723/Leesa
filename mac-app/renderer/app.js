async function refresh() {
  const cfg = await window.liaison.getConfig();
  document.getElementById("lib-path").textContent = cfg.contentLibrary;
  document.getElementById("fallback-url").textContent = cfg.railwayUrl;
  const pill = document.getElementById("agent-pill");
  pill.textContent = cfg.agentRunning ? "local agent: on" : "local agent: off";
  pill.classList.toggle("on", cfg.agentRunning);
  document.getElementById("status-line").textContent = cfg.agentRunning
    ? "Local agent running · library + posting on this Mac · dashboard on Railway"
    : "Dashboard only · start agent via project run.py if needed";

  const webview = document.getElementById("dash");
  if (webview && webview.src !== cfg.railwayUrl) {
    webview.src = cfg.railwayUrl;
  }

  const scan = await window.liaison.scanLibrary();
  const items = scan.items || [];
  const counts = {
    video: items.filter((i) => i.kind === "video").length,
    article: items.filter((i) => i.kind === "article").length,
    bundle: items.filter((i) => i.kind === "bundle").length,
    ready: items.filter((i) => i.status_folder === "ready").length,
  };
  document.getElementById("counts").textContent =
    `${counts.ready} ready · ${counts.video} videos · ${counts.article} articles · ${counts.bundle} bundles`;

  const ul = document.getElementById("item-list");
  ul.innerHTML = "";
  items
    .filter((i) => i.status_folder === "ready")
    .slice(0, 40)
    .forEach((it) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="tag">${it.kind}</span>${escapeHtml(it.title_hint)}`;
      ul.appendChild(li);
    });
  if (!items.length) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = "Library empty — drop content into ready folders.";
    ul.appendChild(li);
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

document.getElementById("btn-dashboard").onclick = async () => {
  const cfg = await window.liaison.getConfig();
  document.getElementById("dash").src = cfg.railwayUrl;
};

document.getElementById("btn-browser").onclick = async () => {
  const cfg = await window.liaison.getConfig();
  // open via shell through temporary link
  window.open(cfg.railwayUrl, "_blank");
};

document.getElementById("btn-open-lib").onclick = () => window.liaison.openLibrary();
document.getElementById("btn-choose-lib").onclick = async () => {
  await window.liaison.chooseLibrary();
  refresh();
};
document.getElementById("btn-videos").onclick = () =>
  window.liaison.openSubfolder("videos/ready");
document.getElementById("btn-articles").onclick = () =>
  window.liaison.openSubfolder("articles/ready");
document.getElementById("btn-new-bundle").onclick = async () => {
  const slug = prompt(
    "Bundle folder name (e.g. 2026-07-31-weekend-storm)",
    new Date().toISOString().slice(0, 10) + "-story"
  );
  if (slug) await window.liaison.newBundle(slug);
  refresh();
};
document.getElementById("btn-scan").onclick = () => refresh();

refresh();
setInterval(refresh, 15000);
