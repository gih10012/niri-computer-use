const {app, BrowserWindow} = require('electron');
app.setName('niri-cu-electron-probe');
app.setDesktopName('niri-cu-electron-probe.desktop');
app.whenReady().then(() => {
  app.setAccessibilitySupportEnabled(true);
  const window = new BrowserWindow({width: 800, height: 700, webPreferences: {sandbox: true, contextIsolation: true, nodeIntegration: false}});
  window.loadURL(process.argv.at(-1));
});
app.on('window-all-closed', () => app.quit());
