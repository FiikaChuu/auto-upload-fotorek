import {plan,columnIndex,quotedTab} from './match.js';
const $=id=>document.getElementById(id);
let token='',expires=0,groups=new Map(),approved=null,busy=false,mode='single';
// Retain upload checkpoints for retries in this tab; never persist credentials.
const checkpoints=new Map();
const log=message=>{$('log').textContent+='\n'+message;};
function invalidate(){approved=null;$('run').disabled=true;}
function auth(){if(!token||Date.now()>=expires)throw Error('Hubungkan ulang akun Google; sesi telah habis.');}
async function api(url,options={}){
 auth();const r=await fetch(url,{...options,headers:{Authorization:`Bearer ${token}`,...options.headers}});
 if(!r.ok){let message=`HTTP ${r.status}`;try{message=(await r.json()).error?.message||message;}catch{}throw Error(message);}
 return r.status===204?null:r.json();
}
function idOf(value,type){const m=value.match(type==='sheet'?/\/spreadsheets\/d\/([\w-]+)/:/\/folders\/([\w-]+)/);if(m)return m[1];if(/^[\w-]+$/.test(value))return value;throw Error('Link atau ID '+type+' tidak valid');}
function config(){
 const c=Object.fromEntries(['tab','no','pic','link','person'].map(k=>[k,$(k).value.trim()]));
 c.start=Number($('start').value);c.end=Number($('end').value);
 if(!c.tab||!c.person||!Number.isSafeInteger(c.start)||!Number.isSafeInteger(c.end)||c.start<1||c.end<c.start||c.end-c.start>10000)throw Error('Isi tab, PIC, dan rentang baris yang valid (maksimal 10.001 baris)');
 c.sheet=idOf($('sheet').value.trim(),'sheet');c.drive=idOf($('drive').value.trim(),'drive');
 for(const key of ['no','pic','link']){columnIndex(c[key]);c[key]=c[key].toUpperCase();}return c;
}
async function rows(c,start=c.start,end=c.end){
 const max=Math.max(...['no','pic','link'].map(k=>columnIndex(c[k])));let n=max+1,col='';while(n){n--;col=String.fromCharCode(65+n%26)+col;n=Math.floor(n/26);}
 const range=`${quotedTab(c.tab)}!A${start}:${col}${end}`;
 return (await api(`https://sheets.googleapis.com/v4/spreadsheets/${c.sheet}/values/${encodeURIComponent(range)}?valueRenderOption=FORMATTED_VALUE`)).values||[];
}
function render(items){const table=document.createElement('table');const head=table.insertRow();for(const label of ['Folder','Baris Sheets','Hasil']){const th=document.createElement('th');th.textContent=label;head.append(th);}for(const p of items){const row=table.insertRow();for(const v of [p.folder,p.row??'—',p.error||'Siap'])row.insertCell().textContent=v;}$('previewResult').replaceChildren(table);}
function updateSelection(){$('selection').textContent=[...groups].map(([name,files])=>`${name}: ${files.length} file`).join(' · ')||'Belum ada folder.';invalidate();}
async function guard(fn){if(busy)return;busy=true;document.querySelectorAll('button,input').forEach(e=>e.disabled=true);try{await fn();}catch(e){log('Gagal: '+e.message);}finally{busy=false;document.querySelectorAll('button,input').forEach(e=>e.disabled=false);$('run').disabled=!approved;}}
$('login').onclick=()=>{
 if(!window.google?.accounts?.oauth2){log('Google Identity belum dimuat. Periksa koneksi dan muat ulang.');return;}
 if(!$('client').value.trim()){log('Isi OAuth Client ID terlebih dahulu.');return;}
 google.accounts.oauth2.initTokenClient({client_id:$('client').value.trim(),scope:'https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/spreadsheets',callback:r=>{
  if(r.error){log('Login gagal: '+r.error);return;}
  token=r.access_token;expires=Date.now()+Number(r.expires_in)*1000-60000;checkpoints.clear();invalidate();$('account').textContent='Terhubung. Periksa kembali pencocokan sebelum upload.';
 },error_callback:e=>log('Login tidak selesai: '+e.type)}).requestAccessToken();
};
for(const el of document.querySelectorAll('input:not([type=file])'))el.addEventListener('input',invalidate);
$('loadTabs').onclick=()=>guard(async()=>{
 const id=idOf($('sheet').value.trim(),'sheet');
 const result=await api(`https://sheets.googleapis.com/v4/spreadsheets/${id}?fields=sheets.properties(title)`);
 const options=(result.sheets||[]).map(s=>{const option=document.createElement('option');option.value=s.properties.title;return option;});
 $('tabs').replaceChildren(...options);log('Daftar tab dimuat. Pilih tab bulanan di kolom Tab bulanan.');
});
$('add').onclick=()=>{mode='single';$('files').click();};$('parent').onclick=()=>{mode='parent';$('files').click();};
$('files').onchange=()=>{
 const incoming=new Map();for(const file of $('files').files){const parts=file.webkitRelativePath.split('/');if(mode==='parent')parts.shift();if(parts.length<2){log('Dilewati: '+file.name+' (bukan di folder bernomor)');continue;}const name=parts.shift();if(!incoming.has(name))incoming.set(name,[]);incoming.get(name).push({file,path:parts.join('/')});}
 for(const [name,files] of incoming){if(groups.has(name)){log('Folder sudah dipilih, dilewati: '+name);continue;}groups.set(name,files);}updateSelection();$('files').value='';
};
$('clear').onclick=()=>{groups.clear();$('previewResult').replaceChildren();updateSelection();};
$('preview').onclick=()=>guard(async()=>{
 invalidate();if(!groups.size)throw Error('Pilih folder terlebih dahulu');const c=config();
 const drive=await api(`https://www.googleapis.com/drive/v3/files/${c.drive}?fields=id,mimeType,capabilities(canAddChildren)&supportsAllDrives=true`);
 if(drive.mimeType!=='application/vnd.google-apps.folder'||!drive.capabilities?.canAddChildren)throw Error('Tujuan harus berupa folder Drive yang dapat Anda isi');
 const items=plan(await rows(c),[...groups.keys()],c);render(items);if(!items.some(x=>!x.error))throw Error('Tidak ada folder yang cocok');approved={c,items};log('Pratinjau siap. Hanya folder berstatus Siap akan diproses.');
});
async function createFolder(name,parent){return api('https://www.googleapis.com/drive/v3/files?fields=id,webViewLink&supportsAllDrives=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,mimeType:'application/vnd.google-apps.folder',parents:[parent]})});}
async function upload(file,parent){
 auth();const begin=await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json','X-Upload-Content-Type':file.type||'application/octet-stream'},body:JSON.stringify({name:file.name,parents:[parent]})});
 if(!begin.ok)throw Error('Tidak dapat memulai upload: HTTP '+begin.status);
 const location=begin.headers.get('Location');if(!location)throw Error('Google tidak mengembalikan lokasi upload');
 const result=await fetch(location,{method:'PUT',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});
 if(!result.ok)throw Error(`Upload ${file.name} gagal: HTTP ${result.status}`);return result.json();
}
$('run').onclick=()=>guard(async()=>{
 const {c,items}=approved;invalidate();
 for(const item of items.filter(x=>!x.error)){
  try{
   const current=plan(await rows(c),[item.folder],c)[0];if(current.error||current.row!==item.row)throw Error('Data Sheets berubah: '+(current.error||'baris berpindah')+'. Periksa ulang.');
   const key=JSON.stringify([c.drive,item.folder,groups.get(item.folder).map(e=>[e.path,e.file.size,e.file.lastModified])]);let cp=checkpoints.get(key);
   if(!cp){const folder=await createFolder(item.folder,c.drive);cp={id:folder.id,dirs:new Map(),done:new Set()};checkpoints.set(key,cp);}
   const url=`https://drive.google.com/drive/folders/${cp.id}`;log(`${item.folder}: ${url}`);
   for(const entry of groups.get(item.folder)){
    if(cp.done.has(entry.path))continue;
    const parts=entry.path.split('/');parts.pop();let parent=cp.id,path='';
    for(const part of parts){path+=part+'/';if(!cp.dirs.has(path))cp.dirs.set(path,(await createFolder(part,parent)).id);parent=cp.dirs.get(path);}
    await upload(entry.file,parent);cp.done.add(entry.path);log(`Terunggah: ${item.folder}/${entry.path}`);
   }
   const last=plan(await rows(c),[item.folder],c)[0];if(last.error||last.row!==item.row)throw Error('Folder sudah terunggah tetapi Sheets berubah. Link belum ditulis; periksa ulang.');
   const range=`${quotedTab(c.tab)}!${c.link}${item.row}`;
   await api(`https://sheets.googleapis.com/v4/spreadsheets/${c.sheet}/values/${encodeURIComponent(range)}?valueInputOption=RAW`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({range,majorDimension:'ROWS',values:[[url]]})});
   log(`Selesai: ${item.folder} → ${range}`);
  }catch(e){log(`${item.folder}: ${e.message}`);log('Proses dihentikan. Periksa ulang lalu coba lagi pada tab ini; file yang sudah berhasil diunggah akan dilewati.');break;}
 }
 log('Proses berakhir. Periksa pencocokan lagi untuk melihat status terbaru.');
});
