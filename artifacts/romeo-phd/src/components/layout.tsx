import { Link, useLocation } from "wouter";
import { motion } from "framer-motion";
import { Terminal, LayoutDashboard, Code, Activity, ShieldAlert, LogOut, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/ide", label: "Studio IDE", icon: Code },
  { href: "/telemetry", label: "Telemetry", icon: Activity },
  { href: "/consultations", label: "Consultations", icon: ShieldAlert },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();

  // On the IDE page, we might want to hide the sidebar or make it compact to maximize screen space.
  // For now, let's keep it visible but tight.
  const isIDE = location.startsWith("/ide");

  return (
    <div className="min-h-screen bg-background text-foreground flex overflow-hidden">
      {/* Sidebar */}
      <aside className={cn(
        "flex flex-col fixed inset-y-0 left-0 z-50 transition-all duration-300 border-r border-border bg-sidebar",
        isIDE ? "w-16 items-center" : "w-64"
      )}>
        <div className={cn("h-16 flex items-center border-b border-border w-full", isIDE ? "justify-center" : "px-6")}>
          <Terminal className="w-6 h-6 text-primary flex-shrink-0" />
          {!isIDE && (
            <span className="font-display font-bold text-lg tracking-wider ml-3 text-transparent bg-clip-text bg-gradient-to-r from-primary to-blue-400 whitespace-nowrap">
              ROMEO PHD 6.0
            </span>
          )}
        </div>
        
        <div className={cn("flex-1 py-6 flex flex-col gap-2 w-full", isIDE ? "px-2" : "px-4")}>
          {!isIDE && (
            <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-2 px-2">
              Mission Control
            </div>
          )}
          {navItems.map((item) => {
            const isActive = location === item.href || (item.href !== "/" && location.startsWith(item.href));
            return (
              <Link key={item.href} href={item.href} className="outline-none w-full">
                <div
                  title={isIDE ? item.label : undefined}
                  className={cn(
                    "flex items-center rounded-lg transition-all duration-200 group relative cursor-pointer",
                    isIDE ? "justify-center p-3" : "px-3 py-2.5",
                    isActive 
                      ? "bg-primary/10 text-primary" 
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )}
                >
                  {isActive && !isIDE && (
                    <motion.div
                      layoutId="sidebar-active"
                      className="absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent border-l-2 border-primary rounded-lg"
                      initial={false}
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    />
                  )}
                  {isActive && isIDE && (
                     <motion.div
                     layoutId="sidebar-active-icon"
                     className="absolute inset-0 bg-primary/10 rounded-lg border-l-2 border-primary"
                     initial={false}
                     transition={{ type: "spring", stiffness: 300, damping: 30 }}
                   />
                  )}
                  <item.icon className={cn("w-5 h-5 relative z-10 flex-shrink-0", !isIDE && "mr-3")} />
                  {!isIDE && <span className="font-medium relative z-10 whitespace-nowrap">{item.label}</span>}
                </div>
              </Link>
            );
          })}
        </div>
        
        <div className={cn("p-4 border-t border-border w-full flex flex-col gap-1", isIDE ? "items-center px-2" : "")}>
          <div title={isIDE ? "Settings" : undefined} className={cn("flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer rounded-lg hover:bg-secondary", isIDE ? "justify-center p-3" : "px-3 py-2")}>
            <Settings className={cn("w-5 h-5 flex-shrink-0", !isIDE && "mr-3 w-4 h-4")} />
            {!isIDE && "System Prefs"}
          </div>
          <div title={isIDE ? "Disconnect" : undefined} className={cn("flex items-center text-sm text-muted-foreground hover:text-destructive transition-colors cursor-pointer rounded-lg hover:bg-destructive/10", isIDE ? "justify-center p-3" : "px-3 py-2")}>
            <LogOut className={cn("w-5 h-5 flex-shrink-0", !isIDE && "mr-3 w-4 h-4")} />
            {!isIDE && "Disconnect"}
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className={cn("flex-1 min-h-screen relative flex flex-col transition-all duration-300", isIDE ? "ml-16" : "ml-64")}>
        <div className="absolute inset-0 pointer-events-none bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-10 mix-blend-overlay"></div>
        <div className="relative z-10 flex-1 flex flex-col h-full overflow-hidden">
          {children}
        </div>
      </main>
    </div>
  );
}
