# =====================================================================================
#  KONFIGURASI SCRAPER  --  satu-satunya file yang kamu edit untuk menambah / mengubah item.
#  Isinya variabel biasa saja (tanpa kurung kurawal, tanpa fungsi).
#
#  AMAN di-commit ke GitHub: hanya nama item, alias, dan ID channel. ID channel BUKAN
#  kredensial. JANGAN PERNAH menaruh di sini: token Discord, SUPABASE_SERVICE_KEY, atau isi .env.
#
#  Setelah mengubah file ini:
#     python scraper/show_config.py        <- lihat hasilnya & cek salah ketik
#     python scraper/sync_workflow.py      <- perbarui dropdown di GitHub Actions
#  lalu commit + push.
# =====================================================================================


# ---------------------------------------------------------------- 1. CHANNEL DISCORD
# Satu baris per channel. Nama variabel bebas. ID: Discord -> Settings -> Advanced ->
# Developer Mode, lalu klik kanan channel -> Copy Channel ID.
# (Boleh dikosongkan: item tanpa `_channel` memakai DISCORD_CHANNEL_IDS seperti cara lama.)

CH_GROWSCAN = 900836866373333052, 782718904056807494, 900860787298553877      # #buy-sell-rare-items
CH_GHC = 900836866373333052, 806455698014732318, 900847822570651658
# CH_TOOLS      = 111111111111111111      # contoh


# ---------------------------------------------------------------- 2. ITEM
# Setiap item = beberapa variabel berawalan nama itemnya (nama item = awalan, huruf kecil
# dipakai di database). Item dikenali dari adanya  <awalan>_alias.
#
#   <awalan>_nama         nama yang tampil di website
#   <awalan>_alias        semua cara orang menyebutnya di chat, pisahkan dengan koma
#   <awalan>_alias_lemah  (opsional) alias ambigu, mis. "gs". Pesan yang HANYA memuat alias
#                         ini baru dihitung bila harganya bersatuan jelas (bgl/dl/wl/emoji)
#   <awalan>_nama_angka   (opsional) angka yang merupakan bagian nama item, bukan harga
#                         (mis. "9000" pada "Growscan 9000")
#   <awalan>_channel      (opsional) channel yang dibaca untuk item ini. Satu channel, atau
#                         beberapa dipisah koma:  CH_RARE_ITEMS, CH_TOOLS
#   <awalan>_harga        (opsional, sangat disarankan) perkiraan harga SEKARANG dalam BGL.
#                         Titik awal hanya selama item belum punya data sama sekali
#   <awalan>_aktif        (opsional) False = tidak ikut saat tidak ada pilihan. Tetap bisa
#                         dipilih dengan menyebut namanya. Default True
#   <awalan>_batas_dl     (lanjutan, opsional) angka tanpa satuan >= batas ini dianggap DL,
#                         di bawahnya BGL; hanya dipakai bila tidak ada patokan harga. Default 50

# ---- Growscan
growscan_nama        = "Growscan 9000"
growscan_alias       = "growscan, gscan, gs"
growscan_alias_lemah = "gs"
growscan_nama_angka  = "9000"
growscan_channel   = CH_GROWSCAN
growscan_harga       = 6


#---- GHC
ghc_nama      = "Golden Heart Crystal"
ghc_alias     = "ghc, golden heart crystal"
ghc_channel   = CH_GHC

# ---- Contoh item berikutnya (hapus tanda # di depan tiap baris, lalu sesuaikan)
# ghc_nama      = "Golden Heart Crystal"
# ghc_alias     = "ghc, golden heart crystal"
# ghc_channel   = CH_RARE_ITEMS, CH_TOOLS
# ghc_harga     = 30


# ---------------------------------------------------------------- 3. PRESET (opsional)
# Nama pilihan untuk beberapa item sekaligus: PRESET_<nama> = "item1, item2".
# Dipakai sebagai  preset:<nama>  di --items atau di Actions.

# PRESET_harian = "growscan, ghc"