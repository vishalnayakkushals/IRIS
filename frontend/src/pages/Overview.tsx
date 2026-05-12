import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Title, Text, Metric, Card, Grid, Badge,
} from "@tremor/react";
import { CalendarDays, ChevronDown } from "lucide-react";
import {
  fetchAnalytics, fetchTrend, fetchLeaderboard, fetchDelta,
  AnalyticsData, TrendPoint, LeaderboardRow, DeltaData, DashboardDateFilter,
} from "../api/client";
import { useStore } from "../context/StoreContext";

const GENDER_HEX = ["#6366f1", "#ec4899", "#f59e0b", "#94a3b8"];

function TrendLineChart({ data }: { data: Array<{ period: string; "Walk-ins": number; Conversions: number }> }) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  if (data.length === 0) return null;

  const W = 600, H = 180;
  const PAD = { l: 44, r: 12, t: 12, b: 28 };
  const cW = W - PAD.l - PAD.r;
  const cH = H - PAD.t - PAD.b;

  const allVals = data.flatMap((d) => [d["Walk-ins"], d["Conversions"]]);
  const maxVal = Math.max(...allVals, 1);

  const xOf = (i: number) => PAD.l + (data.length > 1 ? (i / (data.length - 1)) * cW : cW / 2);
  const yOf = (v: number) => PAD.t + cH - (v / maxVal) * cH;

  const SERIES = [
    { key: "Walk-ins" as const, color: "#6366f1", fill: "rgba(99,102,241,0.09)" },
    { key: "Conversions" as const, color: "#f97316", fill: "rgba(249,115,22,0.07)" },
  ];

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((p) => ({
    val: Math.round(maxVal * p),
    y: PAD.t + cH * (1 - p),
  }));

  const xStep = Math.max(1, Math.ceil(data.length / 7));

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 224, display: "block" }}>
        {yTicks.map((t) => (
          <g key={t.val}>
            <line x1={PAD.l} x2={W - PAD.r} y1={t.y} y2={t.y} stroke="#f1f5f9" strokeWidth={1} />
            <text x={PAD.l - 6} y={t.y + 4} textAnchor="end" fontSize={9} fill="#94a3b8">{t.val}</text>
          </g>
        ))}
        {SERIES.map((s) => {
          if (data.length < 2) return null;
          const pts = data.map((d, i) => `${xOf(i)},${yOf(d[s.key])}`).join(" L ");
          const area = `M ${xOf(0)},${yOf(data[0][s.key])} L ${pts} L ${xOf(data.length - 1)},${PAD.t + cH} L ${xOf(0)},${PAD.t + cH} Z`;
          const line = data.map((d, i) => `${xOf(i)},${yOf(d[s.key])}`).join(" ");
          return (
            <g key={s.key}>
              <path d={area} fill={s.fill} />
              <polyline points={line} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}
        {data.map((d, i) =>
          SERIES.map((s) => (
            <circle key={s.key} cx={xOf(i)} cy={yOf(d[s.key])} r={hoverIdx === i ? 5 : 3} fill={s.color} />
          ))
        )}
        {data.map((_, i) => (
          <rect
            key={i}
            x={xOf(i) - (cW / Math.max(data.length - 1, 1)) / 2}
            y={PAD.t}
            width={cW / Math.max(data.length - 1, 1)}
            height={cH}
            fill="transparent"
            style={{ cursor: "default" }}
            onMouseEnter={() => setHoverIdx(i)}
            onMouseLeave={() => setHoverIdx(null)}
          />
        ))}
        {hoverIdx !== null && (() => {
          const d = data[hoverIdx];
          const tx = xOf(hoverIdx);
          const bW = 144, bH = 58;
          const bX = Math.min(Math.max(tx - bW / 2, PAD.l), W - PAD.r - bW);
          return (
            <g>
              <line x1={tx} x2={tx} y1={PAD.t} y2={PAD.t + cH} stroke="#cbd5e1" strokeWidth={1} strokeDasharray="3 2" />
              <rect x={bX} y={14} width={bW} height={bH} rx={5} fill="white" stroke="#e2e8f0" strokeWidth={1} />
              <text x={bX + 8} y={30} fontSize={9} fill="#64748b" fontWeight={600}>{d.period}</text>
              <circle cx={bX + 12} cy={41} r={4} fill="#6366f1" />
              <text x={bX + 20} y={45} fontSize={10} fill="#4338ca">Walk-ins: {d["Walk-ins"]}</text>
              <circle cx={bX + 12} cy={56} r={4} fill="#f97316" />
              <text x={bX + 20} y={60} fontSize={10} fill="#ea580c">Conversions: {d["Conversions"]}</text>
            </g>
          );
        })()}
        {data.map((d, i) => {
          if (i % xStep !== 0 && i !== data.length - 1) return null;
          return (
            <text key={i} x={xOf(i)} y={H - 8} textAnchor="middle" fontSize={9} fill="#94a3b8">
              {d.period.length > 7 ? d.period.slice(5) : d.period}
            </text>
          );
        })}
      </svg>
      <div className="flex gap-5 mt-1 ml-11">
        {SERIES.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block w-4 h-0.5 rounded" style={{ backgroundColor: s.color }} />
            <span className="text-xs text-slate-500">{s.key}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

type PickerMode = "today" | "yesterday" | "last" | "custom";

interface DateSelectionState {
  mode: PickerMode;
  lastAmount: number;
  includeToday: boolean;
  from: string;
  to: string;
}

const SIDEBAR_OPTIONS: Array<{ key: PickerMode; label: string }> = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "last", label: "Last" },
  { key: "custom", label: "Custom range" },
];

const GROUP_OPTIONS: { label: string; value: string }[] = [
  { label: "Day", value: "day" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];

function formatInputDate(value: Date) {
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftDate(base: Date, days: number) {
  const next = new Date(base);
  next.setDate(next.getDate() + days);
  return next;
}

function formatDisplayDate(value: string) {
  if (!value) return "";
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, (month || 1) - 1, day || 1, 12, 0, 0, 0);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function formatRangeText(from: string, to: string) {
  if (!from || !to) return "";
  if (from === to) return formatDisplayDate(from);
  return `${formatDisplayDate(from)} - ${formatDisplayDate(to)}`;
}

function getComputedSelection(selection: DateSelectionState) {
  const today = new Date();
  today.setHours(12, 0, 0, 0);

  switch (selection.mode) {
    case "today": {
      const iso = formatInputDate(today);
      return {
        filter: { dateFrom: iso, dateTo: iso } as DashboardDateFilter,
        label: "Today",
        summary: formatDisplayDate(iso),
        cacheKey: `today_${iso}`,
        dayCount: 1,
        invalid: false,
      };
    }
    case "yesterday": {
      const iso = formatInputDate(shiftDate(today, -1));
      return {
        filter: { dateFrom: iso, dateTo: iso } as DashboardDateFilter,
        label: "Yesterday",
        summary: formatDisplayDate(iso),
        cacheKey: `yesterday_${iso}`,
        dayCount: 1,
        invalid: false,
      };
    }
    case "custom": {
      if (!selection.from || !selection.to) {
        return {
          filter: { days: 30 } as DashboardDateFilter,
          label: "Custom range",
          summary: "Select both From and To dates",
          cacheKey: "custom_invalid",
          dayCount: 30,
          invalid: true,
        };
      }
      const start = new Date(`${selection.from}T12:00:00`);
      const end = new Date(`${selection.to}T12:00:00`);
      const dayCount = Math.max(1, Math.round((end.getTime() - start.getTime()) / 86400000) + 1);
      return {
        filter: { dateFrom: selection.from, dateTo: selection.to } as DashboardDateFilter,
        label: "Custom range",
        summary: formatRangeText(selection.from, selection.to),
        cacheKey: `custom_${selection.from}_${selection.to}`,
        dayCount,
        invalid: false,
      };
    }
    case "last":
    default: {
      const amount = Math.max(1, Math.floor(selection.lastAmount || 1));
      const end = selection.includeToday ? today : shiftDate(today, -1);
      const start = shiftDate(end, -(amount - 1));
      const from = formatInputDate(start);
      const to = formatInputDate(end);
      return {
        filter: { dateFrom: from, dateTo: to } as DashboardDateFilter,
        label: `Last ${amount} days`,
        summary: formatRangeText(from, to),
        cacheKey: `last_${amount}_${selection.includeToday ? "incl" : "excl"}_${from}_${to}`,
        dayCount: amount,
        invalid: false,
      };
    }
  }
}

function DeltaBadge({ pct }: { pct: number }) {
  if (pct === 0) return <Badge color="gray">—</Badge>;
  return (
    <Badge color={pct > 0 ? "emerald" : "red"}>
      {pct > 0 ? "▲" : "▼"} {Math.abs(pct)}%
    </Badge>
  );
}

export default function Overview() {
  const { storeId: storeFilter } = useStore();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [committedSelection, setCommittedSelection] = useState<DateSelectionState>({
    mode: "last",
    lastAmount: 30,
    includeToday: true,
    from: "",
    to: "",
  });
  const [draftSelection, setDraftSelection] = useState<DateSelectionState>({
    mode: "last",
    lastAmount: 30,
    includeToday: true,
    from: "",
    to: "",
  });
  const [groupBy, setGroupBy] = useState("day");
  const pickerRef = useRef<HTMLDivElement | null>(null);

  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [delta, setDelta] = useState<DeltaData | null>(null);
  const [loading, setLoading] = useState(false);

  const CACHE_TTL_MS = 5 * 60 * 1000;
  const activeFilter = useMemo(() => getComputedSelection(committedSelection), [committedSelection]);
  const draftPreview = useMemo(() => getComputedSelection(draftSelection), [draftSelection]);
  const draftError = useMemo(() => {
    if (draftSelection.mode !== "custom") return "";
    if ((draftSelection.from && !draftSelection.to) || (!draftSelection.from && draftSelection.to)) return "Select both From and To dates.";
    return "";
  }, [draftSelection]);

  const cacheKey = `overview_${storeFilter || "all"}_${activeFilter.cacheKey}_${groupBy}`;

  const load = useCallback((force = false) => {
    if (!force) {
      try {
        const raw = sessionStorage.getItem(cacheKey);
        if (raw) {
          const { data, ts } = JSON.parse(raw);
          if (Date.now() - ts < CACHE_TTL_MS) {
            setAnalytics(data.analytics);
            setTrend(data.trend);
            setLeaderboard(data.leaderboard);
            setDelta(data.delta);
            return;
          }
          sessionStorage.removeItem(cacheKey);
        }
      } catch {}
    }
    setLoading(true);
    const sid = storeFilter || undefined;
    Promise.all([
      fetchAnalytics(sid, activeFilter.filter),
      fetchTrend(sid, activeFilter.filter, groupBy),
      fetchLeaderboard(activeFilter.filter),
      fetchDelta(sid, activeFilter.filter, activeFilter.dayCount),
    ])
      .then(([a, t, l, d]) => {
        setAnalytics(a.data);
        setTrend(t.data ?? []);
        setLeaderboard(l.data ?? []);
        setDelta(d.data);
        try {
          sessionStorage.setItem(cacheKey, JSON.stringify({
            data: { analytics: a.data, trend: t.data ?? [], leaderboard: l.data ?? [], delta: d.data },
            ts: Date.now(),
          }));
        } catch {}
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeFilter, cacheKey, groupBy, storeFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!pickerRef.current?.contains(event.target as Node)) {
        setPickerOpen(false);
        setDraftSelection(committedSelection);
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setPickerOpen(false);
        setDraftSelection(committedSelection);
      }
    }
    if (pickerOpen) {
      document.addEventListener("mousedown", handlePointerDown);
      document.addEventListener("keydown", handleEscape);
    }
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [pickerOpen, committedSelection]);

  const trendData = useMemo(() => trend.map((p) => ({
    period: p.period,
    "Walk-ins": p.walkins,
    Conversions: p.conversions,
    "Avg Dwell (min)": p.avg_dwell,
  })), [trend]);

  const genderData = useMemo(() => (analytics?.gender ?? []).map((g) => ({
    name: g.label,
    value: g.value,
  })), [analytics?.gender]);

  const ageData = useMemo(() => (analytics?.age_bands ?? []).map((a) => ({
    name: a.label,
    value: a.value,
  })), [analytics?.age_bands]);

  return (
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <Title>Business Overview</Title>
          <Text>Walk-in, conversion and engagement analytics from the pipeline.</Text>
        </div>
        <div ref={pickerRef} className="relative w-full sm:w-auto">
          <button
            type="button"
            onClick={() => {
              setDraftSelection(committedSelection);
              setPickerOpen((open) => !open);
            }}
            className="flex w-full min-w-[270px] items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-left shadow-sm transition-colors hover:border-slate-300 sm:w-[320px]"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="rounded-lg bg-slate-100 p-2 text-slate-500">
                <CalendarDays size={16} />
              </span>
              <div className="min-w-0">
                <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Select date</div>
                <div className="truncate text-sm font-semibold text-slate-700">{activeFilter.summary}</div>
              </div>
            </div>
            <ChevronDown size={16} className={`shrink-0 text-slate-400 transition-transform ${pickerOpen ? "rotate-180" : ""}`} />
          </button>

          {pickerOpen && (
            <div className="absolute right-0 z-30 mt-3 w-[780px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
              <div className="flex min-h-[420px] flex-col md:flex-row">
                <div className="w-full border-b border-slate-200 bg-slate-50/80 md:w-[220px] md:border-b-0 md:border-r">
                  <div className="space-y-1 p-3">
                    {SIDEBAR_OPTIONS.map((option) => (
                      <button
                        key={option.key}
                        type="button"
                        onClick={() => setDraftSelection((current) => ({ ...current, mode: option.key }))}
                        className={`w-full rounded-xl px-4 py-3 text-left text-sm font-medium transition-colors ${draftSelection.mode === option.key ? "bg-slate-200 text-slate-900" : "text-slate-700 hover:bg-slate-100"}`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex-1 p-5">
                  {draftSelection.mode === "last" && (
                    <div className="space-y-5">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="text-3xl leading-none text-slate-500">Last</span>
                        <input
                          type="number"
                          min={1}
                          value={draftSelection.lastAmount}
                          onChange={(e) => setDraftSelection((current) => ({
                            ...current,
                            lastAmount: Math.max(1, Number(e.target.value || 1)),
                          }))}
                          className="h-12 w-36 rounded-2xl border border-slate-300 px-4 text-lg font-medium text-slate-800 outline-none transition focus:border-slate-500"
                        />
                        <select
                          value="days"
                          disabled
                          className="h-12 w-40 rounded-2xl border border-slate-300 bg-white px-4 text-lg font-medium text-slate-800 outline-none"
                        >
                          <option value="days">Days</option>
                        </select>
                        <label className="inline-flex items-center gap-3 text-lg font-medium text-slate-700">
                          <input
                            type="checkbox"
                            checked={draftSelection.includeToday}
                            onChange={(e) => setDraftSelection((current) => ({ ...current, includeToday: e.target.checked }))}
                            className="h-5 w-5 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
                          />
                          Include today
                        </label>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                        <div className="text-sm font-medium uppercase tracking-wide text-slate-400">Preview</div>
                        <div className="mt-2 text-2xl font-semibold text-slate-800">{draftPreview.summary}</div>
                        <div className="mt-2 text-sm text-slate-500">Use this for rolling windows like 7, 30, or 90 days without changing the page layout.</div>
                      </div>
                    </div>
                  )}

                  {draftSelection.mode === "custom" && (
                    <div className="space-y-5">
                      <div className="grid gap-4 md:grid-cols-2">
                        <label className="flex flex-col text-sm font-medium text-slate-600">
                          From
                          <input
                            type="date"
                            value={draftSelection.from}
                            onChange={(e) => setDraftSelection((current) => {
                              const nextFrom = e.target.value;
                              const nextTo = current.to && nextFrom && current.to < nextFrom ? nextFrom : current.to;
                              return { ...current, from: nextFrom, to: nextTo };
                            })}
                            className="mt-2 h-12 rounded-2xl border border-slate-300 px-4 text-lg font-medium text-slate-800 outline-none transition focus:border-slate-500"
                          />
                        </label>
                        <label className="flex flex-col text-sm font-medium text-slate-600">
                          To
                          <input
                            type="date"
                            value={draftSelection.to}
                            min={draftSelection.from || undefined}
                            onChange={(e) => setDraftSelection((current) => ({ ...current, to: e.target.value }))}
                            className="mt-2 h-12 rounded-2xl border border-slate-300 px-4 text-lg font-medium text-slate-800 outline-none transition focus:border-slate-500"
                          />
                        </label>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                        <div className="text-sm font-medium uppercase tracking-wide text-slate-400">Selected range</div>
                        <div className="mt-2 text-2xl font-semibold text-slate-800">{draftPreview.summary}</div>
                      </div>
                    </div>
                  )}

                  {(draftSelection.mode === "today" || draftSelection.mode === "yesterday") && (
                    <div className="space-y-5">
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                        <div className="text-sm font-medium uppercase tracking-wide text-slate-400">{draftPreview.label}</div>
                        <div className="mt-2 text-2xl font-semibold text-slate-800">{draftPreview.summary}</div>
                      </div>
                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="rounded-2xl border border-slate-200 p-4">
                          <div className="text-xs uppercase tracking-wide text-slate-400">From</div>
                          <div className="mt-1 text-lg font-semibold text-slate-700">{formatDisplayDate((draftPreview.filter.dateFrom as string) || "")}</div>
                        </div>
                        <div className="rounded-2xl border border-slate-200 p-4">
                          <div className="text-xs uppercase tracking-wide text-slate-400">To</div>
                          <div className="mt-1 text-lg font-semibold text-slate-700">{formatDisplayDate((draftPreview.filter.dateTo as string) || "")}</div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex flex-col gap-3 border-t border-slate-200 px-5 py-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="text-sm font-semibold text-slate-800">{draftPreview.summary}</div>
                  <div className={`text-xs ${draftError ? "text-red-500" : "text-slate-400"}`}>
                    {draftError || "Apply the selected range to analytics, trend, and leaderboard together."}
                  </div>
                </div>
                <div className="flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setDraftSelection(committedSelection);
                      setPickerOpen(false);
                    }}
                    className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={!!draftError || draftPreview.invalid}
                    onClick={() => {
                      if (draftError || draftPreview.invalid) return;
                      setCommittedSelection({
                        ...draftSelection,
                        lastAmount: Math.max(1, Math.floor(draftSelection.lastAmount || 1)),
                      });
                      setPickerOpen(false);
                    }}
                    className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    Apply
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <><Grid numItemsSm={2} numItemsLg={4} className="gap-4">
        <Card decoration="top" decorationColor="blue">
          <div className="flex items-start justify-between">
            <Text>Walk-ins</Text>
            {delta && <DeltaBadge pct={delta.delta_walkins_pct} />}
          </div>
          <Metric className="mt-1">{loading ? "—" : (analytics?.total_walkins ?? 0).toLocaleString()}</Metric>
          <Text className="text-xs text-slate-400 mt-1">Groups: {analytics?.total_groups ?? 0}</Text>
        </Card>
        <Card decoration="top" decorationColor="emerald">
          <div className="flex items-start justify-between">
            <Text>Conversions</Text>
            {delta && <DeltaBadge pct={delta.delta_conversions_pct} />}
          </div>
          <Metric className="mt-1">{loading ? "—" : (analytics?.total_conversions ?? 0).toLocaleString()}</Metric>
          <Text className="text-xs text-slate-400 mt-1">Out of {analytics?.total_walkins ?? 0} walk-ins</Text>
        </Card>
        <Card decoration="top" decorationColor="amber">
          <div className="flex items-start justify-between">
            <Text>Conversion Rate</Text>
            {delta && <DeltaBadge pct={delta.delta_rate_pct} />}
          </div>
          <Metric className="mt-1">{loading ? "—" : `${analytics?.conversion_rate ?? 0}%`}</Metric>
          <Text className="text-xs text-slate-400 mt-1">{activeFilter.summary}</Text>
        </Card>
        <Card decoration="top" decorationColor="indigo">
          <Text>Avg Dwell Time</Text>
          <Metric className="mt-1">{loading ? "—" : `${analytics?.avg_dwell_mins ?? 0} min`}</Metric>
          <Text className="text-xs text-slate-400 mt-1">Staff: {analytics?.total_staff ?? 0}</Text>
        </Card>
      </Grid>

      <Card>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
          <Title>Trend — Walk-ins &amp; Conversions</Title>
          <div className="flex rounded-lg overflow-hidden border border-slate-200 text-sm">
            {GROUP_OPTIONS.map((g) => (
              <button
                key={g.value}
                onClick={() => setGroupBy(g.value)}
                className={`px-3 py-1.5 ${groupBy === g.value ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>
        {!loading && trendData.length === 0 ? (
          <div className="h-56 flex items-center justify-center text-slate-400 bg-slate-50/50 rounded-lg border border-dashed text-sm">
            No trend data yet. Run the pipeline to populate this chart.
          </div>
        ) : (
          <TrendLineChart data={trendData} />
        )}
      </Card>

      <Grid numItemsSm={1} numItemsLg={2} className="gap-4">
        <Card>
          <Title>Gender Breakdown</Title>
          {genderData.length === 0 ? (
            <div className="h-40 flex items-center justify-center text-slate-400 text-sm">No data</div>
          ) : (
            <div className="flex items-center gap-6 mt-4">
              {(() => {
                const total = genderData.reduce((s, g) => s + g.value, 0);
                let cum = 0;
                const stops = genderData.map((g, i) => {
                  const start = (cum / total) * 360;
                  cum += g.value;
                  const end = (cum / total) * 360;
                  return `${GENDER_HEX[i % GENDER_HEX.length]} ${start.toFixed(1)}deg ${end.toFixed(1)}deg`;
                }).join(", ");
                return (
                  <div
                    className="rounded-full shrink-0"
                    style={{
                      width: 144, height: 144,
                      background: total > 0 ? `conic-gradient(${stops})` : "#f1f5f9",
                      WebkitMask: "radial-gradient(circle at center, transparent 42%, black 42%)",
                      mask: "radial-gradient(circle at center, transparent 42%, black 42%)",
                    }}
                  />
                );
              })()}
              <div className="space-y-2">
                {genderData.map((g, i) => {
                  const total = genderData.reduce((s, x) => s + x.value, 0);
                  return (
                    <div key={g.name} className="flex items-center gap-2 text-sm">
                      <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: GENDER_HEX[i % GENDER_HEX.length] }} />
                      <span className="text-slate-700 capitalize">{g.name.toLowerCase()}</span>
                      <span className="text-slate-400 ml-auto pl-4">{g.value} ({total ? Math.round(g.value / total * 100) : 0}%)</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Card>
        <Card>
          <Title>Age Band Breakdown</Title>
          {ageData.length === 0 ? (
            <div className="h-40 flex items-center justify-center text-slate-400 text-sm">No data</div>
          ) : (
            <div className="mt-4 space-y-3">
              {(() => {
                const maxVal = Math.max(...ageData.map((a) => a.value), 1);
                return ageData.map((a) => (
                  <div key={a.name} className="flex items-center gap-3">
                    <span className="text-xs text-slate-500 w-20 text-right shrink-0">{a.name}</span>
                    <div className="flex-1 bg-slate-100 rounded-full h-6 overflow-hidden">
                      <div
                        className="h-full rounded-full flex items-center pl-2 transition-all duration-500"
                        style={{ width: `${Math.max(8, Math.round((a.value / maxVal) * 100))}%`, backgroundColor: "#7c3aed" }}
                      >
                        <span className="text-white text-xs font-semibold">{a.value}</span>
                      </div>
                    </div>
                  </div>
                ));
              })()}
            </div>
          )}
        </Card>
      </Grid>

      {(analytics?.engagement ?? []).length > 0 && (
        <Card>
          <Title>Engagement Types</Title>
          <div className="mt-4 space-y-3">
            {(() => {
              const engData = analytics?.engagement ?? [];
              const maxVal = Math.max(...engData.map((e) => e.value), 1);
              return engData.map((e) => (
                <div key={e.label} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-36 text-right shrink-0 truncate" title={e.label}>{e.label}</span>
                  <div className="flex-1 bg-slate-100 rounded-full h-7 overflow-hidden">
                    <div
                      className="h-full rounded-full flex items-center pl-3 transition-all duration-500"
                      style={{ width: `${Math.max(8, Math.round((e.value / maxVal) * 100))}%`, backgroundColor: "#0284c7" }}
                    >
                      <span className="text-white text-xs font-semibold">{e.value}</span>
                    </div>
                  </div>
                </div>
              ));
            })()}
          </div>
        </Card>
      )}

      {leaderboard.length > 0 && (
        <Card>
          <Title>Store Leaderboard — {activeFilter.summary}</Title>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-100">
                  <th className="pb-2 font-medium">#</th>
                  <th className="pb-2 font-medium">Store</th>
                  <th className="pb-2 font-medium text-right">Walk-ins</th>
                  <th className="pb-2 font-medium text-right">Groups</th>
                  <th className="pb-2 font-medium text-right">Conversions</th>
                  <th className="pb-2 font-medium text-right">Conv. Rate</th>
                  <th className="pb-2 font-medium text-right">Avg Dwell</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((row, idx) => (
                  <tr key={row.store_id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                    <td className="py-2 text-slate-400">{idx + 1}</td>
                    <td className="py-2 font-medium text-slate-800">{row.store_name}</td>
                    <td className="py-2 text-right">{row.walkins.toLocaleString()}</td>
                    <td className="py-2 text-right text-slate-500">{row.groups.toLocaleString()}</td>
                    <td className="py-2 text-right text-emerald-700">{row.conversions.toLocaleString()}</td>
                    <td className="py-2 text-right">
                      <span className={`font-semibold ${row.conversion_rate >= 20 ? "text-emerald-600" : row.conversion_rate >= 10 ? "text-amber-600" : "text-red-500"}`}>
                        {row.conversion_rate}%
                      </span>
                    </td>
                    <td className="py-2 text-right text-slate-500">{row.avg_dwell} min</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      </>
    </div>
  );
}
