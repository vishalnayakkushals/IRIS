import { useEffect, useRef, useState } from "react";
import { adminGetSettings, adminUpdateSettings, adminUploadLogo } from "../api/client";
import { Card, Title, Text } from "@tremor/react";
import { Pencil, Save, Upload, X, Check } from "lucide-react";

export default function Organisation() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [editingAppName, setEditingAppName] = useState(false);
  const [appNameDraft, setAppNameDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [toast, setToast] = useState("");
  const appNameInputRef = useRef<HTMLInputElement>(null);
  const logoInputRef = useRef<HTMLInputElement>(null);

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3500); }

  useEffect(() => {
    adminGetSettings().then((r) => {
      setSettings(r.data);
      setAppNameDraft(r.data.app_name || "");
    });
  }, []);

  function set(key: string, value: string) {
    setSettings((s) => ({ ...s, [key]: value }));
  }

  function startEditAppName() {
    setAppNameDraft(settings.app_name || "");
    setEditingAppName(true);
    setTimeout(() => appNameInputRef.current?.focus(), 50);
  }

  function cancelEditAppName() {
    setAppNameDraft(settings.app_name || "");
    setEditingAppName(false);
  }

  async function saveAppName() {
    if (!appNameDraft.trim()) return;
    setSaving(true);
    try {
      await adminUpdateSettings({ app_name: appNameDraft.trim() });
      setSettings((s) => ({ ...s, app_name: appNameDraft.trim() }));
      setEditingAppName(false);
      flash("App name updated");
    } catch {
      flash("Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleLogoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingLogo(true);
    try {
      const res = await adminUploadLogo(file);
      setSettings((s) => ({ ...s, logo_url: res.data.logo_url }));
      flash("Logo uploaded");
    } catch {
      flash("Logo upload failed");
    } finally {
      setUploadingLogo(false);
      if (logoInputRef.current) logoInputRef.current.value = "";
    }
  }

  function removeLogo() {
    setSettings((s) => ({ ...s, logo_url: "" }));
    adminUpdateSettings({ logo_url: "" }).catch(() => {});
  }

  async function saveFields() {
    setSaving(true);
    try {
      await adminUpdateSettings({
        org_name: settings.org_name || "",
        support_email: settings.support_email || "",
      });
      flash("Settings saved");
    } catch {
      flash("Save failed");
    } finally {
      setSaving(false);
    }
  }

  const logoUrl = settings.logo_url || "";
  const appName = settings.app_name || "IRIS Intelligence";

  return (
    <div className="space-y-6 max-w-2xl">
      {toast && (
        <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">
          {toast}
        </div>
      )}

      <div>
        <Title>Organisation</Title>
        <Text>Configure application branding and organisation details.</Text>
      </div>

      {/* App Identity Card — logo + app name */}
      <Card className="p-6">
        <div className="flex items-center gap-5">
          {/* Logo area */}
          <div className="relative flex-shrink-0">
            {logoUrl ? (
              <div className="relative group">
                <img
                  src={logoUrl}
                  alt="Organisation logo"
                  className="w-20 h-20 rounded-2xl object-contain border border-slate-200 bg-white p-1 shadow-sm"
                />
                <button
                  onClick={removeLogo}
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-rose-500 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow"
                >
                  <X size={10} />
                </button>
              </div>
            ) : (
              <div className="w-20 h-20 rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 flex flex-col items-center justify-center text-slate-400 text-xs gap-1">
                <Upload size={18} />
                <span>Logo</span>
              </div>
            )}
            <button
              onClick={() => logoInputRef.current?.click()}
              disabled={uploadingLogo}
              className="mt-2 w-20 text-center text-xs text-blue-600 hover:text-blue-700 disabled:opacity-50"
            >
              {uploadingLogo ? "Uploading…" : logoUrl ? "Change" : "Upload"}
            </button>
            <input
              ref={logoInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/svg+xml"
              className="hidden"
              onChange={handleLogoUpload}
            />
          </div>

          {/* App name + detail */}
          <div className="flex-1 min-w-0 space-y-4">
            <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Application Name</p>
            {editingAppName ? (
              <div className="flex items-center gap-2">
                <input
                  ref={appNameInputRef}
                  value={appNameDraft}
                  onChange={(e) => setAppNameDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") saveAppName(); if (e.key === "Escape") cancelEditAppName(); }}
                  className="flex-1 text-xl font-bold border-b-2 border-blue-400 outline-none bg-transparent text-slate-800 py-0.5"
                  placeholder="App name"
                />
                <button onClick={saveAppName} disabled={saving} className="p-1.5 rounded-lg bg-emerald-100 text-emerald-700 hover:bg-emerald-200 disabled:opacity-50">
                  <Check size={16} />
                </button>
                <button onClick={cancelEditAppName} className="p-1.5 rounded-lg bg-slate-100 text-slate-500 hover:bg-slate-200">
                  <X size={16} />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 group">
                <h2 className="text-xl font-bold text-slate-800 truncate">{appName}</h2>
                <button
                  onClick={startEditAppName}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-blue-600 hover:bg-blue-50 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <Pencil size={14} />
                </button>
              </div>
            )}
            <p className="text-xs text-slate-400 mt-1">Shown in the browser tab and top navigation</p>

            {/* App Detail / Tagline */}
            <div className="border-t border-slate-100 pt-3">
              <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">App Detail / Tagline</p>
              <div className="flex items-center gap-2">
                <input
                  value={settings.app_detail || ""}
                  onChange={(e) => set("app_detail", e.target.value)}
                  placeholder="e.g. Footfall Analysis"
                  className="iris-input text-sm flex-1"
                />
                <button
                  onClick={async () => {
                    setSaving(true);
                    try {
                      await adminUpdateSettings({ app_detail: settings.app_detail || "" });
                      flash("App detail updated");
                    } catch { flash("Save failed"); }
                    finally { setSaving(false); }
                  }}
                  disabled={saving}
                  className="iris-btn-primary shrink-0"
                >
                  <Save size={14} />
                  Save
                </button>
              </div>
              <p className="text-xs text-slate-400 mt-1">Subtitle shown below the app name in the navigation bar</p>
            </div>
          </div>
        </div>
      </Card>

      {/* Organisation details */}
      <Card className="p-6 space-y-5">
        <h3 className="font-semibold text-slate-700 text-sm">Organisation Details</h3>
        <div className="space-y-4">
          <div>
            <label className="iris-label">Organisation Name</label>
            <input
              type="text"
              placeholder="e.g. Kushal's Jewellery"
              value={settings.org_name || ""}
              onChange={(e) => set("org_name", e.target.value)}
              className="iris-input"
            />
          </div>
          <div>
            <label className="iris-label">Support Email</label>
            <input
              type="email"
              placeholder="support@example.com"
              value={settings.support_email || ""}
              onChange={(e) => set("support_email", e.target.value)}
              className="iris-input"
            />
          </div>
        </div>
        <div className="flex justify-end">
          <button onClick={saveFields} disabled={saving} className="iris-btn-primary">
            <Save size={14} />
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </Card>

      {/* Legacy/Access */}
      <Card className="p-6 space-y-5">
        <h3 className="font-semibold text-slate-700 text-sm">Legacy / Access Settings</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            { key: "streamlit_password", label: "Fallback Admin Password" },
            { key: "admin_password_hint", label: "Admin Password Hint (display only)" },
          ].map(({ key, label }) => (
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
        <div className="flex justify-end">
          <button
            onClick={async () => {
              setSaving(true);
              try {
                await adminUpdateSettings({
                  streamlit_password: settings.streamlit_password || "",
                  admin_password_hint: settings.admin_password_hint || "",
                });
                flash("Saved");
              } catch { flash("Save failed"); }
              finally { setSaving(false); }
            }}
            disabled={saving}
            className="iris-btn-primary"
          >
            <Save size={14} />
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </Card>
    </div>
  );
}
