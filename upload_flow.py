"""Shared, UI-independent upload preparation and execution."""
from pathlib import Path
import auto_upload as core


def add_source(selected, location):
    root = Path(location)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Pilih folder sumber yang valid.')
    candidates = [root] if core.number(root.name) is not None else [p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and core.number(p.name) is not None]
    if not candidates:
        raise ValueError('Folder harus bernomor, atau berisi folder bernomor seperti 11, 13, 15.')
    combined = {str(p.resolve()): p.resolve() for p in selected + candidates}
    return sorted(combined.values())


def prepare(clients, folders, sheet, drive, tab):
    if not folders:
        raise ValueError('Pilih folder hasil edit terlebih dahulu.')
    if not tab:
        raise ValueError('Muat dan pilih tab bulanan terlebih dahulu.')
    for folder in folders:
        if not folder.is_dir():
            raise ValueError('Folder sumber tidak ditemukan: ' + str(folder))
    sid, did = core.extract(sheet.strip(), 'sheet'), core.extract(drive.strip(), 'drive')
    drive_api, sheets = clients
    target = drive_api.files().get(fileId=did, fields='mimeType,capabilities(canAddChildren)', supportsAllDrives=True).execute()
    if target.get('mimeType') != 'application/vnd.google-apps.folder' or not target.get('capabilities', {}).get('canAddChildren'):
        raise ValueError('Akun ini tidak bisa menambah file ke folder Drive tujuan.')
    quoted, rows, header, cols = core.read_sheet(sheets, sid, tab)
    jobs = core.make_plan(rows, header, cols, folders)
    return {'sid': sid, 'did': did, 'tab': tab, 'quoted': quoted, 'cols': cols, 'folders': folders, 'jobs': jobs}


def execute(clients, prepared):
    drive, sheets = clients
    account = drive.about().get(fields='user.permissionId').execute()['user']['permissionId']
    completed = 0
    for job in prepared['jobs']:
        if job['error']:
            continue
        _, rows, header, cols = core.read_sheet(sheets, prepared['sid'], prepared['tab'])
        fresh = next(p for p in core.make_plan(rows, header, cols, prepared['folders']) if p['folder'] == job['folder'])
        if fresh['error'] or fresh['row'] != job['row'] or cols != prepared['cols']:
            raise ValueError('Sheets berubah. Periksa pencocokan lagi sebelum melanjutkan.')
        core.upload_job(drive, sheets, prepared['sid'], prepared['did'], prepared['tab'], job, prepared['folders'], account)
        completed += 1
    return completed
