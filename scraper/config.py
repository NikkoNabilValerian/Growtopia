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
CH_GANG = 900836866373333052, 806455698014732318, 900847822570651658
CH_MAGPLANT = 900836866373333052, 782718904056807494, 900860787298553877
CH_ASTEROID = 806494773711339530, 782720570143277116
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

#---- GANG
gang_nama      = "Golden Angel Wings"
gang_alias     = "gang, golden angel wings, ga"
gang_channel   = CH_GANG

#--- Magplant
magplant_nama      = "Magplant 5000"
magplant_alias     = "magplant, mag, magplant 5000"
magplant_nama_angka = "5000"
magplant_channel   = CH_MAGPLANT

#---Asteroid
asteroid_nama = "Asteroid"
asteroid_alias = "asteroid"
asteroid_channel = CH_ASTEROID

#--- HS
hs_nama = "Heavenly Scythe"
hs_alias = "heavenly scythe, hs"
hs_channel = CH_GANG

#--- Locket
locket_nama = "Datemaster's Heart Locket"
locket_alias = "datemaster's heart locket, locket, datemaster heart locket"
locket_channel = CH_GANG

#--- Golden Diaper
golden_diaper_nama = "Golden Diaper"
golden_diaper_alias = "golden diaper, gd, gdiaper, g diaper"
golden_diaper_channel = CH_GANG
golden_diaper_harga = 20

#--- Golden Air Robinsons
golden_air_robinsons_nama = "Golden Air Robinsons"
golden_air_robinsons_alias = "golden air robinsons, gair"
golden_air_robinsons_channel = CH_GANG

#--- Golden Diamond Necklace
golden_diamond_necklace_nama = "Golden Diamond Necklace"
golden_diamond_necklace_alias = "golden diamond necklace, gneck"
golden_diamond_necklace_channel = CH_GANG

#--- Golden Heart Aura
golden_heart_aura_nama = "Golden Heart Aura"
golden_heart_aura_alias = "golden heart aura, gha"
golden_heart_aura_channel = CH_GANG

#--- Golden Heart Glasses
golden_heart_glasses_nama = "Golden Heart Glasses"
golden_heart_glasses_alias = "golden heart glasses, ghg"
golden_heart_glasses_channel = CH_GANG

#--- Golden Heart Shirt
golden_heart_shirt_nama = "Golden Heart Shirt"
golden_heart_shirt_alias = "golden heart shirt, ghs"
golden_heart_shirt_channel = CH_GANG

#--- Golden Heartbow
golden_heartbow_nama = "Golden Heartbow"
golden_heartbow_alias = "golden heartbow, ghb, gbow"
golden_heartbow_channel = CH_GANG

#--- Golden Heartbreak Wings
golden_heartbreak_wings_nama = "Golden Heartbreak Wings"
golden_heartbreak_wings_alias = "golden heartbreak wings, ghw, golde heart break wings, golden heart wings"
golden_heartbreak_wings_channel = CH_GANG

#--- Golden Heartstaff
golden_heartstaff_nama = "Golden Heartstaff"
golden_heartstaff_alias = "golden heartstaff, ghs, ghstaff, gstaff"
golden_heartstaff_channel = CH_GANG

#--- Golden Heartthrob Helm
golden_heartthrob_helm_nama = "Golden Heartthrob Helm"
golden_heartthrob_helm_alias = "golden heartthrob helm, ghth, ghth, ghelm"
golden_heartthrob_helm_channel = CH_GANG

#--- Golden Love Bug
golden_love_bug_nama = "Golden Love Bug"
golden_love_bug_alias = "golden love bug, glb, gbug"
golden_love_bug_channel = CH_GANG

#--- Golden Mobile Suit Wings
golden_mobile_suit_wings_nama = "Golden Mobile Suit Wings"
golden_mobile_suit_wings_alias = "golden mobile suit wings, gmsw, gms wings"
golden_mobile_suit_wings_channel = CH_GANG

#--- Golden Sparkling Wings
golden_sparkling_wings_nama = "Golden Sparkling Wings"
golden_sparkling_wings_alias = "golden sparkling wings, gsw, gsparkling wings"
golden_sparkling_wings_channel = CH_GANG

#--- Golden Silk Scarf
golden_silk_scarf_nama = "Golden Silk Scarf"
golden_silk_scarf_alias = "golden silk scarf, gss, gsilk scarf"
golden_silk_scarf_channel = CH_GANG

#--- Golden Sunset Cape
golden_sunset_cape_nama = "Golden Sunset Cape"
golden_sunset_cape_alias = "golden sunset cape, gsc, gsunset cape, gscape"
golden_sunset_cape_channel = CH_GANG

#--- Golden Talaria
golden_talaria_nama = "Golden Talaria"
golden_talaria_alias = "golden talaria, gt, gtalaria"
golden_talaria_channel = CH_GANG

#--- Stained Glass Heartwings
stained_glass_heartwings_nama = "Stained Glass Heartwings"
stained_glass_heartwings_alias = "stained glass heartwings, sgh, sghw"
stained_glass_heartwings_channel = CH_GANG

#--- Teeny Golden Wings
teeny_golden_wings_nama = "Teeny Golden Wings"
teeny_golden_wings_alias = "teeny golden wings, tgw, tgwings"
teeny_golden_wings_channel = CH_GANG

#--- Rayman Fist
rayman_fist_nama = "Rayman Fist"
rayman_fist_alias = "rayman fist, rf, raymanfist, rayman"
rayman_fist_channel = CH_MAGPLANT

#--- Royal Lock
royal_lock_nama = "Royal Lock"
royal_lock_alias = "royal lock, rl, royallock"
royal_lock_channel = CH_MAGPLANT




# ---- Contoh item berikutnya (hapus tanda # di depan tiap baris, lalu sesuaikan)
# ghc_nama      = "Golden Heart Crystal"
# ghc_alias     = "ghc, golden heart crystal"
# ghc_channel   = CH_RARE_ITEMS, CH_TOOLS
# ghc_harga     = 30


# ---------------------------------------------------------------- 3. PRESET (opsional)
# Nama pilihan untuk beberapa item sekaligus: PRESET_<nama> = "item1, item2".
# Dipakai sebagai  preset:<nama>  di --items atau di Actions.

# PRESET_harian = "growscan, ghc"
