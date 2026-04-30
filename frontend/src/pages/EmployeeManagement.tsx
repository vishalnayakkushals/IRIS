import { useEffect, useRef, useState } from "react";
import { adminListStores, adminListEmployees, adminDeleteEmployee, api } from "../api/client";
import { Card, Title, Text, Button } from "@tremor/react";
import { Upload, Trash2, UserCircle } from "lucide-react";
import StoreSelect from "../components/StoreSelect";

export default function EmployeeManagement() {
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState("");
  const [employees, setEmployees] = useState<any[]>([]);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  useEffect(() => {
    adminListStores().then((r) => {
      setStores(r.data);
      if (r.data.length) setStoreId(r.data[0].store_id);
    });
  }, []);

  useEffect(() => {
    if (!storeId) return;
    adminListEmployees(storeId).then((r) => setEmployees(r.data));
  }, [storeId]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || !storeId) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        await api.post(`/admin/employees/${storeId}`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      }
      adminListEmployees(storeId).then((r) => setEmployees(r.data));
      flash(`${files.length} photo(s) uploaded`);
    } catch {
      flash("Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Remove employee "${name}"?`)) return;
    await adminDeleteEmployee(storeId, id);
    adminListEmployees(storeId).then((r) => setEmployees(r.data));
    flash("Removed");
  }

  const active = employees.filter((e) => e.is_active);
  const inactive = employees.filter((e) => !e.is_active);

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Title>Employee Management</Title>
          <Text>Upload employee photos for staff recognition during pipeline runs.</Text>
        </div>
        <div className="flex gap-3 items-center">
          <div className="w-72">
            <StoreSelect
              stores={stores}
              value={storeId}
              onChange={setStoreId}
              placeholder="Select store"
            />
          </div>
          <Button
            size="sm"
            icon={Upload}
            loading={uploading}
            onClick={() => fileRef.current?.click()}
          >
            Upload Photos
          </Button>
          <input ref={fileRef} type="file" accept="image/*" multiple className="hidden" onChange={handleUpload} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Active</Text><p className="text-2xl font-bold mt-1">{active.length}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Inactive</Text><p className="text-2xl font-bold mt-1">{inactive.length}</p></Card>
      </div>

      {employees.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">
          No employees for this store. Upload photos above.
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {employees.map((emp) => (
            <div key={emp.id} className={`border rounded-xl bg-white p-4 flex flex-col items-center gap-2 hover:shadow-sm transition-shadow ${!emp.is_active ? "opacity-50" : ""}`}>
              <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center overflow-hidden">
                <UserCircle size={40} className="text-slate-300" />
              </div>
              <p className="text-sm font-medium text-slate-700 text-center leading-tight">{emp.employee_name}</p>
              <p className="text-xs text-slate-400">{emp.is_active ? "Active" : "Inactive"}</p>
              <button
                onClick={() => handleDelete(emp.id, emp.employee_name)}
                className="text-xs text-slate-400 hover:text-rose-600 flex items-center gap-1 mt-1"
              >
                <Trash2 size={12} /> Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
