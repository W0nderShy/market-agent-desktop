const {app, BrowserWindow, ipcMain} = require('electron');
const {readFile} = require('node:fs/promises');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {requestSpec} = require('./policy.cjs');
const root = path.resolve(__dirname, '..');
app.setPath('userData', path.join(root,'runtime','monitor-desktop'));
const page = pathToFileURL(path.join(__dirname,'index.html')).href;
if (!app.requestSingleInstanceLock()) app.quit();
else {
  let win;
  app.on('second-instance',()=>{if(win){win.show();win.focus();}});
  app.whenReady().then(()=>{
    ipcMain.handle('monitor',async(event,action,payload)=>{
      if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame || event.senderFrame.url !== page) throw new Error('Unauthorized frame');
      const spec = requestSpec(action,payload);
      try {
        const token = (await readFile(path.join(root,'runtime','api-token'),'utf8')).trim();
        const response = await fetch(`http://127.0.0.1:8765${spec.path}`,{
          method:spec.method, headers:{'X-Monitor-Token':token,'Content-Type':'application/json'},
          body:spec.body ? JSON.stringify(spec.body):undefined,signal:AbortSignal.timeout(30000),redirect:'error'
        });
        const data = await response.json();
        if(!response.ok) return {ok:false,error:typeof data.error === 'string' ? data.error : `Request failed (${response.status})`};
        return {ok:true,data};
      } catch { return {ok:false,error:'监控服务未连接或请求超时，请检查服务状态。'}; }
    });
    win = new BrowserWindow({width:1160,height:790,minWidth:850,minHeight:600,title:'Market Agent · 监控底座',backgroundColor:'#10171e',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
    win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    win.webContents.on('will-navigate',(event)=>event.preventDefault());
    win.loadFile(path.join(__dirname,'index.html'));
  });
  app.on('window-all-closed',()=>app.quit());
}
