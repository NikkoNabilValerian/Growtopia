"""style.py - gaya grafik konsisten untuk laporan Growtopia Market Insights.
Taruh file ini satu folder dengan skrip gambar. Semua PNG disimpan ke ./figures/
"""
import os
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

BLUE = "#0091DA"      # biru utama (sama dengan msblue di LaTeX)
BLACK = "#000000"
GRAY = "#8C8C8C"
LIGHT = "#D9D9D9"
PALETTE = [BLUE, BLACK, GRAY, "#5BC0F0", "#004C73", LIGHT]

FIG_W, FIG_H = 6.5, 3.4   # inci; pas dengan lebar teks A4 (16,6 cm)
OUT_DIR = "figures"


def apply_style():
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"],
        "font.size": 9,
        "axes.edgecolor": BLACK,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "axes.grid": False,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "lines.linewidth": 1.8,
        "figure.dpi": 150,
        "savefig.dpi": 300,
    })


def fmt_id(x, dec=0):
    """Format angka gaya Indonesia: 1.250,5 (titik ribuan, koma desimal)."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def id_axis(ax, axis="y", dec=0, suffix=""):
    f = FuncFormatter(lambda v, _: fmt_id(v, dec) + suffix)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def label_hbars(ax, bars, dec=0, prefix="", suffix="", pad=0.01):
    """Label nilai di ujung bar horizontal (gaya Exhibit 4 pada paper acuan)."""
    xmax = ax.get_xlim()[1]
    for b in bars:
        ax.text(b.get_width() + xmax * pad, b.get_y() + b.get_height() / 2,
                prefix + fmt_id(b.get_width(), dec) + suffix,
                va="center", ha="left", fontsize=8.5)


def new_fig(h=FIG_H):
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, h))
    return fig, ax


def save(fig, name):
    """name = nama file TANPA ekstensi, mis. 'gambar_01_indeks_harga'."""
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Tersimpan: {path}  -> unggah ke Overleaf folder figures/")