import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const routes = {'/':'index.html','/app.js':'app.js','/match.js':'match.js','/style.css':'style.css'};
const types = {html:'text/html',js:'text/javascript',css:'text/css'};
http.createServer(async(req,res)=>{
  const file=routes[new URL(req.url,'http://localhost').pathname];
  if(!file || req.method!=='GET'){res.writeHead(404);res.end();return;}
  try {const body=await readFile(fileURLToPath(new URL(`./public/${file}`,import.meta.url)));res.writeHead(200,{'Content-Type':`${types[file.split('.').pop()]}; charset=utf-8`,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(body);}
  catch {res.writeHead(500);res.end('Tidak dapat membaca aplikasi');}
}).listen(Number(process.env.PORT||3000),'127.0.0.1',()=>console.log(`Fotorek berjalan di port ${process.env.PORT||3000}`));
