import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { 
  Building2, 
  Users, 
  Camera, 
  Settings, 
  Clock, 
  LayoutDashboard 
} from "lucide-react";

export function Sidebar() {
  const location = useLocation();

  const menu = [
    { name: "Overview", path: "/", icon: <LayoutDashboard size={20} /> },
    { name: "Store Hub", path: "/stores", icon: <Building2 size={20} /> },
    { name: "Walk-ins", path: "/walkins", icon: <Users size={20} /> },
    { name: "Cameras", path: "/cameras", icon: <Camera size={20} /> },
    { name: "Live Pipeline", path: "/pipeline", icon: <Clock size={20} /> },
    { name: "Settings", path: "/settings", icon: <Settings size={20} /> },
  ];

  return (
    <aside className="w-64 border-r bg-background min-h-screen hidden md:block select-none">
      <div className="h-16 flex items-center px-6 border-b">
        <h1 className="text-xl font-bold tracking-tight text-primary">
          <span className="text-brand-blue">IRIS</span> 
           <span className="text-muted-foreground text-sm ml-2 font-normal">Intelligence</span>
        </h1>
      </div>
      <nav className="p-4 space-y-1">
        {menu.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
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
