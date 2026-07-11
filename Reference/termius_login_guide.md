# Panduan Login Luma dari Phone (Termius)

Dokumen ini menerangkan cara setup dan login ke Luma (Antigravity CLI) pada VPS Ubuntu menggunakan aplikasi **Termius** di telefon bimbit anda.

---

## 1. Setup Host Baru di Termius

1. Buka aplikasi **Termius** di phone anda.
2. Pergi ke tab **Hosts** dan tekan butang **+** (atau **New Host**).
3. Isi maklumat berikut:
   * **Alias**: `Luma VPS` (atau nama pilihan anda)
   * **Hostname (IP)**: *[Masukkan IP VPS anda]*
   * **Port**: `22` (atau port custom SSH anda)
   * **Username**: *[Masukkan username VPS, cth: root]*
   * **Password**: *[Masukkan password]* ATAU **Key** (jika guna SSH Key)
4. Tekan **Save** / **Done** di bucu kanan atas.

---

## 2. Sambung ke VPS & Guna tmux

Setelah Host disimpan, klik pada host `Luma VPS` untuk mulakan sambungan.

Bila dah masuk ke Ubuntu CLI:

### A. Untuk Sambung Semula ke Luma (Re-attach)
Taip command ini untuk masuk ke session Luma yang sedia ada:
```bash
tmux a -t luma
```
*Jika session belum wujud (atau VPS baru restart), lihat bahagian [Setup Pertama Kali](#setup-pertama-kali-vps) di bawah.*

### B. Cara Detach (Keluar Tanpa Matikan Luma)
Bila guna Termius di phone, keyboard mempunyai butang khas untuk `Ctrl`.
1. Ketik butang **`Ctrl`** pada bar bantuan keyboard Termius (ia akan kekal aktif/berwarna biru).
2. Tekan huruf **`b`** pada keyboard telefon.
3. Tekan huruf **`d`** pada keyboard telefon.
4. Anda akan keluar dari tmux kembali to shell biasa. Sekarang anda boleh tutup aplikasi Termius dengan selamat!

---

## 3. Shortcut Berguna Termius & tmux

| Aksi | Cara Tekan (Termius) |
| :--- | :--- |
| **Detach dari Luma** | `Ctrl` -> `b`, kemudian `d` |
| **Scroll Chat Ke Atas (Copy Mode)** | `Ctrl` -> `b`, kemudian `[` (guna arrow keys untuk scroll, tekan `q` untuk exit) |
| **Clear Screen Luma** | Taip `/clear` dan tekan `Enter` |
| **Exit Luma (Matikan terus)** | Taip `/exit` dan tekan `Enter` |

---

<a id="setup-pertama-kali-vps"></a>
## 4. Setup Pertama Kali (VPS)
Jika session `luma` belum dibuat pada VPS, jalankan arahan ini selepas login:
```bash
# Cipta session tmux baru bernama luma
tmux new -s luma

# Jalankan Luma di dalam tmux tersebut
agy
```
