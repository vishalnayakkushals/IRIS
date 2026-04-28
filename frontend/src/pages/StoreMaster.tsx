import { useEffect, useState } from "react";
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

function parseTsv(text: string): any[] {
  const lines = text.trim().split("\n").filter(Boolean);
  if (!lines.length) return [];
  const headers = lines[0].split("\t").map((h) => h.trim().toLowerCase().replace(/\s+/g, "_"));
  return lines.slice(1).map((line) => {
    const cells = line.split("\t");
    const row: any = {};
    headers.forEach((h, i) => { row[h] = (cells[i] || "").trim(); });
    return row;
  });
}

export default function StoreMaster() {
  const [rows, setRows] = useState<any[]>([]);
  const [tsv, setTsv] = useState("");
  const [preview, setPreview] = useState<any[]>([]);
  const [importing, setImporting] = useState(false);
  const [toast, setToast] = useState("");
  const [tab, setTab] = useState<"table" | "import">("table");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  async function load() {
    adminListStoreMaster().then((r) => setRows(r.data));
  }

  useEffect(() => { load(); }, []);

  function handleTsvChange(val: string) {
    setTsv(val);
    setPreview(parseTsv(val));
  }

  async function doImport() {
    if (!preview.length) return;
    setImporting(true);
    try {
      await adminUpsertStoreMaster(preview);
      flash(`${preview.length} row(s) imported`);
      setTsv(""); setPreview([]);
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
          <Button size="sm" variant={tab === "import" ? "primary" : "secondary"} icon={Upload} onClick={() => setTab("import")}>Import TSV</Button>
          <button onClick={load} className="p-2 rounded border text-slate-500 hover:text-blue-600 hover:border-blue-400"><RefreshCw size={14} /></button>
        </div>
      </div>

      {tab === "import" && (
        <Card className="p-5 space-y-4">
          <p className="text-sm text-slate-600">Paste a tab-separated table below. First row must be headers matching: <span className="font-mono text-xs">{COLUMNS.map((c) => c.key).join(", ")}</span></p>
          <textarea
            className="w-full border rounded px-3 py-2 text-sm font-mono h-48 focus:outline-none focus:ring-2 focus:ring-blue-300"
            placeholder={"store_id\tshort_code\tgofrugal_name\t...\nD07\tD07\tKushals Jewellery Jayanagar\t..."}
            value={tsv}
            onChange={(e) => handleTsvChange(e.target.value)}
          />
          {preview.length > 0 && (
            <p className="text-sm text-slate-500">Preview: <span className="font-medium">{preview.length}</span> rows detected.</p>
          )}
          <div className="flex gap-2">
            <Button icon={Upload} loading={importing} disabled={!preview.length} onClick={doImport}>Import {preview.length} Rows</Button>
            <Button variant="secondary" onClick={() => { setTsv(""); setPreview([]); }}>Clear</Button>
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
                  <tr><td colSpan={COLUMNS.length} className="text-center py-12 text-gray-400 text-sm">No store master data. Use Import TSV to populate.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
