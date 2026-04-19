# Resolume Scheduler v1.7.0

![Logo](logo.ico)

**Resolume Scheduler** adalah aplikasi automasi presisi untuk Resolume Arena/Wire. Aplikasi ini dirancang untuk desainer visual yang membutuhkan jadwal tayang klip yang kaku, sistem cadangan (redundancy) yang sinkron, dan kontrol jarak jauh yang mudah.

## 🚀 Fitur Utama

- **Precision Scheduling**: Jadwalkan trigger klip (Layer & Column) pada waktu yang spesifik.
- **Redundancy (Multi-Server Sync)**: Kirim perintah trigger ke banyak PC Resolume secara bersamaan (Broadcast Mode). Menjamin PC *Main* dan *Backup* selalu sinkron.
- **Auto Metadata Sync**: Aplikasi secara otomatis membaca durasi klip dari Resolume API untuk menjadwalkan klip berikutnya tanpa input manual.
- **Mobile-Friendly Dashboard**: Akses dan kontrol jadwal dari smartphone atau tablet melalui jaringan Wi-Fi yang sama.
- **Auto-Reconnect & Heartbeat**: Memonitor kesehatan koneksi ke semua server Resolume secara real-time.
- **Persistent Settings**: Jadwal permanen dan tema pilihan Anda tersimpan dengan aman di `schedule.json` dan `settings.json`.
- **Auto-Start**: Pilihan untuk menjalankan aplikasi otomatis saat Windows dinyalakan.

## 🛠️ Instalasi

### Menggunakan Versi Compile (.exe)
1. Unduh rilisan terbaru dari [Halaman Releases](https://github.com/CyrusCore/ResolumeScheduler/releases).
2. Ekstrak file `.zip`.
3. Jalankan `ResolumeScheduler.exe`.

### Menjalankan dari Source (Python)
Jika Anda ingin memodifikasi atau menjalankan langsung dari script:
1. Pastikan Python 3.12+ terinstal.
2. Clone repository ini.
3. Instal dependensi:
   ```bash
   pip install -r requirements.txt
   ```
4. Jalankan aplikasi:
   ```bash
   python app.py
   ```

## ⚙️ Cara Penggunaan

1. **Aktifkan Webserver Resolume**: Di Resolume, masuk ke `Preferences > Web Server` dan aktifkan.
2. **Konfigurasi API**: Di Resolume Scheduler, klik ikon **Settings** dan tambahkan alamat IP serta Port Resolume Anda.
3. **Tambah Jadwal**: Klik **+ New Schedule**, tentukan waktu, Layer, dan Column, lalu klik **Add**.
4. **Auto Sync**: Untuk menyambung klip otomatis, centang "Chain Next Clip" dan masukkan durasi `0` agar aplikasi mendeteksi panjang video secara otomatis.

## 📱 Akses Mobile
Buka menu **Settings** > **About App** untuk melihat URL Dashboard Web unik Anda (contoh: `http://192.168.1.5:5000`). Buka alamat tersebut di browser HP Anda.

## 📄 Lisensi
Copyright © 2026. Designed & Automized by **Bramszs.Visual**.
