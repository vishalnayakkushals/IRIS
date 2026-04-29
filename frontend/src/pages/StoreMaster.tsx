import { useEffect, useRef, useState } from "react";
import { adminListStoreMaster, adminUploadStoreMasterFile, adminUpsertStoreMaster } from "../api/client";
import { Card, Title, Text } from "@tremor/react";
import { Upload, RefreshCw } from "lucide-react";

const COLUMNS = [
  { key: "store_id", label: "Store ID", required: true },
  { key: "store_name", label: "Store Name" },
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
  storename: "store_name",
  store_name: "store_name",
  outletname: "store_name",
  outlet_name: "store_name",
  branch: "store_name",
  branchname: "store_name",
  branch_name: "store_name",
  locationname: "store_name",
  location_name: "store_name",
  name: "store_name",
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

function hasUsefulStoreMasterData(row: Record<string, string>): boolean {
  return [
    row.store_id,
    row.store_name,
    row.short_code,
    row.gofrugal_name,
    row.outlet_id,
    row.store_email,
  ].some((value) => String(value || "").trim());
}

function parseStoreMaster(text: string): any[] {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
  if (!lines.length) return [];

  const delimiter = lines[0].includes("\t") ? "\t" : lines[0].includes(";") ? ";" : ",";
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
    .filter((row) => hasUsefulStoreMasterData(row));
}

export default function StoreMaster() {
  const [rows, setRows] = useState<any[]>([]);
  const [rawInput, setRawInput] = useState("");
  const [preview, setPreview] = useState<any[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [toast, setToast] = useState("");
  const [importErrors, setImportErrors] = useState<{ row: string; index: number; error: string }[]>([]);
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
    setSelectedFile(file);
    setRawInput(text);
    setPreview(parseStoreMaster(text));
    setTab("import");
    flash(`${file.name} loaded`);
  }

  async function doImport() {
    if (!preview.length) return;
    setImporting(true);
    setImportErrors([]);
    try {
      let response;
      if (selectedFile) {
        response = await adminUploadStoreMasterFile(selectedFile);
      } else {
        response = await adminUpsertStoreMaster(preview);
      }
      const meta = response?.data || {};
      const createdStores = Number(meta.created_stores || 0);
      const matchedExisting = Number(meta.matched_existing || 0);
      const generatedStoreIds = Number(meta.generated_store_ids || 0);
      const processed = Number(meta.processed || preview.length);
      const rowErrors: { row: string; index: number; error: string }[] = meta.errors || [];
      if (rowErrors.length) {
        setImportErrors(rowErrors);
        flash(`${processed} imported, ${rowErrors.length} row(s) had issues — see below`);
      } else {
        flash(`${processed} row(s) imported${createdStores ? `, ${createdStores} store(s) created` : ""}${matchedExisting ? `, ${matchedExisting} mapped automatically` : ""}${generatedStoreIds ? `, ${generatedStoreIds} ID(s) generated` : ""}`);
        setRawInput(""); setPreview([]); setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
        setTab("table");
      }
      load();
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Import failed");
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
          <button onClick={() => setTab("table")} className={tab === "table" ? "iris-btn-primary" : "iris-btn-secondary"}>Table</button>
          <button onClick={() => setTab("import")} className={tab === "import" ? "iris-btn-primary" : "iris-btn-secondary"}>
            <Upload size={14} /> Import CSV / TSV
          </button>
          <button onClick={load} className="p-2 rounded border text-slate-500 hover:text-blue-600 hover:border-blue-400"><RefreshCw size={14} /></button>
        </div>
      </div>

      {tab === "import" && (
        <Card className="p-5 space-y-4">
          <p className="text-sm text-slate-600">Upload a `.csv` or `.tsv` file, or paste data below. The importer will try to recognise store rows from headers such as <span className="font-mono text-xs">store_id, store_name, outlet_id, short_code, gofrugal_name</span> and clean common variants automatically.</p>
          <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-3 py-2">System-ready import is enabled. If a row does not exactly match Store Mapping, IRIS will try to map it using store name, short code, gofrugal name, and outlet ID. If needed, it will create the missing store shell automatically so import does not get blocked.</p>
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
            <button className="iris-btn-secondary" onClick={() => fileInputRef.current?.click()}>
              <Upload size={14} /> Choose CSV / TSV File
            </button>
            <Text className="text-xs text-slate-500">Supported: comma-separated or tab-separated files.</Text>
          </div>
          {selectedFile && (
            <Text className="text-xs text-slate-500">Selected file: <span className="font-medium">{selectedFile.name}</span></Text>
          )}
          <textarea
            className="w-full border rounded px-3 py-2 text-sm font-mono h-48 focus:outline-none focus:ring-2 focus:ring-blue-300"
              placeholder={"store_id,store_name,short_code,gofrugal_name,...\nBLRRRN,BLR - RR NAGAR,RRN,Kushals Jewellery RR Nagar,..."}
              value={rawInput}
              onChange={(e) => {
                setSelectedFile(null);
              handleRawInputChange(e.target.value);
            }}
          />
          {preview.length > 0 && (
            <p className="text-sm text-slate-500">Preview: <span className="font-medium">{preview.length}</span> rows detected.</p>
          )}
          {importErrors.length > 0 && (
            <div className="border border-rose-200 bg-rose-50 rounded-lg p-4 space-y-2">
              <p className="text-sm font-semibold text-rose-700">{importErrors.length} row(s) had issues — other rows were saved successfully:</p>
              <ul className="space-y-1">
                {importErrors.map((e) => (
                  <li key={e.index} className="text-xs text-rose-600 font-mono">
                    <span className="font-semibold">Row {e.index} ({e.row}):</span> {e.error}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex gap-2">
            <button className="iris-btn-primary" disabled={!preview.length || importing} onClick={doImport}>
              <Upload size={14} /> {importing ? "Importing…" : `Import ${preview.length} Rows`}
            </button>
            <button className="iris-btn-secondary" onClick={() => { setRawInput(""); setPreview([]); setSelectedFile(null); setImportErrors([]); if (fileInputRef.current) fileInputRef.current.value = ""; }}>Clear</button>
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
