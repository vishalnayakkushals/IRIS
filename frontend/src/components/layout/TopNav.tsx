import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { User, LogOut, ChevronDown, Search, Store } from "lucide-react";
import { adminGetSettings, getMe } from "../../api/client";
import { useStore } from "../../context/StoreContext";

function StoreDropdown() {
  const { storeId, setStoreId, stores } = useStore();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Prefer stores with Drive link + sync enabled; fall back to all stores if none qualify
  const syncReady = stores.filter((s) => s.sync_enabled && s.drive_folder_url?.trim());
  const pool = syncReady.length > 0 ? syncReady : stores;

  const filtered = query.trim()
    ? pool.filter(
        (s) =>
          s.store_name.toLowerCase().includes(query.toLowerCase()) ||
          s.store_id.toLowerCase().includes(query.toLowerCase())
      )
    : pool;

  const selectedName = stores.find((s) => s.store_id === storeId)?.store_name ?? storeId;

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  function openDropdown() {
    setOpen(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  function select(id: string) {
    setStoreId(id);
    setOpen(false);
    setQuery("");
  }

  return (
    <div ref={ref} className="relative flex-1 flex items-center justify-center">
      {/* Trigger button */}
      <button
        onClick={openDropdown}
        className="flex items-center gap-2 h-9 px-3 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-medium shadow-sm hover:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors min-w-[200px] max-w-[320px] w-full sm:w-auto"
      >
        <Store size={14} className="text-slate-400 shrink-0" />
        <span className="flex-1 text-left truncate">
          {storeId && selectedName ? selectedName : "All Stores"}
        </span>
        <ChevronDown
          size={14}
          className={`text-slate-400 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          className="absolute top-full left-1/2 -translate-x-1/2 mt-1.5 w-72 bg-white border border-slate-200 rounded-xl shadow-2xl z-[300] overflow-hidden"
          style={{ filter: "drop-shadow(0 8px 24px rgba(0,0,0,0.15))" }}
        >
          {/* Search */}
          <div className="p-2 border-b border-slate-100">
            <div className="flex items-center gap-2 px-2 h-8 rounded-md bg-slate-50 border border-slate-200">
              <Search size={13} className="text-slate-400 shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search stores…"
                className="flex-1 bg-transparent text-sm text-slate-700 placeholder-slate-400 focus:outline-none"
              />
            </div>
          </div>

          {/* List */}
          <div className="max-h-64 overflow-y-auto py-1">
            {/* Always-visible All Stores option */}
            {!query.trim() && (
              <button
                onClick={() => select("")}
                className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-blue-50 transition-colors border-b border-slate-100 ${
                  !storeId ? "bg-blue-50 text-blue-700 font-medium" : "text-slate-500"
                }`}
              >
                <Store size={13} className="shrink-0 text-slate-400" />
                <span>All Stores</span>
              </button>
            )}
            {filtered.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-4">No matching stores</p>
            ) : (
              filtered.map((s) => (
                <button
                  key={s.store_id}
                  onClick={() => select(s.store_id)}
                  className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-blue-50 transition-colors ${
                    s.store_id === storeId ? "bg-blue-50 text-blue-700 font-medium" : "text-slate-700"
                  }`}
                >
                  <Store size={13} className="shrink-0 text-slate-400" />
                  <span className="truncate">{s.store_name || s.store_id}</span>
                  <span className="ml-auto text-[10px] text-slate-400 font-mono shrink-0">{s.store_id}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function TopNav() {
  const [profileOpen, setProfileOpen] = useState(false);
  const [user, setUser] = useState<{ email: string; full_name: string } | null>(null);
  const [appDetail, setAppDetail] = useState("Footfall Analysis");
  const profileRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

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
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) setProfileOpen(false);
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
    <header className="h-14 border-b bg-background flex items-center pl-5 pr-4 sticky top-0 z-10 w-full select-none gap-3">
      {/* IRIS app identity */}
      <div className="flex items-center gap-2.5 shrink-0">
        <div className="h-8 w-8 rounded-lg bg-blue-600 flex items-center justify-center shadow-sm shrink-0">
          <span className="text-white text-xs font-bold">IR</span>
        </div>
        <div className="leading-tight hidden sm:block">
          <p className="text-sm font-bold text-foreground tracking-wide">IRIS</p>
          <p className="text-[11px] text-muted-foreground">{appDetail}</p>
        </div>
      </div>

      {/* Searchable global store selector */}
      <StoreDropdown />

      {/* Profile dropdown */}
      <div className="shrink-0" ref={profileRef}>
        <button
          onClick={() => setProfileOpen((o) => !o)}
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

        {profileOpen && (
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
