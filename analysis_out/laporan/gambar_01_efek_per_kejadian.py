import pandas as pd
from style import *

# Data: salin analysis_out/laporan_bgl/occurrences.csv -> data/occurrences_bgl.csv
# Kolom dipakai: item, mulai, efek_-20..14_%  (efek rata-rata di jendela uji, persen)
df = pd.read_csv("data/occurrences_bgl.csv")
kol = [c for c in df.columns if c.startswith("efek_")][0]
df["label"] = df["item"] + " " + pd.to_datetime(df["mulai"]).dt.year.astype(str)
df = df.sort_values(kol, ascending=False)        # yang paling dalam tampil di atas

fig, ax = new_fig(h=3.2)
bars = ax.barh(df["label"], df[kol], color=BLUE, height=0.6)
ax.axvline(0, color=BLACK, linewidth=0.8)
ax.set_xlim(df[kol].min() * 1.28, 0)
ax.set_xlabel("Efek rata-rata di jendela uji (% terhadap harga normal)")
id_axis(ax, "x")
for b in bars:                                   # label di ujung batang (batang negatif)
    v = b.get_width()
    ax.text(v + df[kol].min() * 0.012, b.get_y() + b.get_height() / 2,
            fmt_id(v, 1).replace("-", "\u2212") + "%", va="center", ha="right", fontsize=8.5)
save(fig, "gambar_01_efek_per_kejadian")