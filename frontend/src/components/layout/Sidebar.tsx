import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { adminGetSettings } from "../../api/client";
import {
  Building2,
  Camera,
  Settings,
  Clock,
  LayoutDashboard,
  BarChart3,
  Network,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

interface NavItem {
  name: string;
  path?: string;
  icon: React.ReactNode;
  children?: { name: string; path: string }[];
}

const menu: NavItem[] = [
  { name: "Overview", path: "/overview", icon: <LayoutDashboard size={18} /> },
  { name: "Store Detail", path: "/detail", icon: <Building2 size={18} /> },
  { name: "Reports", path: "/reports", icon: <BarChart3 size={18} /> },
  { name: "Customer Journeys", path: "/journeys", icon: <Network size={18} /> },
  {
    name: "Quality Assurance",
    icon: <Camera size={18} />,
    children: [
      { name: "QA Overview", path: "/quality" },
      { name: "Frame Review", path: "/qa/frame-review" },
      { name: "Model Feedback", path: "/qa/model-feedback" },
    ],
  },
  { name: "Scheduler / Pipeline", path: "/scheduler", icon: <Clock size={18} /> },
  {
    name: "Admin",
    icon: <Settings size={18} />,
    children: [
      { name: "Store Mapping", path: "/admin/stores" },
      { name: "Store Master", path: "/admin/store-master" },
      { name: "Camera Zones", path: "/admin/cameras" },
      { name: "Employees", path: "/admin/employees" },
      { name: "Users", path: "/admin/users" },
      { name: "Roles & Permissions", path: "/admin/roles" },
      { name: "Store Access", path: "/admin/store-access" },
      { name: "Organisation", path: "/admin/organisation" },
      { name: "Model Accuracy", path: "/admin/model-accuracy" },
      { name: "Activity Logs", path: "/admin/activity" },
    ],
  },
];

export function Sidebar() {
  const location = useLocation();
  const [branding, setBranding] = useState<Record<string, string>>({});
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => ({
    Admin: location.pathname.startsWith("/admin"),
    "Quality Assurance": location.pathname.startsWith("/quality") || location.pathname.startsWith("/qa/"),
  }));

  useEffect(() => {
    adminGetSettings().then((r) => setBranding(r.data || {})).catch(() => {});
  }, []);

  function toggleGroup(name: string) {
    setOpenGroups((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  const logoUrl = branding.logo_url?.trim() || "";

  return (
    <aside className="w-64 border-r bg-background min-h-screen hidden md:flex flex-col select-none">
      <div className="border-b flex-shrink-0 px-5 py-4 flex items-center justify-center">
        {logoUrl ? (
          <img src={logoUrl} alt="Logo" className="h-10 w-10 rounded-xl border object-contain bg-white p-1 shadow-sm" />
        ) : (
          <div className="h-10 w-10 rounded-xl bg-blue-600 flex items-center justify-center shadow-sm">
            <span className="text-white text-sm font-bold">IR</span>
          </div>
        )}
      </div>
      <nav className="p-3 space-y-0.5 flex-1 overflow-y-auto">
        {menu.map((item) => {
          if (item.children) {
            const isOpen = openGroups[item.name] ?? false;
            const anyChildActive = item.children.some((c) => location.pathname === c.path);
            return (
              <div key={item.name}>
                <button
                  onClick={() => toggleGroup(item.name)}
                  className={cn(
                    "w-full flex items-center justify-between px-3 py-2.5 rounded-md transition-colors text-sm font-medium",
                    anyChildActive
                      ? "bg-secondary text-secondary-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <span className="flex items-center">
                    <span className="mr-3">{item.icon}</span>
                    {item.name}
                  </span>
                  {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                {isOpen && (
                  <div className="ml-6 mt-0.5 space-y-0.5 border-l pl-3">
                    {item.children.map((child) => {
                      const isActive = location.pathname === child.path;
                      return (
                        <Link
                          key={child.path}
                          to={child.path}
                          className={cn(
                            "flex items-center px-2 py-2 rounded-md transition-colors text-sm",
                            isActive
                              ? "bg-secondary text-secondary-foreground font-medium"
                              : "text-muted-foreground hover:bg-muted hover:text-foreground"
                          )}
                        >
                          {child.name}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          }

          const isActive = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path!}
              className={cn(
                "flex items-center px-3 py-2.5 rounded-md transition-colors text-sm font-medium",
                isActive
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <span className="mr-3">{item.icon}</span>
              {item.name}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
