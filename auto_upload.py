"""Auto Upload: terminal Google login, Sheets matching, Drive upload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from matching import number, detect, column, extract

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
        raise ValueError('Ada beberapa OAuth JSON. Pilih satu dengan: Auto Upload.bat login --oauth "lokasi.json"')
    raise ValueError('OAuth Desktop JSON belum ditemukan. Salin file client_secret…json yang diunduh dari Google ke folder aplikasi, atau gunakan login --oauth "lokasi.json". Jangan ganti jenis client menjadi Web.')


def login(explicit=None):
    from google_auth_oauthlib.flow import InstalledAppFlow
    path = client_file(explicit)
    print('OAuth Desktop JSON ditemukan. Browser login Google akan dibuka.')
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    creds = flow.run_local_server(port=0, timeout_seconds=180, access_type='offline', prompt='consent', success_message='Login Auto Upload berhasil. Kembali ke terminal.')
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
        raise ValueError('Belum login. Jalankan Login Google.bat terlebih dahulu.')
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise ValueError('Sesi habis. Jalankan Login Google.bat lagi.')
        try:
            creds.refresh(Request())
        except Exception:
            raise ValueError('Sesi Google tidak dapat diperbarui. Jalankan Login Google.bat lagi.') from None
        save(STATE / 'token.json', json.loads(creds.to_json()))
    return (build('drive', 'v3', credentials=creds, cache_discovery=False),
            build('sheets', 'v4', credentials=creds, cache_discovery=False))


def ask(label, default=''):
    value = input(label + (f' [{default}]' if default else '') + ': ').strip().strip('"')
    return value or default


def tabs(sheets, sid):
    result = sheets.spreadsheets().get(spreadsheetId=sid, fields='sheets.properties.title').execute()
    return [s['properties']['title'] for s in result.get('sheets', [])]


def read_sheet(sheets, sid, tab):
    quoted = "'" + tab.replace("'", "''") + "'"
    rows = sheets.spreadsheets().values().get(spreadsheetId=sid, range=quoted, valueRenderOption='FORMATTED_VALUE').execute().get('values', [])
    header, cols = detect(rows[:50])
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


def upload_job(drive, sheets, sid, did, tab, job, all_folders, account):
    from googleapiclient.http import MediaFileUpload
    folder = job['folder']
    before = manifest(folder)
    # Include account and file manifest to avoid confusing retries with new content.
    identity = [account, did, str(folder.resolve()), before]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    statefile = STATE / 'uploads' / (key + '.json')
    cp = load(statefile)
    def create(name, parent):
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
        request = drive.files().create(body={'name': path.name, 'parents': [parent]}, media_body=MediaFileUpload(str(path), resumable=True, chunksize=8*1024*1024), fields='id', supportsAllDrives=True)
        response = None
        while response is None:
            status, response = request.next_chunk(num_retries=2)
            if status:
                print(f'  {relative}: {status.progress():.0%}', flush=True)
        cp['files'].append(relative)
        save(statefile, cp)
        print('  Selesai:', relative, flush=True)
    if manifest(folder) != before:
        raise ValueError('Isi folder sumber berubah. Link belum ditulis: ' + url)
    quoted, rows, header, cols = read_sheet(sheets, sid, tab)
    fresh = next(p for p in make_plan(rows, header, cols, all_folders) if p['folder'] == folder)
    if fresh['error'] or fresh['row'] != job['row']:
        raise ValueError('Sheets berubah. Folder tersimpan, link belum ditulis: ' + url)
    destination = f'{quoted}!{column(cols["link"])}{job["row"]}'
    sheets.spreadsheets().values().update(spreadsheetId=sid, range=destination, valueInputOption='RAW', body={'values': [[url]]}).execute()
    print('Link berhasil ditulis:', destination)


def configure_and_upload():
    drive, sheets = services()
    cfg = load(STATE / 'settings.json', {})
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
    cfg['drive'] = ask('Link folder Drive tujuan', cfg.get('drive', ''))
    did = extract(cfg['drive'], 'drive')
    cfg['folder'] = ask('Folder INDUK lokal (berisi folder 11, 12, dst.)', cfg.get('folder', ''))
    root = Path(cfg['folder'])
    if not cfg['folder'] or not root.is_dir():
        raise ValueError('Folder induk tidak ditemukan.')
    first = int(ask('Nomor konten mulai', '1'))
    last = int(ask('Nomor konten akhir', '100'))
    if first < 0 or last < first:
        raise ValueError('Rentang nomor tidak valid.')
    folders = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and number(p.name) is not None and first <= number(p.name) <= last]
    if not folders:
        raise ValueError('Tidak ada folder bernomor dalam rentang ini.')
    target = drive.files().get(fileId=did, fields='mimeType,capabilities(canAddChildren)', supportsAllDrives=True).execute()
    if target['mimeType'] != 'application/vnd.google-apps.folder' or not target.get('capabilities', {}).get('canAddChildren'):
        raise ValueError('Akun ini tidak dapat menambah isi folder Drive tujuan.')
    quoted, rows, header, cols = read_sheet(sheets, sid, tab)
    jobs = make_plan(rows, header, cols, folders)
    print(f'\nTab: {quoted} | PIC: afzal | Kolom otomatis: ' + ', '.join(f'{k}={column(v)}' for k,v in cols.items()))
    for job in jobs:
        print(f'{job["folder"].name} -> baris {job["row"] or "-"}: {job["error"] or "SIAP"}')
    save(STATE / 'settings.json', cfg)
    if not any(not j['error'] for j in jobs):
        print('Tidak ada folder yang siap. Tidak ada upload atau perubahan Sheets.')
        return
    if ask('Ketik UPLOAD untuk melanjutkan') != 'UPLOAD':
        print('Dibatalkan tanpa upload.')
        return
    account = drive.about().get(fields='user.permissionId').execute()['user']['permissionId']
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


def main():
    parser = argparse.ArgumentParser(description='Auto Upload — khusus PIC afzal')
    parser.add_argument('command', nargs='?', choices=['login', 'tabs', 'upload', 'logout'])
    parser.add_argument('--oauth', help='Lokasi OAuth Desktop JSON untuk login')
    args = parser.parse_args()
    command = args.command
    if not command:
        print('AUTO UPLOAD\n1. Login Google\n2. Muat tab Sheets\n3. Pratinjau dan upload\n4. Hapus login lokal')
        command = {'1':'login','2':'tabs','3':'upload','4':'logout'}.get(ask('Pilih'))
    if command == 'login':
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
