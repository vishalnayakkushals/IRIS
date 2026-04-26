 
import { Bell, Search, User } from "lucide-react";

export function TopNav() {
  return (
    <header className="h-16 border-b bg-background flex items-center justify-between px-6 sticky top-0 z-10 w-full select-none">
      <div className="flex items-center text-muted-foreground bg-muted/50 rounded-md px-3 py-1.5 w-64 border border-border/50">
        <Search size={18} className="mr-2 opacity-50" />
        <input 
          type="text" 
          placeholder="Search stores or insights..." 
          className="bg-transparent border-none outline-none text-sm w-full placeholder:text-muted-foreground text-foreground"
        />
      </div>
      <div className="flex items-center space-x-4">
        <button className="p-2 text-muted-foreground hover:text-foreground transition-colors rounded-full hover:bg-muted">
          <Bell size={20} />
        </button>
        <div className="h-8 w-8 rounded-full border bg-secondary flex items-center justify-center text-secondary-foreground text-sm font-semibold cursor-pointer">
          <User size={16} />
        </div>
      </div>
    </header>
  );
}
