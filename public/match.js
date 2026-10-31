export function numberOf(name){const m=String(name).trim().match(/^(\d+)(?=$|[\s._-])/);return m?String(Number(m[1])):null;}
export function columnIndex(value){if(!/^[A-Z]+$/i.test(value))throw Error('Kolom harus berupa huruf, misalnya A atau G');return [...value.toUpperCase()].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0)-1;}
export function quotedTab(tab){return "'"+tab.replaceAll("'","''")+"'";}
export function plan(rows,folders,cfg){
 const ni=columnIndex(cfg.no),pi=columnIndex(cfg.pic),li=columnIndex(cfg.link);
 if(new Set([ni,pi,li]).size!==3)throw Error('Kolom No., PIC, dan Link harus berbeda');
 const counts=new Map();for(const f of folders){const n=numberOf(f);if(n)counts.set(n,(counts.get(n)||0)+1);}
 return folders.map(folder=>{
  const number=numberOf(folder);let error='';
  const candidates=rows.map((values,i)=>({values,row:i+cfg.start})).filter(x=>numberOf(x.values[ni]??'')===number&&String(x.values[pi]??'').trim().toLowerCase()===cfg.person.trim().toLowerCase());
  if(!number)error='Nama folder harus diawali nomor';
  else if(counts.get(number)>1)error='Nomor folder duplikat';
  else if(candidates.length!==1)error=candidates.length?'Nomor + PIC ambigu dalam rentang':'Nomor + PIC tidak ditemukan';
  else if(String(candidates[0].values[li]??'').trim())error='Link Drive sudah terisi';
  return {folder,number,row:candidates[0]?.row,error};
 });
}
