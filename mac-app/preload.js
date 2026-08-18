const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("liaison", {
  getConfig: () => ipcRenderer.invoke("get-config"),
  setConfig: (patch) => ipcRenderer.invoke("set-config", patch),
  scanLibrary: () => ipcRenderer.invoke("scan-library"),
  openLibrary: () => ipcRenderer.invoke("open-library"),
  openSubfolder: (rel) => ipcRenderer.invoke("open-subfolder", rel),
  chooseLibrary: () => ipcRenderer.invoke("choose-library"),
  newBundle: (slug) => ipcRenderer.invoke("new-bundle", slug),
});
