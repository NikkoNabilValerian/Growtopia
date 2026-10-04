"""Daftar item yang dipantau. SATU-SATUNYA file yang perlu diubah untuk menambah item.

Cara menambah item baru:
  1. Tambahkan satu entri di ITEMS di bawah (copy-paste contoh yang dikomentari).
  2. Push ke GitHub, lalu jalankan workflow Backfill. Hari yang sudah selesai untuk item
     lain dilewati; item baru otomatis dianggap "belum selesai" di semua hari
     (scrape_log mencatat per item).
  3. Selesai. Item muncul di dropdown website setelah punya data.

Tips: tambahkan beberapa item SEKALIGUS. Membaca pesan Discord adalah bagian yang paling
lama, dan satu kali baca melayani semua item, jadi 5 item sekaligus butuh waktu hampir
sama dengan 1 item.

Isi tiap entri:
  label            nama yang tampil di website
  aliases          semua cara orang menyebut item ini di chat (huruf kecil)
  noise            (opsional) regex dengan 1 grup () untuk bagian nama item yang berupa
                   angka dan bukan harga, mis. "Growscan 9000" -> dibaca "growscan"
  bare_dl_min      (opsional) aturan cadangan untuk angka tanpa satuan: >= nilai ini
                   dianggap DL, di bawahnya BGL. Hanya dipakai bila tidak ada patokan harga.
  seed_anchor_bgl  (opsional, sangat disarankan) perkiraan harga item SEKARANG dalam BGL.
                   Dipakai sebagai titik awal hanya selama item belum punya data sama sekali.
                   Tanpa ini, hari paling baru bisa salah menentukan satuan dan kesalahan
                   itu menjalar ke hari-hari sebelumnya.
"""

ITEMS: dict[str, dict] = {
    "growscan": {
        "label": "Growscan 9000",
        "aliases": ["growscan", "gscan", "gs"],
        "noise": [r"(growscan|gscan)\s*9000"],
        "bare_dl_min": 50,
        "seed_anchor_bgl": 6.0,
    },
    # Contoh item berikutnya (hapus tanda # lalu sesuaikan):
    # "magplant": {
    #     "label": "Magplant 5000",
    #     "aliases": ["magplant", "mag"],
    #     "seed_anchor_bgl": 15.0,   # perkiraan harga sekarang
    # },
}