import { useEffect, useRef, useState } from "react";
import { adminListStoreMaster, adminUpsertStoreMaster } from "../api/client";
import { Card, Title, Text, Button } from "@tremor/react";
import { Upload, RefreshCw } from "lucide-react";

const COLUMNS = [
  { key: "store_id", label: "Store ID", required: true },
  { key: "short_code", label: "Short Code" },
  { key: "gofrugal_name", label: "Gofrugal Name" },
  { key: "outlet_id", label: "Outlet ID" },
  { key: "city", label: "City" },
  { key: "state", label: "State" },
  { key: "zone", label: "Zone" },
  { key: "country", label: "Country" },
  { key: "mobile_no", label: "Mobile" },
  { key: "store_email", label: "Store Email" },
  { key: "cluster_manager", label: "Cluster Manager" },
  { key: "area_manager", label: "Area Manager" },
];

const HEADER_ALIASES: Record<string, string> = {
  storeid: "store_id",
  store_id: "store_id",
  shortcode: "short_code",
  short_code: "short_code",
  gofrugalname: "gofrugal_name",
  gofrugal_name: "gofrugal_name",
  outletid: "outlet_id",
  outlet_id: "outlet_id",
  city: "city",
  state: "state",
  zone: "zone",
  country: "country",
  mobileno: "mobile_no",
  mobile_no: "mobile_no",
  storeemail: "store_email",
  store_email: "store_email",
  clustermanager: "cluster_manager",
  cluster_manager: "cluster_manager",
  areamanager: "area_manager",
  area_manager: "area_manager",
};

function normalizeHeader(value: string): string {
  const compact = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const noUnderscore = compact.replace(/_/g, "");
  return HEADER_ALIASES[compact] ?? HEADER_ALIASES[noUnderscore] ?? compact;
}

function splitDelimitedLine(line: string, delimiter: string): string[] {
  const cells: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === "\"") {
      if (inQuotes && line[i + 1] === "\"") {
        current += "\"";
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === delimiter && !inQuotes) {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }

  cells.push(current.trim());
  return cells;
}

function parseStoreMaster(text: string): any[] {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
  if (!lines.length) return [];

  const delimiter = lines[0].includes("\t") ? "\t" : ",";
  const headers = splitDelimitedLine(lines[0], delimiter).map(normalizeHeader);

  return lines
    .slice(1)
    .map((line) => {
      const cells = splitDelimitedLine(line, delimiter);
      const row: Record<string, string> = {};
      headers.forEach((header, index) => {
        row[header] = (cells[index] || "").trim();
      });
      return row;
    })
    .filter((row) => String(row.store_id || "").trim());
}

export default function StoreMaster() {
  const [rows, setRows] = useState<any[]>([]);
  const [rawInput, setRawInput] = useState("");
  const [preview, setPreview] = useState<any[]>([]);
  const [importing, setImporting] = useState(false);
  const [toast, setToast] = useState("");
  const [tab, setTab] = useState<"table" | "import">("table");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  async function load() {
    adminListStoreMaster().then((r) => setRows(r.data));
  }

  useEffect(() => { load(); }, []);

  function handleRawInputChange(val: string) {
    setRawInput(val);
    setPreview(parseStoreMaster(val));
  }

  async function handleFileUpload(file: File) {
    const ext = file.name.toLowerCase();
    if (!(ext.endsWith(".csv") || ext.endsWith(".tsv") || ext.endsWith(".txt"))) {
      flash("Use a CSV or TSV file");
      return;
    }

    const text = await file.text();
    setRawInput(text);
    setPreview(parseStoreMaster(text));
    setTab("import");
    flash(`${file.name} loaded`);
  }

  async function doImport() {
    if (!preview.length) return;
    setImporting(true);
    try {
      await adminUpsertStoreMaster(preview);
      flash(`${preview.length} row(s) imported`);
      setRawInput(""); setPreview([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      load();
      setTab("table");
    } catch {
      flash("Import failed");
    } finally { setImporting(false); }
  }

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <Title>Store Master</Title>
          <Text>Central reference table for all stores — Gofrugal names, zones, managers.</Text>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant={tab === "table" ? "primary" : "secondary"} onClick={() => setTab("table")}>Table</Button>
          <Button size="sm" variant={tab === "import" ? "primary" : "secondary"} icon={Upload} onClick={() => setTab("import")}>Import CSV / TSV</Button>
          <button onClick={load} className="p-2 rounded border text-slate-500 hover:text-blue-600 hover:border-blue-400"><RefreshCw size={14} /></button>
        </div>
      </div>

      {tab === "import" && (
        <Card className="p-5 space-y-4">
          <p className="text-sm text-slate-600">Upload a `.csv` or `.tsv` file, or paste data below. First row must contain headers like: <span className="font-mono text-xs">{COLUMNS.map((c) => c.key).join(", ")}</span></p>
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFileUpload(file);
              }}
            />
            <Button variant="secondary" icon={Upload} onClick={() => fileInputRef.current?.click()}>
              Choose CSV / TSV File
            </Button>
            <Text className="text-xs text-slate-500">Supported: comma-separated or tab-separated files.</Text>
          </div>
          <textarea
            className="w-full border rounded px-3 py-2 text-sm font-mono h-48 focus:outline-none focus:ring-2 focus:ring-blue-300"
            placeholder={"store_id,short_code,gofrugal_name,...\nBLRRRN,RRN,Kushals Jewellery RR Nagar,..."}
            value={rawInput}
            onChange={(e) => handleRawInputChange(e.target.value)}
          />
          {preview.length > 0 && (
            <p className="text-sm text-slate-500">Preview: <span className="font-medium">{preview.length}</span> rows detected.</p>
          )}
          <div className="flex gap-2">
            <Button icon={Upload} loading={importing} disabled={!preview.length} onClick={doImport}>Import {preview.length} Rows</Button>
            <Button variant="secondary" onClick={() => { setRawInput(""); setPreview([]); if (fileInputRef.current) fileInputRef.current.value = ""; }}>Clear</Button>
          </div>
        </Card>
      )}

      {tab === "table" && (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left whitespace-nowrap">
              <thead>
                <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
                  {COLUMNS.map((c) => <th key={c.key} className="px-4 py-3">{c.label}</th>)}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.store_id} className="hover:bg-slate-50/50">
                    {COLUMNS.map((c) => (
                      <td key={c.key} className="px-4 py-3 text-slate-700">{r[c.key] || "—"}</td>
                    ))}
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={COLUMNS.length} className="text-center py-12 text-gray-400 text-sm">No store master data. Use Import CSV / TSV to populate.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
