const {contextBridge,ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('monitor',Object.freeze({request:(action,payload)=>ipcRenderer.invoke('monitor',action,payload)}));
