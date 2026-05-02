import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { User, LogOut, ChevronDown } from "lucide-react";
import { adminGetSettings, getMe } from "../../api/client";
import { useStore } from "../../context/StoreContext";

export function TopNav() {
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState<{ email: string; full_name: string } | null>(null);
  const [appDetail, setAppDetail] = useState("Footfall Analysis");
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { storeId, setStoreId, stores } = useStore();

  useEffect(() => {
    getMe().then((r) => setUser(r.data)).catch(() => {});
    adminGetSettings().then((r) => {
      const data = r.data || {};
      setAppDetail(data.app_detail?.trim() || "Footfall Analysis");
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

  return (
    <header className="h-14 border-b bg-background flex items-center px-4 sticky top-0 z-10 w-full select-none gap-3">
      {/* IRIS app identity — always blue "IR" box + product name */}
      <div className="flex items-center gap-2.5 shrink-0">
        <div className="h-8 w-8 rounded-lg bg-blue-600 flex items-center justify-center shadow-sm shrink-0">
          <span className="text-white text-xs font-bold">IR</span>
        </div>
        <div className="leading-tight hidden sm:block">
          <p className="text-sm font-bold text-foreground tracking-wide">IRIS</p>
          <p className="text-[11px] text-muted-foreground">{appDetail}</p>
        </div>
      </div>

      {/* Global store selector — pre-selects context, affects all pages */}
      <div className="flex-1 flex items-center justify-center">
        <div className="relative">
          <select
            value={storeId}
            onChange={(e) => setStoreId(e.target.value)}
            className="appearance-none h-9 pl-3 pr-8 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-400 shadow-sm min-w-[180px] max-w-[300px] cursor-pointer"
          >
            <option value="">All Stores</option>
            {stores.map((s) => (
              <option key={s.store_id} value={s.store_id}>
                {s.store_name || s.store_id}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        </div>
      </div>

      {/* Profile dropdown */}
      <div className="shrink-0" ref={ref}>
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
          <div className="absolute right-4 mt-2 w-60 bg-white border border-slate-200 rounded-xl shadow-2xl py-1.5 z-[200]" style={{ filter: "drop-shadow(0 8px 24px rgba(0,0,0,0.15))" }}>
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
    </header>
  );
}
