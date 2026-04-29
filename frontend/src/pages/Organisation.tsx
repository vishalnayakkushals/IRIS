import { useEffect, useState } from "react";
import { adminGetSettings, adminUpdateSettings } from "../api/client";
import { Card, Title, Text } from "@tremor/react";
import { Save } from "lucide-react";

const FIELDS: { key: string; label: string; type?: string; placeholder?: string }[] = [
  { key: "app_name", label: "Application Name", placeholder: "e.g. IRIS Intelligence" },
  { key: "org_name", label: "Organisation Name", placeholder: "e.g. Kushal's Jewellery" },
  { key: "support_email", label: "Support Email", type: "email", placeholder: "support@example.com" },
  { key: "brand_color_primary", label: "Primary Brand Color", placeholder: "#1E40AF" },
  { key: "brand_color_secondary", label: "Secondary Brand Color", placeholder: "#64748B" },
  { key: "font_family", label: "Font Family", placeholder: "Inter" },
  { key: "logo_path", label: "Logo Path / URL", placeholder: "/assets/logo.png" },
  { key: "timezone", label: "Timezone", placeholder: "Asia/Kolkata" },
  { key: "date_format", label: "Date Format", placeholder: "DD/MM/YYYY" },
  { key: "currency", label: "Currency Symbol", placeholder: "₹" },
];

const PASSWORD_FIELDS: { key: string; label: string }[] = [
  { key: "streamlit_password", label: "Fallback Admin Password" },
  { key: "admin_password_hint", label: "Admin Password Hint (display only)" },
];

export default function Organisation() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  useEffect(() => {
    adminGetSettings().then((r) => setSettings(r.data));
  }, []);

  function set(key: string, value: string) {
    setSettings((s) => ({ ...s, [key]: value }));
  }

  async function save() {
    setSaving(true);
    try {
      await adminUpdateSettings(settings);
      flash("Settings saved");
    } catch {
      flash("Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div>
        <Title>Organisation</Title>
        <Text>Configure application-wide branding, display settings, and metadata.</Text>
      </div>

      <Card className="p-6 space-y-5">
        <h3 className="font-semibold text-slate-700 text-sm">General Settings</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {FIELDS.map(({ key, label, type, placeholder }) => (
            <div key={key}>
              <label className="iris-label">{label}</label>
              <input
                type={type || "text"}
                placeholder={placeholder}
                value={settings[key] || ""}
                onChange={(e) => set(key, e.target.value)}
                className="iris-input"
              />
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-6 space-y-5">
        <h3 className="font-semibold text-slate-700 text-sm">Legacy / Access Settings</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {PASSWORD_FIELDS.map(({ key, label }) => (
            <div key={key}>
              <label className="iris-label">{label}</label>
              <input
                type="text"
                value={settings[key] || ""}
                onChange={(e) => set(key, e.target.value)}
                className="iris-input"
              />
            </div>
          ))}
        </div>
      </Card>

      <div className="flex justify-end">
        <button onClick={save} disabled={saving} className="iris-btn-primary">
          <Save size={14} />
          {saving ? "Saving…" : "Save All Settings"}
        </button>
      </div>
    </div>
  );
}
