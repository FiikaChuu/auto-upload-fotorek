"""Translate Google failures using structured reasons, without exposing responses."""
import json
import re
from contextlib import contextmanager


@contextmanager
def api_action(description):
    from googleapiclient.errors import HttpError
    try:
        yield
    except HttpError as exc:
        exc.upload_operation=description
        raise


def safe_description(message):
    if not isinstance(message,str) or not message.strip():
        return 'Google tidak menyertakan alasan terperinci.'
    # Do not expose authentication material even if a server unexpectedly echoes it.
    if re.search(r'\b(access_token|refresh_token|id_token|client_secret|authorization|bearer)\b|\b(?:token|code)\s*[:=]|ya29\.|GOCSPX-|eyJ[A-Za-z0-9_-]+\.',message,re.I):
        return 'Detail autentikasi disembunyikan. Sambungkan ulang akun Google.'
    message=re.sub(r'https?://\S+','[tautan disembunyikan]',message)
    return ' '.join(''.join(c for c in message if c.isprintable() or c.isspace()).split())[:1000]


def http_message(exc):
    status = exc.resp.status
    try:
        error = json.loads(exc.content).get('error', {})
        if not isinstance(error, dict):
            error = {}
    except (ValueError, TypeError, UnicodeError):
        error = {}
    reasons = set()
    service = None
    entries=[]
    for key in ('errors','details'):
        values=error.get(key, [])
        if isinstance(values,list):
            entries.extend(values)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        reason = entry.get('reason', '')
        if isinstance(reason, str):
            reasons.add(re.sub('[^a-z]', '', reason.lower()))
        metadata = entry.get('metadata', {})
        if isinstance(metadata, dict) and metadata.get('service') in ('drive.googleapis.com', 'sheets.googleapis.com'):
            service = metadata['service']
    # Older Google API responses identify the disabled API only in the message.
    message = error.get('message', '')
    if not service and isinstance(message, str):
        if re.search(r'Google (?:Sheets|Drive) API', message, re.I):
            service = 'sheets.googleapis.com' if re.search('Google Sheets API', message, re.I) else 'drive.googleapis.com'
    if status == 401:
        return 'Sesi Google tidak berlaku. Klik Ganti akun untuk login ulang.'
    if status == 400:
        detail=safe_description(message)
        if isinstance(message,str) and re.search(r'mime.?type',message,re.I):
            advice='Google menolak informasi jenis file. Catat nama dan ekstensi file yang tercantum pada tahap gagal.'
        elif isinstance(message,str) and re.search(r'range|a1 notation',message,re.I):
            advice='Periksa tab dan huruf kolom tujuan. Ini berkaitan dengan alamat sel Sheets.'
        else:
            advice='Permintaan aplikasi ditolak Google. Pesan ini tidak membuktikan Anda mengubah file atau Sheets.'
        return f'Google menolak permintaan (HTTP 400).\nAlasan Google: {detail}\n\n{advice}'
    if reasons & {'servicedisabled', 'accessnotconfigured'}:
        api = {'drive.googleapis.com':'Google Drive API', 'sheets.googleapis.com':'Google Sheets API'}.get(service, 'API Google yang diperlukan')
        return f'{api} belum aktif pada proyek OAuth aplikasi.\n\nKlik Pengaturan API, aktifkan API tersebut pada proyek yang sama dengan file OAuth JSON, tunggu beberapa menit, lalu coba tombol tadi lagi. Tidak perlu membuat JSON baru.'
    if reasons & {'accesstokenscopeinsufficient', 'insufficientpermissions'}:
        return 'Izin token Google belum lengkap. Klik Ganti akun, login kembali, lalu berikan izin Google Drive DAN Google Sheets. Jika masih ditolak, periksa kebijakan Google Workspace.'
    if reasons & {'storagequotaexceeded'}:
        return 'Penyimpanan Google Drive akun ini penuh. Kosongkan ruang atau gunakan akun/Drive yang masih memiliki kapasitas, lalu coba lagi.'
    if status == 429 or reasons & {'ratelimitexceeded','userratelimitexceeded','dailylimitexceeded','quotaexceeded','resourceexhausted'}:
        return 'Batas pemakaian API Google tercapai. Tunggu dan coba lagi, atau periksa kuota pada proyek Google Cloud.'
    if reasons & {'domainpolicy','orgrestrictionviolation'}:
        return 'Kebijakan organisasi Google Workspace membatasi aplikasi ini. Hubungi admin akun untuk mengizinkan aplikasi dan akses Drive/Sheets.'
    if reasons & {'insufficientfilepermissions','appnotauthorizedtofile'}:
        return 'Akun Google yang tersambung tidak punya izin yang cukup pada file/folder ini. Buka tujuan dengan akun yang sama dan pastikan punya akses edit pada Sheets serta bisa menambah file ke folder Drive.'
    if status == 404:
        return 'Folder atau Sheets tidak ditemukan oleh akun ini. Periksa tautan dan akses akun Google yang tertera di aplikasi.'
    if status == 403:
        return 'Google menolak operasi ini (HTTP 403). Penyebab khusus tidak tersedia dalam respons. Periksa akun yang tertera, akses edit Sheets/folder Drive, serta kebijakan organisasi. Gunakan Pengaturan API untuk memeriksa bahwa kedua API aktif pada proyek OAuth yang benar.'
    return f'Google API gagal (HTTP {status}). Periksa koneksi dan coba lagi nanti.'
