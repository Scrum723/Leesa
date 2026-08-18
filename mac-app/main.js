const {
  app,
  BrowserWindow,
  shell,
  ipcMain,
  dialog,
  Menu,
  Tray,
  nativeImage,
} = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const Store = require("electron-store");

const store = new Store({
  name: "doc-weather-liaison",
  defaults: {
    railwayUrl: "https://social-media-liaison-production.up.railway.app",
    contentLibrary: path.join(
      app.getPath("home"),
      "Desktop",
      "Doc Weather Content"
    ),
    projectRoot: path.join(app.getPath("home"), "social-media-liaison"),
    startLocalAgent: true,
  },
});

let mainWindow = null;
let agentProc = null;
let tray = null;

const VIDEO_EXTS = new Set([".mp4", ".mov", ".m4v", ".avi", ".mkv"]);
const ARTICLE_EXTS = new Set([".md", ".txt", ".markdown"]);

function ensureLibrary(root) {
  const dirs = [
    "videos/inbox",
    "videos/ready",
    "videos/posted",
    "articles/inbox",
    "articles/ready",
    "articles/posted",
    "bundles/_TEMPLATE",
    "assets",
  ];
  for (const d of dirs) {
    fs.mkdirSync(path.join(root, d), { recursive: true });
  }
  const insight = path.join(root, "bundles/_TEMPLATE/insight.md");
  if (!fs.existsSync(insight)) {
    fs.writeFileSync(
      insight,
      "# Title of your insight\n\nHook first.\n\nYour take…\n\nFull links → https://linktr.ee/URP\n",
      "utf8"
    );
  }
  const meta = path.join(root, "bundles/_TEMPLATE/meta.yaml");
  if (!fs.existsSync(meta)) {
    fs.writeFileSync(
      meta,
      'title_hint: "Your title hint"\nplatforms: [x, instagram, tiktok, youtube]\ncontent_type: bundle\ntags: [WNY, Buffalo]\ncta: "https://linktr.ee/URP"\n',
      "utf8"
    );
  }
  const readme = path.join(root, "README.txt");
  if (!fs.existsSync(readme)) {
    fs.writeFileSync(
      readme,
      "videos/ready = clips\narticles/ready = writing\nbundles/ = video + insight.md + meta.yaml\n",
      "utf8"
    );
  }
}

function scanLibrary(root) {
  ensureLibrary(root);
  const items = [];

  function scanFiles(kind, stage, dir, exts) {
    if (!fs.existsSync(dir)) return;
    for (const name of fs.readdirSync(dir)) {
      if (name.startsWith(".")) continue;
      const full = path.join(dir, name);
      const st = fs.statSync(full);
      if (!st.isFile()) continue;
      const ext = path.extname(name).toLowerCase();
      if (!exts.has(ext)) continue;
      items.push({
        kind,
        status_folder: stage,
        title_hint: path.basename(name, ext).replace(/[-_]/g, " "),
        path: full,
        video_path: kind === "video" ? full : "",
        article_path: kind === "article" ? full : "",
      });
    }
  }

  for (const stage of ["inbox", "ready", "posted"]) {
    scanFiles("video", stage, path.join(root, "videos", stage), VIDEO_EXTS);
    scanFiles("article", stage, path.join(root, "articles", stage), ARTICLE_EXTS);
  }

  const bundles = path.join(root, "bundles");
  if (fs.existsSync(bundles)) {
    for (const name of fs.readdirSync(bundles)) {
      if (name.startsWith("_") || name.startsWith(".")) continue;
      const folder = path.join(bundles, name);
      if (!fs.statSync(folder).isDirectory()) continue;
      let video = "";
      let article = "";
      for (const f of fs.readdirSync(folder)) {
        const full = path.join(folder, f);
        if (!fs.statSync(full).isFile()) continue;
        const ext = path.extname(f).toLowerCase();
        if (VIDEO_EXTS.has(ext) && !video) video = full;
        if (ARTICLE_EXTS.has(ext) && !article) article = full;
      }
      if (!video && !article) continue;
      let stage = "ready";
      if (fs.existsSync(path.join(folder, ".posted"))) stage = "posted";
      items.push({
        kind: video && article ? "bundle" : video ? "video" : "article",
        status_folder: stage,
        title_hint: name.replace(/[-_]/g, " "),
        path: folder,
        video_path: video,
        article_path: article,
      });
    }
  }
  return items;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    title: "Doc Weather Liaison",
    backgroundColor: "#0b1220",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function startLocalAgent() {
  if (!store.get("startLocalAgent")) return;
  const projectRoot = store.get("projectRoot");
  const python = path.join(projectRoot, ".venv", "bin", "python");
  const runPy = path.join(projectRoot, "run.py");
  if (!fs.existsSync(runPy)) {
    console.warn("Project run.py not found:", runPy);
    return;
  }
  const bin = fs.existsSync(python) ? python : "python3";
  const lib = store.get("contentLibrary");
  const env = {
    ...process.env,
    CONTENT_LIBRARY: lib,
    VIDEO_INBOX: path.join(lib, "videos", "ready"),
    DASHBOARD_PORT: "8787",
    DASHBOARD_HOST: "127.0.0.1",
  };
  agentProc = spawn(bin, [runPy, "--no-dashboard"], {
    cwd: projectRoot,
    env,
    stdio: "ignore",
    detached: false,
  });
  agentProc.on("exit", (code) => {
    console.log("local agent exited", code);
    agentProc = null;
  });
}

function stopLocalAgent() {
  if (agentProc) {
    try {
      agentProc.kill("SIGTERM");
    } catch (_) {}
    agentProc = null;
  }
}

function buildMenu() {
  const template = [
    {
      label: app.name,
      submenu: [
        { role: "about" },
        { type: "separator" },
        {
          label: "Open Content Library in Finder",
          click: () => {
            const root = store.get("contentLibrary");
            ensureLibrary(root);
            shell.openPath(root);
          },
        },
        {
          label: "Open Railway Dashboard in Browser",
          click: () => shell.openExternal(store.get("railwayUrl")),
        },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    { role: "editMenu" },
    { role: "viewMenu" },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  ensureLibrary(store.get("contentLibrary"));
  buildMenu();
  createWindow();
  startLocalAgent();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  stopLocalAgent();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => stopLocalAgent());

ipcMain.handle("get-config", () => ({
  railwayUrl: store.get("railwayUrl"),
  contentLibrary: store.get("contentLibrary"),
  projectRoot: store.get("projectRoot"),
  startLocalAgent: store.get("startLocalAgent"),
  agentRunning: Boolean(agentProc),
}));

ipcMain.handle("set-config", (_e, patch) => {
  for (const [k, v] of Object.entries(patch || {})) {
    if (v !== undefined) store.set(k, v);
  }
  return {
    railwayUrl: store.get("railwayUrl"),
    contentLibrary: store.get("contentLibrary"),
    projectRoot: store.get("projectRoot"),
    startLocalAgent: store.get("startLocalAgent"),
    agentRunning: Boolean(agentProc),
  };
});

ipcMain.handle("scan-library", () => {
  const root = store.get("contentLibrary");
  return { root, items: scanLibrary(root) };
});

ipcMain.handle("open-library", () => {
  const root = store.get("contentLibrary");
  ensureLibrary(root);
  return shell.openPath(root);
});

ipcMain.handle("open-subfolder", (_e, rel) => {
  const root = store.get("contentLibrary");
  const target = path.join(root, rel || "");
  fs.mkdirSync(target, { recursive: true });
  return shell.openPath(target);
});

ipcMain.handle("choose-library", async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory", "createDirectory"],
    defaultPath: store.get("contentLibrary"),
  });
  if (res.canceled || !res.filePaths[0]) return store.get("contentLibrary");
  store.set("contentLibrary", res.filePaths[0]);
  ensureLibrary(res.filePaths[0]);
  return res.filePaths[0];
});

ipcMain.handle("new-bundle", (_e, slug) => {
  const root = store.get("contentLibrary");
  ensureLibrary(root);
  const safe =
    (slug || new Date().toISOString().slice(0, 10) + "-story")
      .replace(/[^\w\-]+/g, "-")
      .replace(/-+/g, "-")
      .toLowerCase() || "story";
  const dest = path.join(root, "bundles", safe);
  fs.mkdirSync(dest, { recursive: true });
  const tpl = path.join(root, "bundles/_TEMPLATE");
  for (const f of fs.readdirSync(tpl)) {
    fs.copyFileSync(path.join(tpl, f), path.join(dest, f));
  }
  shell.openPath(dest);
  return dest;
});
