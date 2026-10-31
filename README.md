# Fotorek Auto Upload

Aplikasi browser berbahasa Indonesia untuk mengunggah banyak folder ke Google Drive dan mengisi link folder di Google Sheets berdasarkan **nomor konten + PIC**, dalam tab dan rentang baris yang dipilih.

## Jalankan

### Windows: tinggal klik

Ekstrak atau clone seluruh proyek ke `D:\Upload_auto`. Instal Node.js LTS sekali saja, lalu klik dua kali **Jalankan Fotorek.bat**. Browser terbuka otomatis setelah server siap; tidak perlu mengetik perintah atau alamat localhost. Biarkan jendela peluncur terbuka selama dipakai, lalu tutup untuk menghentikan server. Peluncur ini tetap menggunakan server localhost di belakang layar, bukan aplikasi desktop EXE mandiri. Pengaturan OAuth Google di bawah tetap diperlukan sekali saja. Skrip Windows belum diuji langsung di mesin Windows.

Gunakan Node.js 20 atau lebih baru. Tidak ada dependency npm yang perlu diinstal.

```sh
cd /workspace/auto-upload-fotorek
npm test
npm start
```

Untuk komputer pribadi, jalankan `npm start` dari direktori proyek lalu buka `http://localhost:3000` di Chrome atau Edge. Folder sumber dipilih dari komputer yang menjalankan browser. Pemilihan folder browser tidak menyertakan folder kosong.

## Konfigurasi Google sekali saja

1. Buat/pilih proyek di Google Cloud Console. Aktifkan **Google Drive API** dan **Google Sheets API**.
2. Konfigurasikan Google Auth Platform / OAuth consent screen. Jika aplikasi masih Testing, tambahkan email pengguna sebagai test user.
3. Buat OAuth client jenis **Web application**. Tambahkan `http://localhost:3000` ke **Authorized JavaScript origins**. Untuk hosting HTTPS, gunakan origin HTTPS aplikasi tersebut. Alur ini memakai popup token Google Identity Services, bukan client secret atau redirect server.
4. Masukkan Client ID ke aplikasi dan hubungkan akun yang memiliki akses edit Sheets serta izin menambah file di folder Drive tujuan. Jangan masukkan client secret atau password.

Aplikasi meminta scope `drive` dan `spreadsheets` agar dapat mengakses folder dan spreadsheet yang Anda berikan. Scope ini luas; aplikasi publik mungkin membutuhkan verifikasi Google. Token berada di memori browser, tidak dikirim ke server aplikasi atau disimpan di disk. Login harus dilakukan lagi saat token kedaluwarsa. Google Identity dimuat dari `accounts.google.com`; API menggunakan `www.googleapis.com`, `sheets.googleapis.com`, serta lokasi upload yang dikembalikan Google.

## Alur pemakaian

1. Isi link folder Drive tujuan, link Sheets, dan **nama tab persis**, misalnya `FEEDS-OKT`.
2. Default kolom: No. `A`, PIC `D`, Link Drive `G`; PIC `afzal`. Sesuaikan bila berbeda. Pilih baris awal/akhir untuk membatasi periode. Filter tanggal otomatis belum tersedia karena struktur kolom tanggal belum ditentukan.
3. Klik **Tambah folder bernomor** berulang kali untuk folder `7`, `11 - VLC`, dan seterusnya. Alternatif: pilih folder induk yang berisi folder-folder bernomor melalui **Pilih induk banyak folder**.
4. Klik **Periksa pencocokan**. Nomor dicocokkan dengan nilai kolom No., bukan nomor baris. PIC dicocokkan tanpa membedakan kapital dan spasi luar.
5. Klik **Upload & isi Sheets**. Hanya entri berstatus Siap yang dijalankan. File dan subfolder diunggah berurutan. Setelah semua file selesai, URL folder ditulis sebagai nilai biasa ke satu sel Link Drive.

Nomor folder ganda, baris ambigu, PIC lain, dan sel link yang sudah berisi dilewati. Nomor harus di awal nama folder, diikuti akhir nama, spasi, titik, `_`, atau `-`. Contoh `11 - VLC` valid; `VLC 11` tidak. Folder tetap privat sesuai izin tujuan; aplikasi tidak mengaktifkan akses publik. Link ditulis sebagai URL biasa, bukan smart chip.

## Kegagalan dan batasan

- Data Sheets diperiksa kembali sebelum upload dan sebelum penulisan. Google Sheets tidak menyediakan operasi compare-and-set pada alur ini: hindari mengedit sel tujuan bersamaan selama proses.
- Jika gagal, proses berhenti dan log menampilkan URL folder yang sudah dibuat. Periksa ulang lalu coba lagi **di tab dan sesi login yang sama**; checkpoint memori melewati file yang sukses. Muat ulang, login ulang, atau penutupan tab menghapus checkpoint. Periksa Drive dahulu sebelum mengulang untuk menghindari folder ganda.
- Jika respons upload hilang setelah Google menerima file, percobaan ulang dapat membuat file duplikat. Resume parsial file lintas gangguan jaringan dan penyimpanan job permanen belum tersedia. Folder yang hanya terunggah sebagian tidak dihapus otomatis.
- Jika upload selesai tetapi penulisan Sheets gagal, URL tetap tersedia di log. Perbaiki izin/konfigurasi atau isi link secara manual. Tidak ada rollback Drive otomatis.
- Pemilihan folder dan popup Google memerlukan browser pengguna. Server saja tidak melakukan login atau upload latar belakang terjadwal.

## Validasi

`npm test` menjalankan empat pengujian pencocokan: nomor vs baris, PIC, duplikasi/ambiguitas, proteksi link terisi, serta format nomor/kolom. Uji upload Google nyata memerlukan Client ID, login browser, dan folder/Sheets uji milik pengguna; pengujian unit tidak membuktikan integrasi Google telah berhasil.
