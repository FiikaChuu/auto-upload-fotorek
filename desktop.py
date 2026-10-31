"""Windows desktop uploader. Google credentials remain on the local computer."""
import json
import os
import queue
import re
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
BASE = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent


def number(value):
    match = re.match(r'^(\d+)(?=$|[\s._-])', str(value).strip())
    return int(match[1]) if match else None


def detect(rows):
    aliases = {'no': {'no', 'nomor', 'number'}, 'pic': {'pic', 'penanggungjawab'},
               'link': {'linkdrive', 'linkgoogledrive', 'tautandrive'}}
    for index, row in enumerate(rows):
        found = {}
        for col, value in enumerate(row):
            normalized = re.sub(r'[^a-z0-9]', '', str(value).lower())
            for name, options in aliases.items():
                if normalized in options:
                    if name in found:
                        raise ValueError('Header kolom ganda; rapikan header terlebih dahulu.')
                    found[name] = col
        if len(found) == 3:
            return index, found
    raise ValueError('Header No., PIC, dan Link Drive tidak ditemukan dalam 50 baris pertama.')


def column(index):
    result = ''
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def extract(value, kind):
    match = re.search(r'/spreadsheets/d/([\w-]+)' if kind == 'sheet' else r'/folders/([\w-]+)', value)
    if match:
        return match[1]
    if re.fullmatch(r'[\w-]+', value):
        return value
    raise ValueError('Tautan ' + kind + ' tidak valid.')


class App:
    def __init__(self, root):
        self.root = root
        root.title('Afzal • Drive & Sheets Uploader')
        root.geometry('1000x760')
        self.events = queue.Queue()
        self.services = None
        self.prepared = None
        self.checkpoints = {}
        self.cancelled = threading.Event()
        self.busy = False
        self.fields = {}
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Folder → Drive → Sheets, otomatis.', font=('Segoe UI', 21, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Khusus PIC afzal · pilih tab bulanan · cocokkan nomor folder dengan No. konten').pack(anchor='w', pady=(4, 16))
        source = ttk.LabelFrame(outer, text='1. Tujuan & filter', padding=12)
        source.pack(fill='x')
        source.columnconfigure(1, weight=1)
        for index, (key, label, default) in enumerate([
            ('drive', 'Tautan folder Google Drive', ''), ('sheet', 'Tautan Google Sheets', ''),
            ('oauth', 'OAuth JSON (sekali saja)', str(BASE / 'credentials.json')),
            ('tab', 'Tab bulanan', ''), ('first', 'Nomor konten mulai', '1'), ('last', 'Sampai nomor', '100')]):
            ttk.Label(source, text=label).grid(row=index, column=0, sticky='w', padx=(0, 16), pady=5)
            variable = tk.StringVar(value=default)
            self.fields[key] = variable
            widget = ttk.Combobox(source, textvariable=variable, state='readonly') if key == 'tab' else ttk.Entry(source, textvariable=variable)
            widget.grid(row=index, column=1, sticky='ew', pady=5)
            if key == 'tab':
                self.tabs = widget
                ttk.Button(source, text='Muat tab / login Google', command=lambda: self.work(self.load_tabs)).grid(row=index, column=2, padx=8)
            if key == 'oauth':
                ttk.Button(source, text='Pilih JSON…', command=self.pick_json).grid(row=index, column=2, padx=8)
        folders = ttk.LabelFrame(outer, text='2. Folder sumber di komputer ini', padding=12)
        folders.pack(fill='x', pady=12)
        self.fields['folder'] = tk.StringVar()
        ttk.Entry(folders, textvariable=self.fields['folder']).pack(side='left', fill='x', expand=True)
        ttk.Button(folders, text='Pilih folder induk…', command=self.pick_folder).pack(side='left', padx=8)
        ttk.Label(outer, text='Contoh: D:\\Bahan\\11, D:\\Bahan\\12. Pilih D:\\Bahan. Subfolder ikut diunggah; link terisi dilewati.').pack(anchor='w')
        buttons = ttk.Frame(outer)
        buttons.pack(fill='x', pady=12)
        ttk.Button(buttons, text='3. Pratinjau Afzal', command=lambda: self.work(self.preview)).pack(side='left')
        ttk.Button(buttons, text='4. Mulai upload', command=lambda: self.work(self.run)).pack(side='left', padx=8)
        ttk.Button(buttons, text='Batalkan setelah file aktif', command=self.cancelled.set).pack(side='left')
        self.table = ttk.Treeview(outer, columns=('no', 'row', 'folder', 'status'), show='headings', height=8)
        for key, title in [('no', 'No.'), ('row', 'Baris Sheets'), ('folder', 'Folder'), ('status', 'Status')]:
            self.table.heading(key, text=title)
            self.table.column(key, width=90 if key in ('no', 'row') else 320)
        self.table.pack(fill='both', expand=True)
        self.log = tk.Text(outer, height=7, state='disabled', wrap='word')
        self.log.pack(fill='x', pady=(12, 0))
        self.root.after(100, self.poll)

    def pick_json(self):
        path = filedialog.askopenfilename(filetypes=[('OAuth JSON', '*.json')])
        if path:
            self.fields['oauth'].set(path)
            self.services = None
            self.checkpoints.clear()

    def pick_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.fields['folder'].set(path)

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == 'log':
                self.log.configure(state='normal')
                self.log.insert('end', value + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
            elif kind == 'tabs':
                self.tabs['values'] = value
                self.fields['tab'].set('')
            elif kind == 'rows':
                self.table.delete(*self.table.get_children())
                for item in value:
                    self.table.insert('', 'end', values=item)
            elif kind == 'done':
                self.busy = False
        self.root.after(100, self.poll)

    def work(self, operation):
        if self.busy:
            return
        self.values = {k: v.get().strip() for k, v in self.fields.items()}
        self.busy = True
        self.cancelled.clear()
        def task():
            try:
                operation()
            except Exception as exc:
                self.events.put(('log', 'Gagal: ' + str(exc)))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=task, daemon=True).start()

    def connect(self):
        if self.services:
            return self.services
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        path = Path(self.values['oauth'])
        if not path.is_file():
            raise ValueError('Pilih credentials.json OAuth jenis Desktop app. Lihat README; tidak perlu memasukkan password di aplikasi.')
        with path.open(encoding='utf-8') as handle:
            if 'installed' not in json.load(handle):
                raise ValueError('JSON harus dari OAuth client jenis Desktop app, bukan Web application.')
        self.events.put(('log', 'Browser login Google akan terbuka. Izinkan akses Drive dan Sheets.'))
        flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
        credentials = flow.run_local_server(port=0, timeout_seconds=180, success_message='Login berhasil. Silakan kembali ke aplikasi Fotorek.')
        self.services = (build('drive', 'v3', credentials=credentials, cache_discovery=False),
                         build('sheets', 'v4', credentials=credentials, cache_discovery=False))
        return self.services

    def load_tabs(self):
        _, sheets = self.connect()
        result = sheets.spreadsheets().get(spreadsheetId=extract(self.values['sheet'], 'sheet'), fields='sheets.properties.title').execute()
        self.events.put(('tabs', [s['properties']['title'] for s in result['sheets']]))
        self.events.put(('log', 'Pilih tab bulan yang sesuai, lalu klik Pratinjau.'))

    def read(self, sheets, sid, tab):
        name = "'" + tab.replace("'", "''") + "'"
        rows = sheets.spreadsheets().values().get(spreadsheetId=sid, range=name, valueRenderOption='FORMATTED_VALUE').execute().get('values', [])
        header, cols = detect(rows[:50])
        return name, rows, header, cols

    def prepare(self):
        drive, sheets = self.connect()
        sid, did = extract(self.values['sheet'], 'sheet'), extract(self.values['drive'], 'drive')
        if not self.values['tab']:
            raise ValueError('Pilih tab bulanan terlebih dahulu.')
        first, last = int(self.values['first']), int(self.values['last'])
        if first < 0 or last < first:
            raise ValueError('Rentang nomor tidak valid.')
        target = drive.files().get(fileId=did, fields='mimeType,capabilities(canAddChildren)', supportsAllDrives=True).execute()
        if target['mimeType'] != 'application/vnd.google-apps.folder' or not target.get('capabilities', {}).get('canAddChildren'):
            raise ValueError('Folder Drive tujuan tidak dapat diisi oleh akun ini.')
        root = Path(self.values['folder'])
        if not self.values['folder'] or not root.is_dir():
            raise ValueError('Pilih folder sumber yang valid.')
        folders = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and number(p.name) is not None and first <= number(p.name) <= last]
        if not folders:
            raise ValueError('Tidak ada folder bernomor dalam rentang tersebut di folder induk yang dipilih.')
        name, rows, header, cols = self.read(sheets, sid, self.values['tab'])
        def value(row, key):
            return str(row[cols[key]]).strip() if len(row) > cols[key] else ''
        jobs = []
        for folder in sorted(folders):
            num = number(folder.name)
            matches = [(i + 1, row) for i, row in enumerate(rows) if i > header and number(value(row, 'no')) == num and value(row, 'pic').lower() == 'afzal']
            status = 'Siap'
            if sum(number(p.name) == num for p in folders) > 1:
                status = 'Nomor folder duplikat'
            elif len(matches) != 1:
                status = 'Baris ambigu' if matches else 'No. + PIC afzal tidak ditemukan'
            elif value(matches[0][1], 'link'):
                status = 'Link sudah terisi'
            jobs.append((num, matches[0][0] if len(matches) == 1 else '', folder, status))
        return (sid, did, name, cols, jobs)

    def preview(self):
        self.prepared = (dict(self.values), self.prepare())
        self.events.put(('rows', [(n, r, str(p), s) for n, r, p, s in self.prepared[1][4]]))
        self.events.put(('log', 'Pratinjau selesai. Hanya status Siap yang akan diunggah.'))

    def run(self):
        if not self.prepared or self.prepared[0] != self.values:
            raise ValueError('Pengaturan berubah atau belum diperiksa. Klik Pratinjau dahulu.')
        from googleapiclient.http import MediaFileUpload
        drive, sheets = self.connect()
        sid, did, name, cols, jobs = self.prepare()
        if (sid, did, name, cols, jobs) != self.prepared[1]:
            raise ValueError('Data Sheets/folder berubah. Klik Pratinjau lagi.')
        def create(label, parent):
            return drive.files().create(body={'name': label, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent]}, fields='id', supportsAllDrives=True).execute()['id']
        for num, row, folder, status in jobs:
            if self.cancelled.is_set():
                break
            if status != 'Siap':
                continue
            key = (did, str(folder.resolve()))
            cp = self.checkpoints.get(key)
            if not cp:
                cp = {'id': create(folder.name, did), 'dirs': {}, 'files': set()}
                self.checkpoints[key] = cp
            url = 'https://drive.google.com/drive/folders/' + cp['id']
            self.events.put(('log', folder.name + ': ' + url))
            for current, dirs, files in os.walk(folder, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(current) / d).is_symlink()]
                relative = Path(current).relative_to(folder)
                if relative == Path('.'):
                    parent = cp['id']
                else:
                    if relative not in cp['dirs']:
                        parent_path = relative.parent
                        cp['dirs'][relative] = create(relative.name, cp['id'] if parent_path == Path('.') else cp['dirs'][parent_path])
                    parent = cp['dirs'][relative]
                for filename in files:
                    if self.cancelled.is_set():
                        self.events.put(('log', 'Dibatalkan. Folder parsial tetap di Drive; link belum ditulis.'))
                        return
                    path = Path(current) / filename
                    if path.is_symlink():
                        continue
                    fingerprint = (str(path.relative_to(folder)), path.stat().st_size, path.stat().st_mtime_ns)
                    if fingerprint in cp['files']:
                        continue
                    request = drive.files().create(body={'name': filename, 'parents': [parent]}, media_body=MediaFileUpload(str(path), resumable=True, chunksize=8*1024*1024), fields='id', supportsAllDrives=True)
                    response = None
                    while response is None:
                        _, response = request.next_chunk()
                    cp['files'].add(fingerprint)
                    self.events.put(('log', 'Terunggah: ' + str(path.relative_to(folder))))
            if self.cancelled.is_set():
                self.events.put(('log', 'Dibatalkan. Folder tersimpan, link belum ditulis: ' + url))
                return
            # Read current headers, number, PIC and destination immediately before writing.
            _, live, _, live_cols = self.read(sheets, sid, self.values['tab'])
            cells = live[row-1] if len(live) >= row else []
            def at(key):
                return str(cells[cols[key]]).strip() if len(cells) > cols[key] else ''
            if live_cols != cols or number(at('no')) != num or at('pic').lower() != 'afzal' or at('link'):
                raise ValueError('Sheets berubah. Upload sudah tersimpan di ' + url + '; link belum ditulis.')
            sheets.spreadsheets().values().update(spreadsheetId=sid, range=f'{name}!{column(cols["link"])}{row}', valueInputOption='RAW', body={'values': [[url]]}).execute()
            self.events.put(('log', f'Selesai: No. {num} → {name}, baris {row}'))
        self.prepared = None
        self.events.put(('log', 'Proses berakhir. Klik Pratinjau untuk status terbaru.'))


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
