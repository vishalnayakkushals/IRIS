import { useEffect, useMemo, useRef, useState } from "react";
import { adminDeleteStoreMaster, adminListStoreMaster, adminUploadStoreMasterFile, adminUpsertStoreMaster } from "../api/client";
import { Card, Title, Text } from "@tremor/react";
import { Upload, RefreshCw, Search, ChevronDown, X, Plus, Pencil, Trash2, Check } from "lucide-react";

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

// Dropdown filter for a column — shows unique values from the data
function ColFilter({ colKey, label, rows, value, onChange }: {
  colKey: string; label: string; rows: any[]; value: string; onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const options = useMemo(() => {
    const set = new Set<string>();
    for (const r of rows) { const v = String(r[colKey] || "").trim(); if (v) set.add(v); }
    return Array.from(set).sort();
  }, [rows, colKey]);

  if (options.length === 0) {
    return <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</span>;
  }

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen((p) => !p)}
        className={`flex items-center gap-1 text-xs font-semibold uppercase tracking-wider transition-colors ${value ? "text-blue-600" : "text-slate-500"}`}
      >
        {label} <ChevronDown size={11} />
        {value && <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-blue-500 inline-block" />}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-[200] bg-white border border-slate-200 rounded-lg shadow-xl min-w-[160px] max-h-56 overflow-y-auto py-1">
          <button
            onClick={() => { onChange(""); setOpen(false); }}
            className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-50 ${!value ? "text-blue-600 font-semibold" : "text-slate-500"}`}
          >
            All
          </button>
          {options.map((o) => (
            <button
              key={o}
              onClick={() => { onChange(o); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-50 ${o === value ? "text-blue-600 font-semibold bg-blue-50" : "text-slate-700"}`}
            >
              {o}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const FILTER_COLS = ["city", "state", "zone", "cluster_manager", "area_manager"];
const MANUAL_FIELDS = COLUMNS;

const EMPTY_FORM = {
  store_id: "",
  store_name: "",
  short_code: "",
  gofrugal_name: "",
  outlet_id: "",
  city: "",
  state: "",
  zone: "",
  country: "",
  mobile_no: "",
  store_email: "",
  cluster_manager: "",
  area_manager: "",
};

function StoreMasterForm({
  value,
  onChange,
  onSave,
  onCancel,
  saving,
  isNew,
}: {
  value: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  onSave: () => Promise<void>;
  onCancel: () => void;
  saving: boolean;
  isNew: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {isNew ? "Add Store Master Row" : `Edit ${value.store_id}`}
        </p>
        <p className="mt-1 text-sm text-slate-500">
          Keep Store ID aligned with Store Mapping. Saving here also updates the linked store shell details.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {MANUAL_FIELDS.map((field) => (
          <div key={field.key}>
            <label className="iris-label">
              {field.label}
              {field.required ? " *" : ""}
            </label>
            <input
              className="iris-input"
              value={value[field.key] || ""}
              disabled={!isNew && field.key === "store_id"}
              onChange={(event) => onChange({ ...value, [field.key]: event.target.value })}
            />
          </div>
        ))}
      </div>
      <div className="flex gap-2 border-t border-slate-100 pt-2">
        <button onClick={() => void onSave()} disabled={saving} className="iris-btn-primary">
          <Check size={14} />
          {saving ? "Saving…" : "Save Row"}
        </button>
        <button onClick={onCancel} className="iris-btn-secondary">
          <X size={14} />
          Cancel
        </button>
      </div>
    </div>
  );
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
  const [showNewRow, setShowNewRow] = useState(false);
  const [editingStoreId, setEditingStoreId] = useState("");
  const [formState, setFormState] = useState<Record<string, string>>(EMPTY_FORM);
  const [savingRow, setSavingRow] = useState(false);

  // Filter state
  const [search, setSearch] = useState("");
  const [colFilters, setColFilters] = useState<Record<string, string>>({});

  function setColFilter(key: string, value: string) {
    setColFilters((p) => ({ ...p, [key]: value }));
  }

  const filtered = useMemo(() => {
    let out = rows;
    const q = search.trim().toLowerCase();
    if (q) {
      out = out.filter((r) =>
        COLUMNS.some((c) => String(r[c.key] || "").toLowerCase().includes(q))
      );
    }
    for (const [key, val] of Object.entries(colFilters)) {
      if (val) out = out.filter((r) => String(r[key] || "").trim() === val);
    }
    return out;
  }, [rows, search, colFilters]);

  const activeFilters = Object.values(colFilters).filter(Boolean).length + (search.trim() ? 1 : 0);

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

  function beginCreate() {
    setFormState(EMPTY_FORM);
    setEditingStoreId("");
    setShowNewRow(true);
  }

  function beginEdit(row: any) {
    setFormState({
      store_id: String(row.store_id || ""),
      store_name: String(row.store_name || ""),
      short_code: String(row.short_code || ""),
      gofrugal_name: String(row.gofrugal_name || ""),
      outlet_id: String(row.outlet_id || ""),
      city: String(row.city || ""),
      state: String(row.state || ""),
      zone: String(row.zone || ""),
      country: String(row.country || ""),
      mobile_no: String(row.mobile_no || ""),
      store_email: String(row.store_email || ""),
      cluster_manager: String(row.cluster_manager || ""),
      area_manager: String(row.area_manager || ""),
    });
    setShowNewRow(false);
    setEditingStoreId(String(row.store_id || ""));
  }

  function resetEditor() {
    setShowNewRow(false);
    setEditingStoreId("");
    setFormState(EMPTY_FORM);
  }

  async function saveRow() {
    if (!String(formState.store_id || "").trim()) {
      flash("Store ID is required");
      return;
    }
    setSavingRow(true);
    try {
      await adminUpsertStoreMaster([formState]);
      flash(editingStoreId ? "Store master row updated" : "Store master row added");
      resetEditor();
      load();
    } catch (error: any) {
      flash(error?.response?.data?.detail || "Could not save store master row");
    } finally {
      setSavingRow(false);
    }
  }

  async function deleteRow(storeId: string) {
    if (!confirm(`Remove store master row for ${storeId}?`)) return;
    try {
      await adminDeleteStoreMaster(storeId);
      flash("Store master row removed");
      if (editingStoreId === storeId) resetEditor();
      load();
    } catch (error: any) {
      flash(error?.response?.data?.detail || "Could not delete store master row");
    }
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
          {tab === "table" && (
            <button onClick={beginCreate} className="iris-btn-secondary">
              <Plus size={14} /> Add Store Row
            </button>
          )}
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
        <div className="space-y-4">
          {(showNewRow || editingStoreId) && (
            <StoreMasterForm
              value={formState}
              onChange={setFormState}
              onSave={saveRow}
              onCancel={resetEditor}
              saving={savingRow}
              isNew={showNewRow}
            />
          )}

        <Card className="p-0 overflow-hidden">
          <div className="border-b px-4 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative min-w-[220px] flex-1 max-w-sm">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  className="iris-input pl-8"
                  placeholder="Search by store ID, name, short code, city, managers…"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              {activeFilters > 0 && (
                <button
                  onClick={() => {
                    setSearch("");
                    setColFilters({});
                  }}
                  className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
                >
                  <X size={12} /> Clear {activeFilters} filter{activeFilters > 1 ? "s" : ""}
                </button>
              )}
              <span className="ml-auto text-xs text-slate-400">{filtered.length} / {rows.length} stores</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {FILTER_COLS.map((columnKey) => {
                const column = COLUMNS.find((item) => item.key === columnKey);
                if (!column) return null;
                return (
                  <ColFilter
                    key={columnKey}
                    colKey={columnKey}
                    label={column.label}
                    rows={rows}
                    value={colFilters[columnKey] || ""}
                    onChange={(next) => setColFilter(columnKey, next)}
                  />
                );
              })}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left whitespace-nowrap">
              <thead>
                <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
                  {COLUMNS.map((c) => <th key={c.key} className="px-4 py-3">{c.label}</th>)}
                  <th className="px-4 py-3 sticky right-0 bg-slate-50 shadow-[-8px_0_8px_-4px_rgba(0,0,0,0.05)]">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((r) => (
                  <tr key={r.store_id} className="hover:bg-slate-50/50">
                    {COLUMNS.map((c) => (
                      <td key={c.key} className="px-4 py-3 text-slate-700">{r[c.key] || "—"}</td>
                    ))}
                    <td className="px-4 py-3 sticky right-0 bg-white shadow-[-8px_0_8px_-4px_rgba(0,0,0,0.05)]">
                      <div className="flex items-center gap-2">
                        <button onClick={() => beginEdit(r)} className="text-slate-400 transition hover:text-blue-600" title="Edit row">
                          <Pencil size={14} />
                        </button>
                        <button onClick={() => void deleteRow(r.store_id)} className="text-slate-400 transition hover:text-rose-600" title="Delete row">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={COLUMNS.length + 1} className="text-center py-12 text-gray-400 text-sm">{rows.length === 0 ? "No store master data. Use Import CSV / TSV to populate." : "No stores match the current filters."}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
        </div>
      )}
    </div>
  );
}
