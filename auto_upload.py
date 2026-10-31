"""Auto Upload: terminal Google login, Sheets matching, Drive upload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from matching import number, detect, column, extract
from google_errors import api_action

BASE = Path(__file__).resolve().parent
STATE = BASE / '.auto-upload'
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    temp.replace(path)


def load(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def client_file(explicit=None):
    if explicit:
        candidates = [Path(explicit.strip('"'))]
    else:
        candidates = [BASE / 'credentials.json', *sorted(BASE.glob('client_secret*.json'))]
        if not any(p.is_file() for p in candidates):
            candidates = sorted((Path.home() / 'Downloads').glob('client_secret*.json'))
    valid = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = load(path)
        except (ValueError, OSError):
            continue
        if 'installed' in data and all(data['installed'].get(k) for k in ('client_id', 'client_secret', 'auth_uri', 'token_uri')):
            valid.append(path)
    if len(valid) == 1:
        return valid[0]
    if len(valid) > 1:
        raise ValueError('Ada beberapa OAuth JSON. Pilih satu melalui tombol Pilih OAuth JSON di aplikasi.')
    raise ValueError('OAuth Desktop JSON belum ditemukan. Salin file client_secret…json ke folder aplikasi, atau gunakan tombol Pilih OAuth JSON. File harus berjenis Desktop app.')


def login(explicit=None):
    from google_auth_oauthlib.flow import InstalledAppFlow
    path = client_file(explicit)
    print('OAuth Desktop JSON ditemukan. Browser login Google akan dibuka.')
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    creds = flow.run_local_server(port=0, timeout_seconds=180, access_type='offline', prompt='consent', success_message='Login Auto Upload berhasil. Silakan kembali ke aplikasi Auto Upload.')
    if not creds.has_scopes(SCOPES):
        raise ValueError('Izin Drive dan Sheets belum lengkap. Jalankan login lagi dan izinkan keduanya.')
    save(STATE / 'token.json', json.loads(creds.to_json()))
    print('Login berhasil. Token tersimpan lokal; berikutnya bisa langsung muat tab.')


def services():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    data = load(STATE / 'token.json')
    if not data:
        raise ValueError('Belum login. Buka Auto Upload.bat untuk login dan melanjutkan.')
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise ValueError('Sesi habis. Buka Auto Upload.bat untuk login lagi.')
        try:
            creds.refresh(Request())
        except Exception:
            raise ValueError('Sesi Google tidak dapat diperbarui. Buka Auto Upload.bat untuk login lagi.') from None
        save(STATE / 'token.json', json.loads(creds.to_json()))
    return (build('drive', 'v3', credentials=creds, cache_discovery=False),
            build('sheets', 'v4', credentials=creds, cache_discovery=False))


def ask(label, default=''):
    value = input(label + (f' [{default}]' if default else '') + ': ').strip().strip('"')
    return value or default


def tabs(sheets, sid):
    with api_action('Memuat daftar tab Google Sheets'):
        result = sheets.spreadsheets().get(spreadsheetId=sid, fields='sheets(properties(title))').execute()
    return [s['properties']['title'] for s in result.get('sheets', [])]


def account_key(drive):
    with api_action('Memeriksa identitas akun Google sebelum upload'):
        return drive.about().get(fields='user(permissionId)').execute()['user']['permissionId']


def read_sheet(sheets, sid, tab, columns=None):
    quoted = "'" + tab.replace("'", "''") + "'"
    with api_action('Membaca data Sheets pada tab ' + tab):
        rows = sheets.spreadsheets().values().get(spreadsheetId=sid, range=quoted, valueRenderOption='FORMATTED_VALUE').execute().get('values', [])
    header, cols = detect(rows[:50], columns)
    return quoted, rows, header, cols


def cell(row, cols, key):
    return str(row[cols[key]]).strip() if len(row) > cols[key] else ''


def make_plan(rows, header, cols, folders):
    jobs = []
    for folder in sorted(folders):
        num = number(folder.name)
        matches = [(i+1, row) for i, row in enumerate(rows) if i > header and number(cell(row, cols, 'no')) == num and cell(row, cols, 'pic').casefold() == 'afzal']
        error = ''
        if sum(number(p.name) == num for p in folders) > 1:
            error = 'Nomor folder duplikat'
        elif len(matches) != 1:
            error = 'No. + PIC afzal ambigu' if matches else 'No. + PIC afzal tidak ditemukan'
        elif cell(matches[0][1], cols, 'link'):
            error = 'Link sudah terisi'
        jobs.append({'folder': folder, 'no': num, 'row': matches[0][0] if len(matches) == 1 else None, 'error': error})
    return jobs


def manifest(folder):
    items = []
    for current, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(current) / d).is_symlink())
        for name in sorted(files):
            path = Path(current) / name
            if not path.is_symlink():
                stat = path.stat()
                items.append((str(path.relative_to(folder)), stat.st_size, stat.st_mtime_ns))
    return items


def upload_job(drive, sheets, sid, did, tab, job, all_folders, account, columns=None):
    from googleapiclient.http import MediaFileUpload
    folder = job['folder']
    before = manifest(folder)
    # Include account and file manifest to avoid confusing retries with new content.
    identity = [account, did, str(folder.resolve()), before]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    statefile = STATE / 'uploads' / (key + '.json')
    cp = load(statefile)
    def create(name, parent):
        with api_action('Membuat folder Drive: ' + name):
            return drive.files().create(body={'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent]}, fields='id', supportsAllDrives=True).execute()['id']
    if not cp:
        cp = {'id': create(folder.name, did), 'dirs': {}, 'files': []}
        save(statefile, cp)
    url = 'https://drive.google.com/drive/folders/' + cp['id']
    print('Folder Drive:', url, flush=True)
    for relative, size, modified in before:
        if relative in cp['files']:
            continue
        path = folder / relative
        if (path.stat().st_size, path.stat().st_mtime_ns) != (size, modified):
            raise ValueError('File sumber berubah. Upload dihentikan.')
        parent = cp['id']
        accumulated = Path()
        for part in Path(relative).parts[:-1]:
            accumulated /= part
            name = str(accumulated)
            if name not in cp['dirs']:
                cp['dirs'][name] = create(part, parent)
                save(statefile, cp)
            parent = cp['dirs'][name]
        print('  Mengunggah:', relative, flush=True)
        with api_action('Menyiapkan upload file: ' + relative):
            request = drive.files().create(body={'name': path.name, 'parents': [parent]}, media_body=MediaFileUpload(str(path), resumable=True, chunksize=8*1024*1024), fields='id', supportsAllDrives=True)
        response = None
        while response is None:
            with api_action('Mengunggah file: ' + relative):
                status, response = request.next_chunk(num_retries=2)
            if status:
                print(f'  {relative}: {status.progress():.0%}', flush=True)
        cp['files'].append(relative)
        save(statefile, cp)
        print('  Selesai:', relative, flush=True)
    if manifest(folder) != before:
        raise ValueError('Isi folder sumber berubah. Link belum ditulis: ' + url)
    quoted, rows, header, cols = read_sheet(sheets, sid, tab, columns)
    fresh = next(p for p in make_plan(rows, header, cols, all_folders) if p['folder'] == folder)
    if fresh['error'] or fresh['row'] != job['row']:
        raise ValueError('Sheets berubah. Folder tersimpan, link belum ditulis: ' + url)
    destination = f'{quoted}!{column(cols["link"])}{job["row"]}'
    with api_action('Menulis link folder ' + folder.name + ' ke ' + destination):
        sheets.spreadsheets().values().update(spreadsheetId=sid, range=destination, valueInputOption='RAW', body={'values': [[url]]}).execute()
    print('Link berhasil ditulis:', destination)


def step(index, title):
    print(f'\n=== LANGKAH {index}/6: {title} ===', flush=True)


def pick_directory(default=''):
    if os.name == 'nt':
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            try:
                return filedialog.askdirectory(title='Pilih folder hasil edit (11) atau induk berisi banyak folder nomor', initialdir=default or None, parent=root)
            finally:
                root.destroy()
        except Exception:
            print('Pemilih folder tidak tersedia. Tempel lokasi folder di bawah.')
    return ask('Lokasi folder hasil edit atau folder induknya', default)


def select_local_folders(default=''):
    step(2, 'Pilih folder hasil edit di komputer')
    print('Pilih folder bernomor (contoh 11), atau folder induk berisi 11, 13, 15, dst.')
    selected = {}
    while True:
        location = pick_directory(default)
        if not location:
            if selected:
                break
            raise ValueError('Pemilihan folder dibatalkan. Tidak ada upload.')
        root = Path(location).resolve()
        if not root.is_dir():
            raise ValueError('Folder sumber tidak ditemukan.')
        candidates = [root] if number(root.name) is not None else [p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and number(p.name) is not None]
        if not candidates:
            raise ValueError('Pilih folder bernomor atau induk yang berisi folder bernomor.')
        for folder in candidates:
            selected[str(folder.resolve())] = folder
        print('Folder terpilih:', ', '.join(p.name for p in selected.values()))
        default = str(root.parent)
        if ask('Tambah folder lain? (y/t)', 't').casefold() != 'y':
            break
    return list(selected.values())


def configure_and_upload(clients=None):
    drive, sheets = clients or services()
    cfg = load(STATE / 'settings.json', {})
    folders = select_local_folders(cfg.get('folder', ''))
    cfg['folder'] = str(folders[0].parent)
    step(3, 'Google Sheets dan tab bulanan')
    cfg['sheet'] = ask('Link Google Sheets', cfg.get('sheet', ''))
    sid = extract(cfg['sheet'], 'sheet')
    names = tabs(sheets, sid)
    for i, name in enumerate(names, 1):
        print(f'{i}. {name}')
    choice = int(ask('Pilih nomor urut TAB (bukan nomor konten)'))
    if choice < 1 or choice > len(names):
        raise ValueError('Pilihan tab tidak valid.')
    tab = names[choice-1]
    print('Tab terpilih:', tab)
    step(4, 'Folder tujuan di Google Drive')
    cfg['drive'] = ask('Link folder Drive tujuan', cfg.get('drive', ''))
    did = extract(cfg['drive'], 'drive')
    target = drive.files().get(fileId=did, fields='mimeType,capabilities(canAddChildren)', supportsAllDrives=True).execute()
    if target['mimeType'] != 'application/vnd.google-apps.folder' or not target.get('capabilities', {}).get('canAddChildren'):
        raise ValueError('Akun ini tidak dapat menambah isi folder Drive tujuan.')
    quoted, rows, header, cols = read_sheet(sheets, sid, tab)
    jobs = make_plan(rows, header, cols, folders)
    step(5, 'Pratinjau pencocokan otomatis')
    print(f'\nTab: {quoted} | PIC: afzal | Kolom otomatis: ' + ', '.join(f'{k}={column(v)}' for k,v in cols.items()))
    for job in jobs:
        destination = f'{quoted}!{column(cols["link"])}{job["row"]}' if job['row'] else '-'
        print(f'{job["folder"]} -> No. {job["no"]} -> {destination}: {job["error"] or "SIAP"}')
    save(STATE / 'settings.json', cfg)
    if not any(not j['error'] for j in jobs):
        print('Tidak ada folder yang siap. Tidak ada upload atau perubahan Sheets.')
        return
    if ask('Ketik UPLOAD untuk melanjutkan') != 'UPLOAD':
        print('Dibatalkan tanpa upload.')
        return
    step(6, 'Upload dan isi link Sheets')
    account = account_key(drive)
    for job in jobs:
        if job['error']:
            continue
        # Re-read after confirmation and immediately before creating a Drive folder.
        _, live, hi, ci = read_sheet(sheets, sid, tab)
        fresh = next(p for p in make_plan(live, hi, ci, folders) if p['folder'] == job['folder'])
        if fresh['error'] or fresh['row'] != job['row']:
            raise ValueError('Sheets berubah; jalankan pratinjau lagi sebelum upload.')
        upload_job(drive, sheets, sid, did, tab, job, folders, account)
    print('Selesai. Semua folder berstatus SIAP sudah diproses.')


def drive_folders(drive, parent):
    result = []
    page = None
    while True:
        response = drive.files().list(q=f"'{parent}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'", fields='nextPageToken,files(id,name)', pageSize=1000, pageToken=page, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        result.extend(f for f in response.get('files', []) if number(f['name']) is not None)
        page = response.get('nextPageToken')
        if not page:
            return result


def sync_drive(clients=None):
    drive, sheets = clients or services()
    cfg = load(STATE / 'settings.json', {})
    step(3, 'Google Sheets dan tab bulanan')
    cfg['sheet'] = ask('Link Google Sheets', cfg.get('sheet', ''))
    sid = extract(cfg['sheet'], 'sheet')
    names = tabs(sheets, sid)
    for i, title in enumerate(names, 1):
        print(f'{i}. {title}')
    choice = int(ask('Pilih nomor urut TAB bulanan'))
    if not 1 <= choice <= len(names):
        raise ValueError('Pilihan tab tidak valid.')
    tab = names[choice-1]
    print('Tab terpilih:', tab)
    step(4, 'Folder sumber di Google Drive')
    cfg['drive'] = ask('Link folder INDUK di Drive yang berisi 11, 13, dst.', cfg.get('drive', ''))
    did = extract(cfg['drive'], 'drive')
    folders = drive_folders(drive, did)
    if not folders:
        raise ValueError('Tidak ada subfolder bernomor yang bisa diakses dalam folder Drive ini.')
    # Use IDs as the stable reference; names may be duplicated in Google Drive.
    paths = [Path(f['name']) for f in folders]
    quoted, rows, header, cols = read_sheet(sheets, sid, tab)
    jobs = make_plan(rows, header, cols, paths)
    by_name = {f['name']: f['id'] for f in folders}
    step(5, 'Pratinjau pencocokan otomatis')
    print(f'\nTab: {tab} | PIC: afzal | Semua nomor folder dideteksi otomatis')
    for job in jobs:
        print(f'{job["folder"].name} -> baris {job["row"] or "-"}: {job["error"] or "SIAP"}')
    save(STATE / 'settings.json', cfg)
    if not any(not j['error'] for j in jobs):
        print('Tidak ada link yang perlu ditulis.')
        return
    if ask('Ketik ISI untuk menulis link folder ke Sheets') != 'ISI':
        print('Dibatalkan tanpa mengubah Sheets.')
        return
    step(6, 'Isi link folder ke Sheets')
    # Require the same source set after user confirmation.
    fresh_folders = drive_folders(drive, did)
    if sorted((f['id'], f['name']) for f in fresh_folders) != sorted((f['id'], f['name']) for f in folders):
        raise ValueError('Folder Drive berubah. Jalankan pratinjau lagi.')
    for job in jobs:
        if job['error']:
            continue
        quoted, live, hi, ci = read_sheet(sheets, sid, tab)
        fresh = next(p for p in make_plan(live, hi, ci, paths) if p['folder'] == job['folder'])
        if fresh['error'] or fresh['row'] != job['row']:
            raise ValueError('Sheets berubah; proses dihentikan agar link tidak salah baris.')
        url = 'https://drive.google.com/drive/folders/' + by_name[job['folder'].name]
        destination = f'{quoted}!{column(ci["link"])}{job["row"]}'
        sheets.spreadsheets().values().update(spreadsheetId=sid, range=destination, valueInputOption='RAW', body={'values': [[url]]}).execute()
        print(f'No. {job["no"]} -> {destination}: {url}')
    print('Selesai. Tidak ada file yang diunggah ulang.')


def wizard(oauth=None):
    print('AUTO UPLOAD — PIC afzal\nLogin -> pilih folder hasil edit -> Sheets/tab -> tujuan Drive -> pratinjau -> upload dan isi link')
    step(1, 'Sambungkan Google')
    clients = None
    if (STATE / 'token.json').exists():
        try:
            clients = services()
            print('Sesi Google tersimpan siap digunakan.')
        except ValueError:
            print('Sesi tersimpan perlu login ulang.')
    if clients is None:
        # Let the user supply a path here instead of closing the wizard when
        # automatic client discovery cannot choose a single JSON file.
        try:
            path = client_file(oauth)
        except ValueError as exc:
            print(str(exc))
            path = client_file(ask('Tempel lokasi lengkap OAuth JSON (boleh seret file ke terminal)'))
        login(str(path))
        clients = services()
    drive, _ = clients
    user = drive.about().get(fields='user(displayName,emailAddress)').execute().get('user', {})
    print('Terhubung sebagai:', user.get('emailAddress') or user.get('displayName') or 'akun Google')
    configure_and_upload(clients)


def main():
    parser = argparse.ArgumentParser(description='Auto Upload — khusus PIC afzal')
    parser.add_argument('command', nargs='?', choices=['wizard', 'login', 'tabs', 'upload', 'sync', 'logout'])
    parser.add_argument('--oauth', help='Lokasi OAuth Desktop JSON untuk login')
    args = parser.parse_args()
    command = args.command or 'wizard'
    if command == 'wizard':
        wizard(args.oauth)
    elif command == 'login':
        login(args.oauth)
    elif command == 'tabs':
        _, sheets = services()
        cfg = load(STATE / 'settings.json', {})
        cfg['sheet'] = ask('Link Google Sheets', cfg.get('sheet', ''))
        for i, title in enumerate(tabs(sheets, extract(cfg['sheet'], 'sheet')), 1):
            print(f'{i}. {title}')
        save(STATE / 'settings.json', cfg)
    elif command == 'upload':
        configure_and_upload()
    elif command == 'sync':
        sync_drive()
    elif command == 'logout':
        (STATE / 'token.json').unlink(missing_ok=True)
        print('Login lokal dihapus. Akses aplikasi juga bisa dicabut melalui pengaturan akun Google.')
    else:
        raise ValueError('Pilihan tidak valid.')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nDihentikan. Folder parsial tetap di Drive. Jalankan lagi untuk melanjutkan.')
        sys.exit(130)
    except Exception as exc:
        # Never echo HTTP bodies, tokens or OAuth callback URLs into logs.
        from googleapiclient.errors import HttpError
        if isinstance(exc, HttpError):
            status = exc.resp.status
            advice = {401:'Login Google lagi.',403:'Pastikan Drive API dan Sheets API aktif, email terdaftar sebagai test user, serta akun punya izin edit.',404:'Periksa link dan akses folder/Sheets.',429:'Kuota sementara terlampaui; coba nanti.'}.get(status,'Periksa koneksi dan coba lagi.')
            print(f'Gagal: Google API HTTP {status}. {advice}')
        elif isinstance(exc, (ValueError, FileNotFoundError)):
            print('Gagal:', str(exc))
        else:
            print('Gagal:', type(exc).__name__, '— periksa koneksi, izin file, dan jalankan login lagi bila diperlukan.')
        sys.exit(1)
