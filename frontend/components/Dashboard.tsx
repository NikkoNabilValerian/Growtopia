"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import PriceCharts, { OVERLAYS, SERIES, type Scale } from "@/components/PriceChart";
import {
  RANGE_DAYS,
  changeOver,
  drawdown,
  fmtDate,
  fmtPct,
  fmtPrice,
  mergeSignals,
  percentileRank,
  sliceRange,
  volatility,
  volumeVsMedian,
  type EventRow,
  type Point,
  type RangeKey,
  type SignalRow,
} from "@/lib/analytics";
import { fetchEvents, fetchItems, fetchPrices, fetchSignals, type ItemInfo } from "@/lib/data";

const RANGES = Object.keys(RANGE_DAYS) as RangeKey[];

const tone = (v: number | null | undefined) =>
  v == null ? "" : v >= 0 ? "text-emerald-600" : "text-red-600";

const SIGNAL_STYLE: Record<string, string> = {
  BUY: "bg-emerald-600 text-white",
  SELL: "bg-red-600 text-white",
  HOLD: "bg-muted text-foreground",
  NO_TRADE: "bg-amber-500 text-white",
};

function Card({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium">{title}</h2>
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </div>
      <div className="mt-3 space-y-1.5 text-sm">{children}</div>
    </div>
  );
}

function Row({ label, value, className = "" }: { label: string; value: ReactNode; className?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className={`tabular-nums ${className}`}>{value}</span>
    </div>
  );
}

function Dot({ color }: { color: string }) {
  return <span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: color }} />;
}

export default function Dashboard() {
  const [items, setItems] = useState<ItemInfo[]>([]);
  const [item, setItem] = useState("");
  const [range, setRange] = useState<RangeKey>("90D");
  const [scale, setScale] = useState<Scale>("linear");
  const [lines, setLines] = useState<string[]>(["sell", "buy", "combined"]);
  const [overlays, setOverlays] = useState<string[]>(["ma", "events"]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [points, setPoints] = useState<Point[]>([]);
  const [hasSignals, setHasSignals] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false); // parameter URL sudah dibaca

  const cache = useRef(new Map<string, { points: Point[]; signals: SignalRow[] }>());
  const wantedItem = useRef<string | null>(null);

  // 1) Baca parameter URL, lalu muat daftar item + event.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const r = q.get("range");
    if (r && r in RANGE_DAYS) setRange(r as RangeKey);
    const sc = q.get("scale");
    if (sc === "log" || sc === "linear") setScale(sc);
    wantedItem.current = q.get("item");

    Promise.all([fetchItems(), fetchEvents()])
      .then(([its, evs]) => {
        setItems(its);
        setEvents(evs);
        const chosen = its.find((i) => i.name === wantedItem.current)?.name ?? its[0]?.name ?? "";
        setItem(chosen);
        if (!chosen) setLoading(false);
        setReady(true);
      })
      .catch((e) => {
        setError(e.message ?? String(e));
        setLoading(false);
      });
  }, []);

  // 2) Simpan pilihan di URL supaya tampilan bisa dibagikan / di-bookmark.
  useEffect(() => {
    if (!ready || !item) return;
    window.history.replaceState(null, "", `?${new URLSearchParams({ item, range, scale })}`);
  }, [ready, item, range, scale]);

  // 3) Muat seluruh riwayat item sekali (ganti rentang tidak perlu fetch ulang).
  useEffect(() => {
    if (!item) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      let entry = cache.current.get(item);
      if (!entry) {
        const [prices, signals] = await Promise.all([fetchPrices(item), fetchSignals(item)]);
        entry = { points: mergeSignals(prices, signals), signals };
        cache.current.set(item, entry);
      }
      if (cancelled) return;
      setPoints(entry.points);
      setHasSignals(entry.signals.length > 0);
    })()
      .catch((e) => !cancelled && setError(e.message ?? "Gagal memuat data"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [item]);

  const view = useMemo(() => sliceRange(points, range), [points, range]);

  // Indikator dihitung dari SELURUH riwayat, bukan dari rentang yang sedang dilihat.
  const k = useMemo(() => {
    if (!points.length) return null;
    return {
      last: points[points.length - 1],
      changes: [7, 30, 90, 365].map((d) => ({ d, v: changeOver(points, d) })),
      pct1y: percentileRank(points, 365),
      dd: drawdown(points),
      vol30: volatility(points, 30),
      volRatio: volumeVsMedian(points),
    };
  }, [points]);

  const latestSignal = useMemo(() => [...points].reverse().find((p) => p.signal) ?? null, [points]);
  const hasAuthor = useMemo(() => points.some((p) => p.authorMedian != null), [points]);
  const hasPredicted = useMemo(() => points.some((p) => p.predicted != null), [points]);

  // Tombol overlay hanya muncul bila datanya ada.
  const overlayOptions = (Object.keys(OVERLAYS) as (keyof typeof OVERLAYS)[]).filter((o) => {
    if (o === "author") return hasAuthor;
    if (o === "events") return events.length > 0;
    if (o === "model") return hasPredicted;
    if (o === "signals") return hasSignals;
    return true;
  });
  const activeOverlays = overlays.filter((o) => overlayOptions.includes(o as keyof typeof OVERLAYS));

  const label = items.find((i) => i.name === item)?.label ?? item;

  return (
    <div className="w-full space-y-5">
      {/* Kontrol utama */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Select value={item} onValueChange={setItem} disabled={!items.length}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder="Pilih item" />
          </SelectTrigger>
          <SelectContent>
            {items.map((i) => (
              <SelectItem key={i.name} value={i.name}>
                {i.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={range}
            onValueChange={(v) => v && setRange(v as RangeKey)}
          >
            {RANGES.map((r) => (
              <ToggleGroupItem key={r} value={r} aria-label={`Rentang ${r}`}>
                {r}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={scale}
            onValueChange={(v) => v && setScale(v as Scale)}
          >
            <ToggleGroupItem value="linear" aria-label="Skala linear">Linear</ToggleGroupItem>
            <ToggleGroupItem value="log" aria-label="Skala logaritmik">Log</ToggleGroupItem>
          </ToggleGroup>
        </div>
      </div>

      {/* Garis dan overlay */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Garis</span>
          <ToggleGroup
            type="multiple"
            variant="outline"
            size="sm"
            value={lines}
            onValueChange={(v) => v.length && setLines(v)}
          >
            {SERIES.map((s) => (
              <ToggleGroupItem key={s.key} value={s.key} aria-label={s.label}>
                <Dot color={s.color} />
                {s.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Overlay</span>
          <ToggleGroup type="multiple" variant="outline" size="sm" value={overlays} onValueChange={setOverlays}>
            {overlayOptions.map((o) => (
              <ToggleGroupItem key={o} value={o} aria-label={OVERLAYS[o].label}>
                <Dot color={OVERLAYS[o].color} />
                {OVERLAYS[o].label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">Data tidak bisa dimuat: {error}</p>}
      {!error && loading && <p className="text-sm text-muted-foreground">Memuat data…</p>}
      {!error && !loading && !points.length && (
        <p className="text-sm text-muted-foreground">Belum ada data untuk item ini.</p>
      )}

      {/* Sinyal model (hanya bila skrip analisis sudah mengisi item_signals) */}
      {!loading && latestSignal && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border p-4">
          <span className={`rounded px-2 py-0.5 text-sm font-semibold ${SIGNAL_STYLE[latestSignal.signal!] ?? ""}`}>
            {latestSignal.signal}
          </span>
          <span className="text-sm">
            Sinyal model {fmtDate(latestSignal.date, true)}
            {latestSignal.residZ != null && ` · resid z ${latestSignal.residZ.toFixed(1)}`}
            {latestSignal.reason && ` · ${latestSignal.reason}`}
          </span>
          {k && latestSignal.date !== k.last.date && (
            <span className="text-xs text-amber-600">bukan sinyal hari terbaru</span>
          )}
        </div>
      )}

      {/* Indikator */}
      {!loading && k && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Card title={label} hint={fmtDate(k.last.date, true)}>
            <Row label="Jual (ask)" value={fmtPrice(k.last.sell)} className="text-orange-500" />
            <Row label="Beli (bid)" value={fmtPrice(k.last.buy)} className="text-blue-500" />
            <Row label="Gabungan" value={fmtPrice(k.last.combined)} className="font-semibold" />
            <Row
              label="Spread"
              value={k.last.spreadPct != null ? `${k.last.spreadPct.toFixed(1)}%` : "–"}
            />
          </Card>

          <Card title="Perubahan" hint="harga gabungan">
            {k.changes.map(({ d, v }) => (
              <Row key={d} label={d === 365 ? "1 tahun" : `${d} hari`} value={fmtPct(v)} className={tone(v)} />
            ))}
          </Card>

          <Card title="Posisi & risiko">
            <Row
              label="Persentil 1 tahun"
              value={
                k.pct1y == null
                  ? "–"
                  : `${Math.round(k.pct1y)}% ${k.pct1y <= 20 ? "(murah)" : k.pct1y >= 80 ? "(mahal)" : ""}`
              }
            />
            <Row
              label="Dari puncak"
              value={k.dd ? `${fmtPct(k.dd.pct)}` : "–"}
              className={tone(k.dd?.pct)}
            />
            {k.dd && (
              <p className="text-xs text-muted-foreground">
                Puncak {fmtPrice(k.dd.peak)} pada {fmtDate(k.dd.peakDate, true)}
                {k.dd.daysSince > 0 && ` (${k.dd.daysSince} hari lalu)`}
              </p>
            )}
            <Row label="Volatilitas 30 hari" value={k.vol30 == null ? "–" : `${k.vol30.toFixed(1)}% / hari`} />
          </Card>

          <Card title="Kualitas data" hint="hari terakhir">
            <Row label="Postingan" value={`${k.last.volume}`} />
            <Row
              label="Dibanding median 30 hari"
              value={k.volRatio == null ? "–" : `${k.volRatio.toFixed(1)}×`}
              className={k.volRatio != null && k.volRatio < 0.5 ? "text-amber-600" : ""}
            />
            {k.last.authors > 0 && <Row label="Penulis unik" value={`${k.last.authors}`} />}
            {k.last.lowConf && <p className="text-xs text-amber-600">Data tipis: harga kurang andal.</p>}
          </Card>
        </div>
      )}

      {/* Grafik */}
      {!loading && view.length > 0 && (
        <PriceCharts data={view} events={events} scale={scale} lines={lines} overlays={activeOverlays} range={range} />
      )}

      <p className="text-xs leading-relaxed text-muted-foreground">
        Harga dalam BGL (1 BGL = 100 DL = 10.000 WL), diambil dari median promosi jual-beli di Discord, bukan harga
        transaksi sungguhan. Gabungan = median buy + sell; spread = (ask − bid) / harga. Data tipis = jumlah postingan di
        bawah persentil ke-10 selama 30 hari terakhir. Informasi ini bukan nasihat keuangan.
      </p>
    </div>
  );
}