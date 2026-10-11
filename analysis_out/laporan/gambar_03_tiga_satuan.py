import pandas as pd
from style import *

# Data: data/ringkasan_efek.csv, diisi dari keluaran event_study.py (baris "Efek rata-rata")
# Kolom: ukuran, efek_persen, kejadian
df = pd.read_csv("data/ringkasan_efek.csv")
df["label"] = df["ukuran"] + " (" + df["kejadian"].astype(str) + ")"
df = df.sort_values("efek_persen", ascending=False)

fig, ax = new_fig(h=2.4)
WARNA = {"Item dalam BGL": BLUE, "Kurs rupiah per DL": GRAY, "Item dalam rupiah": BLACK}
bars = ax.barh(df["label"], df["efek_persen"], color=df["ukuran"].map(WARNA).fillna(BLUE), height=0.55)
ax.axvline(0, color=BLACK, linewidth=0.8)
ax.set_xlim(df["efek_persen"].min() * 1.28, 0)
ax.set_xlabel("Efek rata-rata di jendela uji (% terhadap harga normal)")
id_axis(ax, "x")
for b in bars:
    v = b.get_width()
    ax.text(v + df["efek_persen"].min() * 0.012, b.get_y() + b.get_height() / 2,
            fmt_id(v, 1).replace("-", "\u2212") + "%", va="center", ha="right", fontsize=8.5)
save(fig, "gambar_03_tiga_satuan")