import pandas as pd
from style import *

# Data: salin analysis_out/laporan_bgl/profil_harian.csv -> data/profil_harian_bgl.csv
# Kolom dipakai: item, tahun, hari (sejak mulai event), persen (selisih terhadap harga normal)
df = pd.read_csv("data/profil_harian_bgl.csv")
df = df[(df["hari"] >= -30) & (df["hari"] <= 45)]
rata = df.groupby(["tahun", "hari"])["persen"].mean().unstack("tahun")    # rata-rata antar item

fig, ax = new_fig()
ax.axvspan(-20, 14, color=LIGHT, alpha=0.35, linewidth=0)               # jendela uji
for warna, tahun in zip([GRAY, BLACK, BLUE], rata.columns):
    ax.plot(rata.index, rata[tahun], color=warna, label=str(tahun))
ax.axhline(0, color=GRAY, linewidth=0.8, linestyle="--")
ax.axvline(0, color=BLACK, linewidth=0.8)
ax.set_xlabel("Hari sejak mulai event Valentine")
ax.set_ylabel("Selisih terhadap harga normal (%)")
id_axis(ax, "y")
ax.legend(loc="lower left", ncol=3)
save(fig, "gambar_02_jalur_harian_tahun")