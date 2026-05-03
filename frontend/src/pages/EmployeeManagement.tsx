import { useEffect, useRef, useState } from "react";
import { adminListEmployees, adminListAllEmployees, adminDeleteEmployee, api } from "../api/client";
import { Card, Title, Text, Button, Badge } from "@tremor/react";
import { Upload, Trash2, UserCircle } from "lucide-react";
import { useStore } from "../context/StoreContext";

export default function EmployeeManagement() {
  const { storeId, storeName } = useStore();
  const [employees, setEmployees] = useState<any[]>([]);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const allStores = !storeId;

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  useEffect(() => {
    if (allStores) {
      adminListAllEmployees().then((r) => setEmployees(r.data)).catch(() => setEmployees([]));
    } else {
      adminListEmployees(storeId).then((r) => setEmployees(r.data)).catch(() => setEmployees([]));
    }
  }, [storeId, allStores]);

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

  async function handleDelete(id: number, name: string, empStoreId: string) {
    if (!confirm(`Remove employee "${name}"?`)) return;
    await adminDeleteEmployee(empStoreId, id);
    if (allStores) {
      adminListAllEmployees().then((r) => setEmployees(r.data));
    } else {
      adminListEmployees(storeId).then((r) => setEmployees(r.data));
    }
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
          <Text>
            {allStores
              ? "Showing employees across all stores."
              : `Upload employee photos for staff recognition — ${storeName || storeId}.`}
          </Text>
        </div>
        {!allStores && (
          <div className="flex gap-3 items-center">
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
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Active</Text><p className="text-2xl font-bold mt-1">{active.length}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Inactive</Text><p className="text-2xl font-bold mt-1">{inactive.length}</p></Card>
      </div>

      {employees.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">
          {allStores ? "No employees across any stores." : "No employees for this store. Upload photos above."}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {employees.map((emp) => (
            <div key={emp.id} className={`border rounded-xl bg-white p-4 flex flex-col items-center gap-2 hover:shadow-sm transition-shadow ${!emp.is_active ? "opacity-50" : ""}`}>
              <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center overflow-hidden">
                <UserCircle size={40} className="text-slate-300" />
              </div>
              <p className="text-sm font-medium text-slate-700 text-center leading-tight">{emp.employee_name}</p>
              {allStores && (
                <Badge color="slate" className="text-[10px]">{emp.store_id}</Badge>
              )}
              <p className="text-xs text-slate-400">{emp.is_active ? "Active" : "Inactive"}</p>
              <button
                onClick={() => handleDelete(emp.id, emp.employee_name, emp.store_id)}
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
