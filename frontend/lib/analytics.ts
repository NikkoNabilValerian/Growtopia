// Fungsi murni untuk analisis harga. Tidak bergantung pada React atau Supabase,
// sehingga mudah diuji dan dipakai ulang (mis. dari skrip lain).

export const DAY = 86_400_000;

export type Signal = "BUY" | "SELL" | "HOLD" | "NO_TRADE";

export type Point = {
  date: string; // YYYY-MM-DD
  t: number; // epoch ms (UTC) untuk hitungan tanggal
  combined: number; // median gabungan buy + sell
  buy: number | null; // median pembeli (bid)
  sell: number | null; // median penjual (ask)
  authorMedian: number | null; // 1 suara per penulis
  avg: number;
  min: number;
  max: number;
  volume: number; // jumlah postingan
  buyVol: number;
  sellVol: number;
  authors: number; // penulis unik (0 = belum dihitung)
  // turunan
  spreadPct: number | null; // (sell - buy) / combined * 100
  ma30: number | null; // rata-rata bergerak 30 hari dari median gabungan
  lowConf: boolean; // volume di bawah persentil ke-10 selama 30 hari terakhir
  // keluaran model (opsional, dari tabel item_signals)
  predicted?: number | null;
  signal?: Signal | null;
  reason?: string | null;
  residZ?: number | null;
};

export type EventRow = {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  kind: string;
  notes: string | null;
};

export type SignalRow = {
  date: string;
  predicted: number | null;
  resid_z: number | null;
  signal: Signal;
  reason: string | null;
};

export type RangeKey = "7D" | "30D" | "90D" | "1Y" | "ALL";
export const RANGE_DAYS: Record<RangeKey, number | null> = {
  "7D": 7,
  "30D": 30,
  "90D": 90,
  "1Y": 365,
  ALL: null,
};

export const parseDay = (iso: string) => Date.parse(iso + "T00:00:00Z");

// ------------------------------------------------------------- statistik dasar

export function quantile(values: number[], q: number): number {
  const s = [...values].sort((a, b) => a - b);
  const pos = (s.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

export const median = (values: number[]) => quantile(values, 0.5);

// ---------------------------------------------------------------- konstruksi

const num = (v: unknown) => (v == null ? null : Number(v));

/** Ubah baris tabel daily_item_prices menjadi Point (urut tanggal) + hitung turunan. */
export function toPoints(rows: any[]): Point[] {
  const pts: Point[] = rows
    .map((r) => ({
      date: r.date as string,
      t: parseDay(r.date),
      combined: Number(r.median_price),
      buy: num(r.buy_median),
      sell: num(r.sell_median),
      authorMedian: num(r.author_median),
      avg: Number(r.avg_price),
      min: Number(r.min_price),
      max: Number(r.max_price),
      volume: Number(r.total_volume ?? 0),
      buyVol: Number(r.buy_volume ?? 0),
      sellVol: Number(r.sell_volume ?? 0),
      authors: Number(r.total_authors ?? 0),
      spreadPct: null,
      ma30: null,
      lowConf: false,
    }))
    .sort((a, b) => a.t - b.t);
  return enrich(pts);
}

/** Hitung spread, MA30 dan penanda data tipis. Jendela berbasis TANGGAL (bukan jumlah baris),
 *  karena hari tanpa data tidak punya baris. */
export function enrich(pts: Point[]): Point[] {
  let lo = 0;
  let sum = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    sum += p.combined;
    while (pts[lo].t <= p.t - 30 * DAY) {
      sum -= pts[lo].combined;
      lo++;
    }
    const n = i - lo + 1;
    p.ma30 = n >= 5 ? sum / n : null;
    p.spreadPct =
      p.buy != null && p.sell != null ? ((p.sell - p.buy) / p.combined) * 100 : null;

    const prior: number[] = [];
    for (let j = lo; j < i; j++) prior.push(pts[j].volume);
    p.lowConf = prior.length >= 10 && p.volume < quantile(prior, 0.1);
  }
  return pts;
}

export function mergeSignals(pts: Point[], signals: SignalRow[]): Point[] {
  const byDate = new Map(signals.map((s) => [s.date, s]));
  return pts.map((p) => {
    const s = byDate.get(p.date);
    return s
      ? { ...p, predicted: num(s.predicted), signal: s.signal, reason: s.reason, residZ: num(s.resid_z) }
      : p;
  });
}

export function sliceRange(pts: Point[], range: RangeKey): Point[] {
  const days = RANGE_DAYS[range];
  if (!days || !pts.length) return pts;
  const from = pts[pts.length - 1].t - days * DAY;
  return pts.filter((p) => p.t >= from);
}

// ------------------------------------------------------------- indikator

/** Perubahan % median gabungan dibanding `days` hari lalu. null bila tidak ada titik yang cukup dekat. */
export function changeOver(pts: Point[], days: number): number | null {
  if (pts.length < 2) return null;
  const last = pts[pts.length - 1];
  const target = last.t - days * DAY;
  let base: Point | null = null;
  for (let i = pts.length - 2; i >= 0; i--) {
    if (pts[i].t <= target) {
      base = pts[i];
      break;
    }
  }
  if (!base) return null;
  if (target - base.t > Math.max(5, days * 0.25) * DAY) return null;
  return (last.combined / base.combined - 1) * 100;
}

/** Persentil harga terbaru di antara harga `days` hari terakhir (0 = termurah, 100 = termahal). */
export function percentileRank(pts: Point[], days: number): number | null {
  if (!pts.length) return null;
  const last = pts[pts.length - 1];
  const win = pts.filter((p) => p.t >= last.t - days * DAY);
  if (win.length < 20) return null;
  return (win.filter((p) => p.combined <= last.combined).length / win.length) * 100;
}

export function drawdown(pts: Point[]) {
  if (!pts.length) return null;
  let peak = pts[0];
  for (const p of pts) if (p.combined > peak.combined) peak = p;
  const last = pts[pts.length - 1];
  return {
    peak: peak.combined,
    peakDate: peak.date,
    pct: (last.combined / peak.combined - 1) * 100,
    daysSince: Math.round((last.t - peak.t) / DAY),
  };
}

/** Simpangan baku log-return harian (dalam %) selama `days` hari. Hanya pasangan hari berurutan. */
export function volatility(pts: Point[], days: number): number | null {
  if (pts.length < 2) return null;
  const from = pts[pts.length - 1].t - days * DAY;
  const rets: number[] = [];
  for (let i = 1; i < pts.length; i++) {
    if (pts[i].t < from || pts[i].t - pts[i - 1].t !== DAY) continue;
    rets.push(Math.log(pts[i].combined / pts[i - 1].combined));
  }
  if (rets.length < 10) return null;
  const m = rets.reduce((a, b) => a + b, 0) / rets.length;
  const v = rets.reduce((a, b) => a + (b - m) ** 2, 0) / (rets.length - 1);
  return Math.sqrt(v) * 100;
}

/** Volume hari terakhir dibanding median 30 hari sebelumnya (1.0 = normal). */
export function volumeVsMedian(pts: Point[]): number | null {
  if (pts.length < 11) return null;
  const last = pts[pts.length - 1];
  const prior = pts.filter((p) => p.t < last.t && p.t >= last.t - 30 * DAY).map((p) => p.volume);
  if (prior.length < 10) return null;
  const m = median(prior);
  return m > 0 ? last.volume / m : null;
}

// ------------------------------------------------------------- tampilan

/** Harga disimpan dalam BGL. Di bawah 1 BGL tampilkan dalam DL / WL agar terbaca. */
export function fmtPrice(bgl: number | null | undefined): string {
  if (bgl == null || Number.isNaN(bgl)) return "–";
  if (bgl >= 100) return `${Math.round(bgl)} BGL`;
  if (bgl >= 1) return `${+bgl.toFixed(2)} BGL`;
  const wl = bgl * 10_000;
  return wl >= 100 ? `${+(wl / 100).toFixed(1)} DL` : `${Math.round(wl)} WL`;
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "–";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export function fmtDate(iso: string, long = false): string {
  return new Date(iso + "T00:00:00Z").toLocaleDateString("id-ID", {
    day: "numeric",
    month: "short",
    ...(long ? { year: "numeric" } : {}),
    timeZone: "UTC",
  });
}

/** Tick sumbu-Y skala log: 1, 2, 5 × 10^k di dalam [min, max]. */
export function logTicks(min: number, max: number): number[] {
  if (!(min > 0) || !(max > min)) return [];
  const out: number[] = [];
  for (let e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e++) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** e;
      if (v >= min && v <= max) out.push(+v.toPrecision(12));
    }
  }
  return out;
}

/** Cocokkan event ke tanggal yang benar-benar ada di data (ReferenceArea butuh nilai kategori yang ada). */
export function snapEvent(ev: EventRow, pts: Point[]): { x1: string; x2: string; line: boolean } | null {
  if (!pts.length) return null;
  const s = parseDay(ev.start_date);
  const e = parseDay(ev.end_date);
  if (e < pts[0].t || s > pts[pts.length - 1].t) return null;
  if (s === e) {
    // kejadian satu hari -> garis vertikal di titik data terdekat (maks. 3 hari)
    let best: Point | null = null;
    for (const p of pts) if (!best || Math.abs(p.t - s) < Math.abs(best.t - s)) best = p;
    return best && Math.abs(best.t - s) <= 3 * DAY ? { x1: best.date, x2: best.date, line: true } : null;
  }
  const inside = pts.filter((p) => p.t >= s && p.t <= e);
  if (!inside.length) return null;
  return { x1: inside[0].date, x2: inside[inside.length - 1].date, line: false };
}