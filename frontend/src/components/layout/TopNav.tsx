import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, User, LogOut, ChevronDown } from "lucide-react";
import { adminGetSettings, getMe } from "../../api/client";

export function TopNav() {
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState<{ email: string; full_name: string } | null>(null);
  const [branding, setBranding] = useState<Record<string, string>>({});
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getMe().then((r) => setUser(r.data)).catch(() => {});
    adminGetSettings().then((r) => {
      const data = r.data || {};
      setBranding(data);
      const appName = data.app_name?.trim() || "IRIS";
      const orgName = data.org_name?.trim();
      document.title = orgName ? `${appName} | ${orgName}` : appName;
    }).catch(() => {});
  }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function logout() {
    localStorage.removeItem("iris_token");
    navigate("/login");
  }

  const initials = user?.full_name
    ? user.full_name.split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2)
    : <User size={16} />;
  const appName = branding.app_name?.trim() || "IRIS";
  const supportEmail = branding.support_email?.trim() || "";
  const timezone = branding.timezone?.trim() || "Asia/Kolkata";
  const brandPrimary = branding.brand_color_primary?.trim() || "#2563EB";

  return (
    <header className="h-16 border-b bg-background flex items-center justify-between px-6 sticky top-0 z-10 w-full select-none">
      <div className="flex items-center gap-3 min-w-0">
        <div className="h-10 w-1 rounded-full" style={{ backgroundColor: brandPrimary }} />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground truncate">{appName} Control Center</p>
          <p className="text-xs text-muted-foreground truncate">
            {supportEmail ? `Support: ${supportEmail}` : "Management preview build"} • {timezone}
          </p>
        </div>
      </div>

      <div className="flex items-center space-x-3">
        <button className="p-2 text-muted-foreground hover:text-foreground transition-colors rounded-full hover:bg-muted">
          <Bell size={20} />
        </button>

        {/* Profile dropdown */}
        <div className="relative" ref={ref}>
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-muted transition-colors"
          >
            <div className="h-8 w-8 rounded-full border bg-secondary flex items-center justify-center text-secondary-foreground text-xs font-semibold">
              {initials}
            </div>
            {user && (
              <span className="text-sm text-muted-foreground hidden sm:block max-w-[140px] truncate">
                {user.full_name || user.email}
              </span>
            )}
            <ChevronDown size={14} className="text-muted-foreground" />
          </button>

          {open && (
            <div className="absolute right-0 mt-2 w-60 bg-white border border-slate-200 rounded-xl shadow-2xl py-1.5 z-[200]" style={{filter: "drop-shadow(0 8px 24px rgba(0,0,0,0.15))"}}>
              {user && (
                <div className="px-4 py-3 border-b border-slate-100 bg-slate-50 rounded-t-xl">
                  <p className="text-sm font-semibold text-slate-800 truncate">{user.full_name}</p>
                  <p className="text-xs text-slate-500 truncate mt-0.5">{user.email}</p>
                </div>
              )}
              <div className="py-1">
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm font-medium text-rose-600 hover:bg-rose-50 active:bg-rose-100 transition-colors rounded-b-xl"
                >
                  <LogOut size={15} />
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
