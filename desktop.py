"""Simple Windows UI; all network/file upload work runs outside the UI thread."""
import contextlib
import io
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import auto_upload as core
import upload_flow as flow


class Writer:
    def __init__(self, events):
        self.events = events
    def write(self, text):
        if text:
            self.events.put(('log', text))
    def flush(self):
        pass


def error_message(exc):
    from googleapiclient.errors import HttpError
    if isinstance(exc, HttpError):
        return {401:'Sesi Google habis. Klik Sambungkan Google lagi.', 403:'Akses ditolak. Pastikan Drive API dan Sheets API aktif, akun terdaftar sebagai test user, dan punya izin edit.', 404:'Folder atau Sheets tidak ditemukan. Periksa tautan dan akun yang digunakan.'}.get(exc.resp.status, f'Google API gagal (HTTP {exc.resp.status}). Coba lagi nanti.')
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return str(exc)
    return f'{type(exc).__name__}: proses belum berhasil. Periksa koneksi dan sambungkan Google kembali.'


class App:
    def __init__(self, root):
        self.root = root
        root.title('Auto Upload')
        root.geometry('980x850')
        root.minsize(790, 740)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.events = queue.Queue()
        self.clients = None
        self.folders = []
        self.prepared = None
        self.busy = False
        self.oauth = None
        self.widgets = []
        try:
            cfg = core.load(core.STATE / 'settings.json', {})
        except (ValueError, OSError):
            cfg = {}
        self.sheet = tk.StringVar(value=cfg.get('sheet', ''))
        self.drive = tk.StringVar(value=cfg.get('drive', ''))
        self.tab = tk.StringVar()
        self.status = tk.StringVar(value='Mulai dengan menyambungkan akun Google.')
        style = ttk.Style()
        style.configure('TButton', padding=(10, 7))
        outer = ttk.Frame(root, padding=18)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Auto Upload', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Folder hasil edit → Google Drive → Link Drive di Sheets · khusus PIC afzal').pack(anchor='w', pady=(2, 12))
        auth = ttk.LabelFrame(outer, text='1. Sambungkan Google', padding=10)
        auth.pack(fill='x')
        self.button(auth, 'Sambungkan Google', self.connect).pack(side='left')
        self.button(auth, 'Ganti akun', lambda: self.connect(True)).pack(side='left', padx=8)
        self.button(auth, 'Pilih OAuth JSON…', self.pick_oauth).pack(side='left', padx=(0,8))
        self.account = ttk.Label(auth, text='Belum terhubung')
        self.account.pack(side='left', padx=6)
        source = ttk.LabelFrame(outer, text='2. Pilih folder hasil edit', padding=10)
        source.pack(fill='x', pady=10)
        ttk.Label(source, text='Pilih folder 11 langsung, atau induk berisi banyak folder seperti 11, 13, 15.').pack(anchor='w')
        row = ttk.Frame(source); row.pack(fill='x', pady=(6, 0))
        self.button(row, 'Tambah folder…', self.add_folder).pack(side='left')
        self.button(row, 'Hapus pilihan', self.clear).pack(side='left', padx=8)
        self.selection = ttk.Label(source, text='Belum ada folder dipilih.', wraplength=850)
        self.selection.pack(anchor='w', pady=(6, 0))
        dest = ttk.LabelFrame(outer, text='3. Tujuan Google Drive dan Sheets', padding=10)
        dest.pack(fill='x')
        dest.columnconfigure(1, weight=1)
        for i, (title, variable) in enumerate([('Link folder Drive tujuan', self.drive), ('Link Google Sheets', self.sheet)]):
            ttk.Label(dest, text=title).grid(row=i, column=0, sticky='w', padx=(0, 12), pady=4)
            entry = ttk.Entry(dest, textvariable=variable)
            entry.grid(row=i, column=1, sticky='ew', pady=4)
            self.widgets.append(entry)
        self.button(dest, 'Muat tab', self.load_tabs).grid(row=1, column=2, padx=(8, 0))
        ttk.Label(dest, text='Tab bulan yang diproses').grid(row=2, column=0, sticky='w')
        self.combo = ttk.Combobox(dest, textvariable=self.tab, state='readonly')
        self.combo.grid(row=2, column=1, sticky='ew', pady=4)
        self.widgets.append(self.combo)
        ttk.Label(dest, text='Nomor folder dideteksi otomatis. Kolom No., PIC, dan Link Drive juga dideteksi.').grid(row=3, column=0, columnspan=3, sticky='w', pady=(6, 0))
        actions = ttk.Frame(outer); actions.pack(fill='x', pady=12)
        self.button(actions, '4. Periksa pencocokan', self.preview).pack(side='left')
        self.upload_button = self.button(actions, '5. Upload & isi Sheets', self.upload)
        self.upload_button.pack(side='left', padx=8)
        self.table = ttk.Treeview(outer, columns=('folder','number','cell','status'), show='headings', height=6)
        for key, title, width in [('folder','Folder',200),('number','No.',60),('cell','Sel Link Drive',200),('status','Hasil pemeriksaan',300)]:
            self.table.heading(key,text=title); self.table.column(key,width=width)
        self.table.pack(fill='both', expand=True)
        ttk.Label(outer,textvariable=self.status,wraplength=880).pack(anchor='w', pady=(10, 4))
        self.progress=ttk.Progressbar(outer,mode='indeterminate')
        self.progress.pack(fill='x',pady=(0,5))
        self.log = tk.Text(outer, height=7, state='disabled', wrap='word')
        self.log.pack(fill='x')
        for variable in (self.drive, self.sheet, self.tab):
            variable.trace_add('write', lambda *_: self.invalidate())
        self.sheet.trace_add('write', lambda *_: self.clear_tabs())
        self.invalidate()
        root.after(100, self.poll)

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.widgets.append(button)
        return button

    def invalidate(self):
        self.prepared = None
        self.upload_button.configure(state='disabled')

    def clear_tabs(self):
        self.combo['values'] = ()
        self.tab.set('')

    def set_busy(self, active):
        self.busy = active
        if active:
            self.progress.start()
        else:
            self.progress.stop()
        for widget in self.widgets:
            widget.configure(state='disabled' if active else ('readonly' if widget is self.combo else 'normal'))
        self.upload_button.configure(state='normal' if not active and self.prepared and any(not j['error'] for j in self.prepared['jobs']) else 'disabled')

    def work(self, task, success, status):
        if self.busy:
            return
        self.set_busy(True)
        self.status.set(status)
        def run():
            try:
                with contextlib.redirect_stdout(Writer(self.events)):
                    result = task()
                self.events.put(('success', (success, result)))
            except Exception as exc:
                self.events.put(('error', error_message(exc)))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == 'log':
                self.log.configure(state='normal'); self.log.insert('end',value); self.log.see('end'); self.log.configure(state='disabled')
            elif kind == 'success':
                callback, result = value
                try:
                    callback(result)
                except Exception as exc:
                    self.invalidate()
                    messagebox.showerror('Auto Upload',error_message(exc),parent=self.root)
            elif kind == 'error':
                self.invalidate()
                self.status.set('Proses belum berhasil. ' + value)
                messagebox.showerror('Auto Upload',value,parent=self.root)
            elif kind == 'done':
                self.set_busy(False)
        self.root.after(100,self.poll)

    def connect(self, force=False):
        if self.busy:
            return
        self.invalidate()
        path = self.oauth
        if force or not (core.STATE/'token.json').exists():
            try:
                path = str(core.client_file(path))
            except ValueError:
                path = filedialog.askopenfilename(title='Pilih OAuth JSON Desktop dari Google',filetypes=[('OAuth JSON','*.json')],parent=self.root)
                if not path:
                    return
                self.oauth = path
        self.clients = None
        self.account.configure(text='Menyambungkan…')
        def task():
            try:
                clients = None if force else core.services()
            except ValueError:
                clients = None
            if clients is None:
                # OAuth URLs do not need to be shown in the activity panel.
                with contextlib.redirect_stdout(io.StringIO()):
                    core.login(path)
                clients = core.services()
            user = clients[0].about().get(fields='user(emailAddress,displayName)').execute().get('user',{})
            return clients, user.get('emailAddress') or user.get('displayName') or 'Akun Google'
        def success(result):
            self.clients, name = result
            self.account.configure(text=name)
            self.status.set('Google terhubung. Pilih folder, isi tujuan, lalu muat tab Sheets.')
        self.work(task,success,'Selesaikan login Google di browser jika diminta…')

    def pick_oauth(self):
        path=filedialog.askopenfilename(title='Pilih OAuth JSON Desktop dari Google',filetypes=[('OAuth JSON','*.json')],parent=self.root)
        if path:
            try:
                self.oauth=str(core.client_file(path))
                self.status.set('OAuth JSON dipilih. Klik Sambungkan Google.')
            except ValueError:
                messagebox.showerror('OAuth JSON','File harus berupa OAuth client Desktop app dari Google Cloud.',parent=self.root)

    def add_folder(self):
        path = filedialog.askdirectory(title='Pilih folder hasil edit atau folder induknya',parent=self.root)
        if path:
            try:
                self.folders = flow.add_source(self.folders,path)
                self.selection.configure(text=', '.join(p.name for p in self.folders))
                self.invalidate()
            except ValueError as exc:
                messagebox.showerror('Folder belum cocok',str(exc),parent=self.root)

    def clear(self):
        self.folders=[]; self.selection.configure(text='Belum ada folder dipilih.'); self.invalidate()

    def require_google(self):
        if self.clients is None:
            messagebox.showinfo('Sambungkan Google','Klik Sambungkan Google terlebih dahulu.',parent=self.root)
            return False
        return True

    def load_tabs(self):
        if not self.require_google():
            return
        try:
            sid=core.extract(self.sheet.get().strip(),'sheet')
        except ValueError as exc:
            messagebox.showerror('Link Sheets',str(exc),parent=self.root); return
        self.invalidate()
        def success(names):
            self.combo['values']=names; self.tab.set('')
            self.status.set('Pilih tab bulanan yang sesuai, lalu klik Periksa pencocokan.')
        self.work(lambda:core.tabs(self.clients[1],sid),success,'Memuat daftar tab Sheets…')

    def preview(self):
        if not self.require_google():
            return
        folders=list(self.folders);sheet=self.sheet.get();drive=self.drive.get();tab=self.tab.get()
        self.invalidate()
        def success(prepared):
            self.prepared=prepared
            self.table.delete(*self.table.get_children())
            for job in prepared['jobs']:
                cell=f'{prepared["quoted"]}!{core.column(prepared["cols"]["link"])}{job["row"]}' if job['row'] else '—'
                self.table.insert('','end',values=(job['folder'].name,job['no'],cell,job['error'] or 'Siap diunggah'))
            core.save(core.STATE/'settings.json',{'sheet':sheet,'drive':drive})
            count=sum(not j['error'] for j in prepared['jobs'])
            self.status.set(f'{count} folder siap. Link baru ditulis setelah semua file dalam folder selesai diunggah.')
        self.work(lambda:flow.prepare(self.clients,folders,sheet,drive,tab),success,'Memeriksa nomor, PIC afzal, dan sel tujuan…')

    def upload(self):
        if not self.prepared:
            return
        count=sum(not j['error'] for j in self.prepared['jobs'])
        if not messagebox.askyesno('Mulai upload?',f'Upload {count} folder ke Drive dan tulis link ke tab {self.prepared["tab"]}?',parent=self.root):
            return
        prepared=self.prepared
        self.invalidate()
        def success(completed):
            self.status.set(f'Selesai: {completed} folder diunggah dan link ditulis ke Sheets. Klik Periksa pencocokan untuk status terbaru.')
            messagebox.showinfo('Selesai',f'{completed} folder selesai diproses.',parent=self.root)
        self.work(lambda:flow.execute(self.clients,prepared),success,'Mengunggah folder. Jangan ubah file sumber atau Sheets selama proses.')

    def close(self):
        if self.busy and not messagebox.askyesno('Proses masih berjalan','Tutup dan hentikan proses? Folder parsial bisa tersisa di Drive. File yang sudah selesai dapat dilanjutkan nanti.',parent=self.root):
            return
        self.root.destroy()


if __name__ == '__main__':
    root=tk.Tk()
    App(root)
    root.mainloop()
