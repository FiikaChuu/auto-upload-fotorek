# Auto Upload

Aplikasi Windows sederhana: pilih folder hasil edit, unggah ke Google Drive, lalu isi kolom Link Drive di Google Sheets berdasarkan No. konten dan PIC **afzal**.

## Menjalankan di Windows

1. Instal **Python 3.12** untuk Windows dari python.org, termasuk Python Launcher.
2. Ekstrak seluruh ZIP repository ke `D:\Upload_auto`. Timpa kode lama dan pertahankan OAuth JSON serta folder `.auto-upload` Anda.
3. Klik dua kali **Auto Upload.vbs**. Jendela persiapan tampil, dependency Google dipasang otomatis saat pertama kali (perlu internet), kemudian UI terbuka. Tidak perlu terminal atau Node.js. `Auto Upload.bat` juga membuka UI yang sama.
4. Simpan OAuth JSON unduhan Google (`client_secret_….json`) di folder aplikasi. File tidak perlu diganti nama. Bila tidak terdeteksi, gunakan tombol **Pilih OAuth JSON…**.

Jika Windows menolak skrip VBS karena kebijakan perangkat, gunakan `pythonw bootstrap.py` dari instalasi Python Anda. Peluncur belum berupa EXE mandiri.

## Urutan di satu jendela

1. **Sambungkan Google**: browser meminta login jika diperlukan. Sesi tersimpan dipakai lagi secara otomatis. **Ganti akun** membuka login baru.
2. **Tambah folder…**: pilih folder bernomor seperti `11`, atau induk yang berisi `11`, `13`, `15`. Tambahkan beberapa kali bila folder tersebar. Tidak perlu rentang nomor.
3. Isi **Link folder Drive tujuan** dan **Link Google Sheets**. Klik **Muat tab**, lalu pilih tab bulan yang sesuai.
4. Klik **Periksa pencocokan**. Tabel menampilkan nomor folder, alamat sel tujuan, dan alasan dilewati bila ada.
5. Klik **Upload & isi Sheets**, lalu konfirmasi. Panel aktivitas menampilkan file yang berhasil diunggah dan link folder. Pengaturan terkunci selama bekerja.

Contoh: folder lokal `11` diunggah ke Drive, baru link folder hasil upload ditulis ke `FEEDS-OKT!G12` bila No. `11` dan PIC `afzal` berada pada baris 12. Nomor folder dicocokkan ke nilai kolom No., bukan nomor baris Sheets. Kolom Reference tidak diubah. Nomor ganda, PIC lain, dan Link Drive yang sudah terisi dilewati. Nama folder Drive mengikuti nama folder sumber. Semua isi dan subfolder file disalin; subfolder kosong dan symlink dilewati. Hak berbagi tidak diubah menjadi publik dan link ditulis sebagai URL biasa.

Header No., PIC, Link Drive dideteksi otomatis di 50 baris pertama. Tab bulan tetap dipilih agar nomor yang berulang antarbulan tidak tertukar. Mengubah input membatalkan pratinjau dan membutuhkan pemeriksaan ulang.

## Kemampuan tambahan

Mode folder yang sudah ada di Drive tetap tersedia untuk pengembangan melalui `python auto_upload.py sync`. Mode utama UI selalu mengunggah folder lokal dahulu.

## OAuth satu kali

Aktifkan **Drive API** dan **Sheets API** di proyek Google Cloud. Buat OAuth client jenis **Desktop app**. Saat aplikasi masih Testing, tambahkan email login ke **Audience → Test users**. Download JSON ke folder aplikasi. JSON adalah identitas aplikasi, bukan izin akun: persetujuan login browser tetap diperlukan. Jika beberapa file JSON tersedia, pilih eksplisit di Command Prompt:

```bat
cd /d D:\Upload_auto
python auto_upload.py login --oauth "C:\Users\Nama\Downloads\client_secret_....json"
```

Token/refresh token disimpan lokal dalam `.auto-upload\token.json` dan diperbarui otomatis. Jangan membagikan file token, OAuth JSON, atau menyinkronkan folder ini ke penyimpanan publik. Perintah `python auto_upload.py logout` menghapus token lokal; pencabutan akses dilakukan di pengaturan akun Google. Refresh token aplikasi External Testing bisa kedaluwarsa setelah 7 hari, sehingga perlu login lagi.

## Pengembangan

Python >=3.10. Buat virtual environment, lalu `python -m pip install -r requirements.txt`.

```sh
python auto_upload.py
# Perintah langsung untuk pengembangan:
python auto_upload.py login
python auto_upload.py tabs
python auto_upload.py upload
python auto_upload.py sync
python -m unittest -v test_auto_upload test_upload_flow
```

## Pemulihan & batasan

Proses berhenti pada kegagalan pertama. URL folder dicetak sebelum upload. Checkpoint di `.auto-upload/uploads` menyimpan file yang sukses, sehingga pengulangan dengan akun, sumber, dan tujuan yang sama bisa melanjutkan setelah aplikasi ditutup. Jangan menghapus folder Drive yang dirujuk checkpoint. File parsial tidak dihapus otomatis.

Link baru ditulis setelah semua file folder berhasil diunggah dan data Sheets diperiksa kembali. Jangan mengedit sumber atau Sheets selama upload. Pemeriksaan Sheets bukan transaksi dan edit bersamaan masih dapat bertabrakan. Respons jaringan yang hilang dapat membuat file/folder duplikat saat retry. Tidak ada jaminan exactly-once atau resume lintas proses untuk potongan file yang belum selesai. Ctrl+C menghentikan proses; file aktif mungkin sudah diterima Google.

403: periksa API aktif, test user, scope dan hak edit. 404: periksa link/akses. 401 atau token habis: login lagi. OAuth access_denied: periksa test user serta persetujuan izin. Pesan error tidak menampilkan token atau isi respons rahasia.

Pengujian otomatis mencakup 22 pemeriksaan logika dengan Google API tiruan. Login/upload Google nyata dan peluncur Windows memerlukan komputer serta persetujuan akun pengguna; belum diklaim sudah berhasil. UI tidak menyimpan token di GitHub. Tidak ada preview localhost; browser hanya dipakai untuk login Google.
