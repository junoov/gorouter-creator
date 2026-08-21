# GoRouter Creator

Tool CLI untuk membuat akun [GoRouter](https://gorouter.app) lewat GitHub OAuth, lalu generate API key dan impor otomatis ke [9Router](https://github.com/9router/9router).

## Alur Kerja

```
1. Buat temp email       (mail.noov.app)
2. Signup GitHub         (Camoufox + OTP dari inbox noov)
3. Login GoRouter        (GitHub OAuth + Cloudflare Turnstile)
4. Generate API key      (ambil key lewat intercept clipboard)
5. Impor ke 9Router      (opsional)
```

## Kebutuhan

- Python 3.10+
- [Camoufox](https://camoufox.com) — browser anti-deteksi berbasis Firefox
- Akun [mail.noov.app](https://mail.noov.app) untuk temp email
- 9Router (opsional, untuk impor key otomatis)

## Instalasi

```bash
pip install -r requirements.txt
camoufox fetch          # unduh browser, sekali saja (~200MB)
```

Semua konfigurasi sudah terisi di `.env`, jadi bisa langsung jalan.

## Pemakaian

```bash
python3 main.py
```

Muncul menu setting:

```
====================================================
  GoRouter Creator — Setting
====================================================
 1) Jumlah akun        : 1
 2) Kode referral      : aP1o
 3) Mode browser       : tampil di layar
 4) Import ke 9Router  : ya
 5) Sumber akun        : buat GitHub baru
 6) Proxy              : tidak pakai
----------------------------------------------------
 [enter] mulai   |   nomor = ubah   |   q = keluar
```

Ketik nomor untuk mengubah, Enter untuk mulai.

### Lewat flag

```bash
python3 main.py -y                          # pakai .env apa adanya, tanpa menu
python3 main.py --count 3 --aff aP1o        # 3 akun, referral tertentu
python3 main.py --use-existing --line 5     # pakai akun GitHub baris ke-5
python3 main.py --headless                  # tanpa jendela browser
python3 main.py --no-router                 # jangan impor ke 9Router
python3 main.py --proxy http://user:pass@host:port
```

## Utilitas

**Cek kesehatan IP** — jalankan sebelum bikin akun, biar tahu IP sudah kena flag DataDome atau belum:

```bash
python3 cek_ip.py                  # IP saat ini
python3 cek_ip.py --pool           # coba semua proxy di proxies.txt
python3 cek_ip.py --proxy URL      # proxy tertentu
```

**Ambil kode verifikasi GitHub** dari inbox noov:

```bash
python3 get_code.py <username|email>
python3 get_code.py <username> --watch     # tunggu kode baru masuk
```

## Konfigurasi

Semua di `.env`:

| Variabel | Keterangan | Default |
|---|---|---|
| `COUNT` | Jumlah akun per run | `1` |
| `INTERACTIVE` | `1` tampilkan menu, `0` langsung jalan | `1` |
| `HEADLESS` | `1` tanpa jendela, `0` browser tampil | `0` |
| `NOOV_COOKIE` | Cookie `mailflare_session` dari mail.noov.app | — |
| `GR_AFF_CODE` | Kode referral GoRouter | `aP1o` |
| `ADD_TO_ROUTER` | `1` impor key ke 9Router | `1` |
| `ROUTER_URL` | Endpoint 9Router | `http://127.0.0.1:20128` |
| `ROUTER_PASS` | Password 9Router (kosongkan bila login dimatikan) | — |
| `USE_PROXY_POOL` | `1` pakai proxy dari `proxies.txt` | `1` |
| `PROXY_COOLDOWN` | Jeda minimal sebelum proxy dipakai lagi (detik) | `600` |
| `DELAY_BETWEEN_ACCOUNTS` | Jeda antar akun (detik) | `90` |
| `DATADOME_RETRIES` | Percobaan saat kena DataDome | `6` |

## Output

| File | Isi |
|---|---|
| `gorouter_keys.txt` | `email\|username\|nama_key\|sk-xxx` |
| `github_keys.txt` | `email:password:username` |
| `logs/run-*.log` | Log lengkap per run |

## Format Proxy

`proxies.txt`, satu proxy per baris. Format yang didukung:

```
host:port:user:pass
host:port
http://user:pass@host:port
socks5://user:pass@host:port
```

SOCKS5 dengan autentikasi otomatis dijembatani lewat `proxy_bridge.py`, karena Firefox tidak mendukungnya secara langsung.

## Troubleshooting

**`Access is temporarily restricted` saat signup GitHub**

GitHub memakai DataDome. Ini soal reputasi IP, bukan jenisnya — proxy residential pun bisa kena kalau blok IP-nya sudah dipakai orang lain untuk hal serupa.

Cek dulu:

```bash
python3 cek_ip.py
```

Kalau `DIBLOKIR`:

1. Tethering dari HP — IP seluler pakai CGNAT, paling sulit diblokir permanen
2. Restart router untuk dapat IP baru
3. Tunggu 2–6 jam (masa cooldown DataDome)
4. Pakai akun GitHub yang sudah ada: `--use-existing`

Langkah OAuth GoRouter **tidak** lewat DataDome, jadi `--use-existing` tetap jalan walau IP sedang kena flag.

**OTP GitHub tidak masuk**

Cek cookie noov masih valid:

```bash
curl -H "cookie: mailflare_session=$NOOV_COOKIE" https://mail.noov.app/api/users
```

Kalau `401`, login ulang ke mail.noov.app dan ambil cookie baru.

**Tombol "Continue with GitHub" tidak bereaksi**

GoRouter memakai Cloudflare Turnstile dan React. Klik via JavaScript diabaikan karena bukan trusted event. Kode sudah menangani ini: tunggu Turnstile selesai, klik pakai mouse asli, lalu verifikasi URL benar-benar berpindah, dengan 4 kali percobaan.

**9Router gagal impor**

- Pastikan 9Router jalan di `ROUTER_URL`
- Matikan **Require Login** di Settings → Security, atau isi `ROUTER_PASS`
- API key tetap tersimpan di `gorouter_keys.txt` meski impor gagal

## Struktur

```
gorouter-creator/
├── main.py               # CLI + orkestrasi 4 langkah
├── gorouter.py           # OAuth GoRouter + generate API key
├── signup_camoufox.py    # signup GitHub (Camoufox)
├── noov_email.py         # temp email + baca inbox
├── router9.py            # klien 9Router
├── proxy_pool.py         # rotasi proxy + cooldown
├── proxy_bridge.py       # jembatan SOCKS5-auth → HTTP lokal
├── logger.py             # log ke stdout + file
├── cek_ip.py             # cek reputasi IP
├── get_code.py           # ambil kode verifikasi GitHub
└── .env                  # semua konfigurasi
```

## Catatan

Dipakai untuk keperluan pribadi dan belajar. Patuhi Terms of Service tiap layanan yang digunakan.
