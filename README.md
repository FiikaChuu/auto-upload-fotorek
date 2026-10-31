# Auto Upload

Upload banyak folder ke Drive, lalu isi link di Google Sheets khusus PIC **afzal**, melalui terminal sederhana. Tidak memakai UI web/desktop atau Node.js.

## Windows

1. Instal Python 3.12 untuk Windows dari python.org, termasuk Python Launcher (`py`).
2. Ekstrak seluruh ZIP repository ke `D:\Upload_auto`. Hapus peluncur lama `Jalankan Fotorek.bat` dan `Jalankan Desktop.bat` jika masih tertinggal dari ekstraksi sebelumnya.
3. Taruh OAuth JSON unduhan Google (`client_secret_….json`) di folder aplikasi. **Tidak perlu diganti nama**. Satu OAuth Desktop JSON dalam Downloads juga bisa dideteksi. File OAuth pengguna tidak dimasukkan ke GitHub.
4. Klik **Login Google.bat**. Instalasi dependency pertama membutuhkan internet. Browser membuka login Google. Setelah izin diberikan, token disimpan lokal agar login tidak diulang setiap pemakaian.
5. Klik **Muat Tab.bat** untuk membaca daftar tab Sheets. Langkah ini terpisah dari login dan tidak melakukan upload.
6. Klik **Mulai Upload.bat**. Isi link Sheets, pilih nomor urut TAB bulanan, isi link folder Drive tujuan, pilih path folder INDUK sumber, tanpa mengisi rentang nomor.
7. Periksa pratinjau, lalu ketik `UPLOAD` untuk melanjutkan. Jawaban lain membatalkan tanpa upload.

**Auto Upload.bat** menyediakan menu semua langkah. Tidak ada halaman localhost yang harus dibuka. Login memakai callback loopback sementara sesuai alur Google Desktop.

Contoh: sumber `D:\Bahan` berisi folder `11`, `12 - VLC`, `13`. Nomor folder dicocokkan ke nilai kolom No., bukan nomor baris. Tab dipilih secara eksplisit karena nomor bisa berulang antarbulan. Header No., PIC, Link Drive dideteksi otomatis di 50 baris pertama. PIC selain afzal, nomor ambigu/duplikat dan link yang sudah berisi dilewati. File dan subfolder ikut diunggah; symlink dan subfolder kosong dilewati. Akses berbagi tidak diubah menjadi publik. Link ditulis sebagai URL biasa.

## Folder sudah ada di Drive?

Klik **Isi Sheets dari Drive.bat**. Masukkan link Sheets, pilih tab bulan, lalu beri link folder INDUK di Drive. Semua subfolder bernomor langsung di dalamnya (contoh 11, 13, 15, 17, 19, 21, 24) dicocokkan otomatis ke No. yang sama khusus PIC afzal. Tidak ada rentang nomor. Pratinjau ditampilkan; ketik `ISI` untuk menulis link. Mode ini tidak mengunggah file lagi dan tidak membutuhkan folder sumber lokal. Folder bulan tetap dipilih sendiri untuk menghindari salah periode. Nomor ganda atau link sudah terisi dilewati.

## OAuth satu kali

Aktifkan **Drive API** dan **Sheets API** di proyek Google Cloud. Buat OAuth client jenis **Desktop app**. Saat aplikasi masih Testing, tambahkan email login ke **Audience → Test users**. Download JSON ke folder aplikasi. JSON adalah identitas aplikasi, bukan izin akun: persetujuan login browser tetap diperlukan. Jika beberapa file JSON tersedia, pilih eksplisit di Command Prompt:

```bat
cd /d D:\Upload_auto
"Auto Upload.bat" login --oauth "C:\Users\Nama\Downloads\client_secret_....json"
```

Token/refresh token disimpan lokal dalam `.auto-upload\token.json` dan diperbarui otomatis. Jangan membagikan file token, OAuth JSON, atau menyinkronkan folder ini ke penyimpanan publik. Menu logout menghapus token lokal; pencabutan akses dilakukan di pengaturan akun Google. Refresh token aplikasi External Testing bisa kedaluwarsa setelah 7 hari, sehingga perlu login lagi.

## Pengembangan

Python >=3.10. Buat virtual environment, lalu `python -m pip install -r requirements.txt`.

```sh
python auto_upload.py login
python auto_upload.py tabs
python auto_upload.py upload
python auto_upload.py sync
python -m unittest -v test_auto_upload
```

## Pemulihan & batasan

Proses berhenti pada kegagalan pertama. URL folder dicetak sebelum upload. Checkpoint di `.auto-upload/uploads` menyimpan file yang sukses, sehingga pengulangan dengan akun, sumber, dan tujuan yang sama bisa melanjutkan setelah aplikasi ditutup. Jangan menghapus folder Drive yang dirujuk checkpoint. File parsial tidak dihapus otomatis.

Link baru ditulis setelah semua file folder berhasil diunggah dan data Sheets diperiksa kembali. Jangan mengedit sumber atau Sheets selama upload. Pemeriksaan Sheets bukan transaksi dan edit bersamaan masih dapat bertabrakan. Respons jaringan yang hilang dapat membuat file/folder duplikat saat retry. Tidak ada jaminan exactly-once atau resume lintas proses untuk potongan file yang belum selesai. Ctrl+C menghentikan proses; file aktif mungkin sudah diterima Google.

403: periksa API aktif, test user, scope dan hak edit. 404: periksa link/akses. 401 atau token habis: login lagi. OAuth access_denied: periksa test user serta persetujuan izin. Pesan error tidak menampilkan token atau isi respons rahasia.

Pengujian otomatis menggunakan Google API tiruan. Login/upload Google nyata dan peluncur Windows memerlukan komputer serta persetujuan akun pengguna; belum diklaim sudah berhasil.
