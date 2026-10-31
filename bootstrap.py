"""First-run installer with a visible status window and no console."""
import hashlib
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk

BASE=Path(__file__).resolve().parent


def prepare():
    python=BASE/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    def run(args):
        result=subprocess.run(args,cwd=BASE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',**flags)
        if result.returncode:
            raise RuntimeError(result.stdout[-6000:] or 'Perintah persiapan gagal.')
    if not python.exists():
        run([sys.executable,'-m','venv',str(BASE/'.venv')])
    requirements=BASE/'requirements.txt'
    digest=hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp=BASE/'.venv'/'auto-upload-requirements.sha256'
    check=subprocess.run([str(python),'-c','import googleapiclient, google_auth_oauthlib, tkinter'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
    if check.returncode or not stamp.exists() or stamp.read_text()!=digest:
        run([str(python),'-m','pip','install','-r',str(requirements)])
        stamp.write_text(digest)
    return python.with_name('pythonw.exe') if os.name=='nt' else python


def main():
    root=tk.Tk();root.title('Auto Upload');root.geometry('620x280')
    outer=ttk.Frame(root,padding=22);outer.pack(fill='both',expand=True)
    ttk.Label(outer,text='Menyiapkan Auto Upload',font=('Segoe UI',17,'bold')).pack(anchor='w')
    status=tk.StringVar(value='Pertama kali dapat memerlukan beberapa menit dan koneksi internet.\nAplikasi akan terbuka otomatis setelah persiapan selesai.')
    ttk.Label(outer,textvariable=status,wraplength=570).pack(anchor='w',pady=12)
    progress=ttk.Progressbar(outer,mode='indeterminate');progress.pack(fill='x');progress.start()
    events=queue.Queue()
    def worker():
        try:
            events.put(('ready',prepare()))
        except Exception as exc:
            events.put(('error',str(exc)))
    threading.Thread(target=worker,daemon=True).start()
    def poll():
        try:
            kind,value=events.get_nowait()
        except queue.Empty:
            root.after(150,poll);return
        progress.stop()
        if kind=='ready':
            try:
                subprocess.Popen([str(value),str(BASE/'desktop.py')],cwd=BASE)
                root.destroy()
            except OSError:
                status.set('Aplikasi belum dapat dibuka. Periksa instalasi Python dan ekstrak ulang seluruh file aplikasi.')
        else:
            status.set('Persiapan belum berhasil. Periksa koneksi internet dan instalasi Python 3.12, lalu buka ulang aplikasi.')
            text=tk.Text(outer,height=5,wrap='word');text.pack(fill='both',expand=True);text.insert('end',value);text.configure(state='disabled')
    root.after(150,poll);root.mainloop()


if __name__=='__main__':
    main()
