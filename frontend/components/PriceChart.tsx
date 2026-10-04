"use client";

import { useMemo } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fmtDate,
  fmtPrice,
  logTicks,
  median,
  snapEvent,
  type EventRow,
  type Point,
  type RangeKey,
} from "@/lib/analytics";

export type Scale = "linear" | "log";

// Biru vs oranye tetap mudah dibedakan untuk buta warna; gabungan memakai warna teks.
export const SERIES = [
  { key: "sell", label: "Penjual (ask)", color: "#f97316", dashed: false },
  { key: "buy", label: "Pembeli (bid)", color: "#3b82f6", dashed: false },
  { key: "combined", label: "Gabungan", color: "currentColor", dashed: true },
] as const;

export const OVERLAYS = {
  ma: { label: "MA30", color: "#8b5cf6" },
  author: { label: "1 suara/penulis", color: "#10b981" },
  events: { label: "Event", color: "#f59e0b" },
  model: { label: "Prediksi model", color: "#ec4899" },
  signals: { label: "Sinyal", color: "#16a34a" },
} as const;

const MARGIN = { top: 8, right: 8, bottom: 0, left: 0 };
const Y_WIDTH = 56; // sama di semua panel agar sumbu-X sejajar

const BUY_COLOR = "#16a34a";
const SELL_COLOR = "#dc2626";

type Props = {
  data: Point[]; // sudah dipotong sesuai rentang
  events: EventRow[];
  scale: Scale;
  lines: string[];
  overlays: string[];
  range: RangeKey;
};

function MainTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p: Point = payload[0].payload;
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-sm shadow-sm">
      <div className="font-medium">{fmtDate(p.date, true)}</div>
      <div className="mt-1 grid grid-cols-[auto_auto_auto] gap-x-4 text-muted-foreground">
        {SERIES.map((s) => (
          <div key={s.key} className="contents">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
            <span className="text-right text-foreground">{fmtPrice(p[s.key])}</span>
            <span className="text-right">
              {s.key === "sell" ? p.sellVol : s.key === "buy" ? p.buyVol : p.volume} post
            </span>
          </div>
        ))}
        {p.authorMedian != null && (
          <div className="contents">
            <span>1 suara/penulis</span>
            <span className="text-right text-foreground">{fmtPrice(p.authorMedian)}</span>
            <span className="text-right">{p.authors} penulis</span>
          </div>
        )}
        {p.ma30 != null && (
          <div className="contents">
            <span>MA30</span>
            <span className="text-right text-foreground">{fmtPrice(p.ma30)}</span>
            <span />
          </div>
        )}
        {p.predicted != null && (
          <div className="contents">
            <span>Prediksi model</span>
            <span className="text-right text-foreground">{fmtPrice(p.predicted)}</span>
            <span className="text-right">{p.residZ != null ? `z ${p.residZ.toFixed(1)}` : ""}</span>
          </div>
        )}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">
        Rentang {fmtPrice(p.min)} – {fmtPrice(p.max)}
        {p.spreadPct != null && ` · spread ${p.spreadPct.toFixed(1)}%`}
      </div>
      {p.lowConf && <div className="mt-1 text-xs text-amber-600">Data tipis: volume rendah, harga kurang andal.</div>}
      {p.signal && (
        <div className="mt-1 text-xs font-medium">
          Sinyal {p.signal}
          {p.reason ? `: ${p.reason}` : ""}
        </div>
      )}
    </div>
  );
}

function VolumeTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p: Point = payload[0].payload;
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-sm shadow-sm">
      <div className="font-medium">{fmtDate(p.date, true)}</div>
      <div className="mt-1 text-muted-foreground">
        Penjual {p.sellVol} · Pembeli {p.buyVol} · Total {p.volume}
        {p.authors > 0 && ` · ${p.authors} penulis`}
      </div>
      {p.lowConf && <div className="mt-1 text-xs text-amber-600">Data tipis</div>}
    </div>
  );
}

function PanelTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-1 mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">{children}</h3>;
}

export default function PriceCharts({ data, events, scale, lines, overlays, range }: Props) {
  const chartData = useMemo(
    () =>
      data.map((p) => ({
        ...p,
        buyMark: p.signal === "BUY" ? p.combined : null,
        sellMark: p.signal === "SELL" ? p.combined : null,
      })),
    [data]
  );

  const has = (o: string) => overlays.includes(o);

  // Domain sumbu-Y dihitung dari garis yang sedang tampil saja.
  const { domain, ticks } = useMemo(() => {
    const keys: string[] = [...lines];
    if (has("ma")) keys.push("ma30");
    if (has("author")) keys.push("authorMedian");
    if (has("model")) keys.push("predicted");
    const vals: number[] = [];
    for (const d of chartData as any[])
      for (const k of keys) if (typeof d[k] === "number" && d[k] > 0) vals.push(d[k]);
    if (!vals.length || scale === "linear") return { domain: ["auto", "auto"] as [string, string], ticks: undefined };
    const lo = Math.min(...vals) * 0.93;
    const hi = Math.max(...vals) * 1.07;
    const t = logTicks(lo, hi);
    return { domain: [lo, hi] as [number, number], ticks: t.length >= 3 ? t : undefined };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartData, lines, overlays, scale]);

  const snapped = useMemo(
    () =>
      has("events")
        ? events
            .map((ev) => ({ ev, s: snapEvent(ev, data) }))
            .filter((x): x is { ev: EventRow; s: NonNullable<ReturnType<typeof snapEvent>> } => x.s !== null)
        : [],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [events, data, overlays]
  );

  const spreadMedian = useMemo(() => {
    const v = data.map((d) => d.spreadPct).filter((x): x is number => x != null);
    return v.length >= 5 ? median(v) : null;
  }, [data]);

  const long = range === "1Y" || range === "ALL";
  const xFormat = (d: string) => fmtDate(d, long);
  const yFormat = (v: number) => String(+Number(v).toPrecision(3));

  return (
    <div className="text-foreground">
      <PanelTitle>Harga (BGL){scale === "log" ? " · skala log" : ""}</PanelTitle>
      <div className="h-[340px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} syncId="price" margin={MARGIN}>
            <CartesianGrid stroke="currentColor" strokeOpacity={0.1} vertical={false} />
            <XAxis dataKey="date" tickFormatter={xFormat} tick={{ fontSize: 12 }} tickLine={false} minTickGap={40} />
            <YAxis
              scale={scale}
              domain={domain}
              ticks={ticks}
              allowDataOverflow
              tickFormatter={yFormat}
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={Y_WIDTH}
            />
            <Tooltip content={<MainTooltip />} />

            {snapped.map(({ ev, s }) =>
              s.line ? (
                <ReferenceLine
                  key={ev.id}
                  x={s.x1}
                  stroke={ev.kind === "structural" ? "#dc2626" : OVERLAYS.events.color}
                  strokeDasharray="4 3"
                  label={{ value: ev.name, position: "insideTopRight", fontSize: 10, fill: "currentColor" }}
                />
              ) : (
                <ReferenceArea
                  key={ev.id}
                  x1={s.x1}
                  x2={s.x2}
                  fill={OVERLAYS.events.color}
                  fillOpacity={0.14}
                  stroke="none"
                  label={{ value: ev.name, position: "insideTop", fontSize: 10, fill: "currentColor" }}
                />
              )
            )}

            {SERIES.filter((s) => lines.includes(s.key)).map((s) => (
              <Line
                key={s.key}
                name={s.label}
                dataKey={s.key}
                stroke={s.color}
                strokeWidth={s.dashed ? 1.5 : 2}
                strokeDasharray={s.dashed ? "5 4" : undefined}
                connectNulls
                dot={data.length <= 31}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            ))}
            {has("ma") && (
              <Line dataKey="ma30" name="MA30" stroke={OVERLAYS.ma.color} strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
            )}
            {has("author") && (
              <Line dataKey="authorMedian" name="1 suara/penulis" stroke={OVERLAYS.author.color} strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
            )}
            {has("model") && (
              <Line dataKey="predicted" name="Prediksi model" stroke={OVERLAYS.model.color} strokeWidth={1.5} strokeDasharray="2 3" dot={false} connectNulls isAnimationActive={false} />
            )}
            {has("signals") && (
              <>
                <Line dataKey="buyMark" stroke="none" dot={{ r: 5, fill: BUY_COLOR, stroke: "white", strokeWidth: 1 }} activeDot={false} isAnimationActive={false} legendType="none" />
                <Line dataKey="sellMark" stroke="none" dot={{ r: 5, fill: SELL_COLOR, stroke: "white", strokeWidth: 1 }} activeDot={false} isAnimationActive={false} legendType="none" />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <PanelTitle>Spread penjual–pembeli (% dari harga)</PanelTitle>
      <div className="h-[120px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} syncId="price" margin={MARGIN}>
            <CartesianGrid stroke="currentColor" strokeOpacity={0.1} vertical={false} />
            <XAxis dataKey="date" hide />
            <YAxis
              tickFormatter={(v) => `${Math.round(v)}%`}
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={Y_WIDTH}
            />
            <Tooltip
              formatter={(v: any) => [`${Number(v).toFixed(1)}%`, "Spread"]}
              labelFormatter={(d: any) => fmtDate(String(d), true)}
            />
            {spreadMedian != null && (
              <ReferenceLine y={spreadMedian} stroke="currentColor" strokeOpacity={0.4} strokeDasharray="4 3" />
            )}
            <Area dataKey="spreadPct" stroke="#64748b" strokeWidth={1.5} fill="#64748b" fillOpacity={0.15} connectNulls dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <PanelTitle>Jumlah postingan (biru pembeli, oranye penjual; pudar = data tipis)</PanelTitle>
      <div className="h-[120px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} syncId="price" margin={MARGIN} barCategoryGap={1}>
            <CartesianGrid stroke="currentColor" strokeOpacity={0.1} vertical={false} />
            <XAxis dataKey="date" tickFormatter={xFormat} tick={{ fontSize: 12 }} tickLine={false} minTickGap={40} />
            <YAxis tick={{ fontSize: 12 }} tickLine={false} axisLine={false} width={Y_WIDTH} />
            <Tooltip content={<VolumeTooltip />} />
            <Bar dataKey="buyVol" stackId="v" fill="#3b82f6" isAnimationActive={false}>
              {chartData.map((d) => (
                <Cell key={d.date} fillOpacity={d.lowConf ? 0.3 : 1} />
              ))}
            </Bar>
            <Bar dataKey="sellVol" stackId="v" fill="#f97316" isAnimationActive={false}>
              {chartData.map((d) => (
                <Cell key={d.date} fillOpacity={d.lowConf ? 0.3 : 1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}