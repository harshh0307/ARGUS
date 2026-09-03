"use client";

import { useHealth } from "@/hooks/use-health";
import { useVendors } from "@/hooks/use-vendors";
import { useAuth } from "@/providers/auth-provider";
import { useTheme } from "next-themes";
import { motion } from "@/components/ui/motion";
import { Sun, Moon, Activity, Zap, LayoutDashboard, Store, LogOut, User } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface HeaderProps {
  activeTab?: "dashboard" | "vendors";
  onTabChange?: (tab: "dashboard" | "vendors") => void;
}

export function Header({ activeTab = "dashboard", onTabChange }: HeaderProps) {
  const { data: health } = useHealth();
  const { vendors, selectedVendor, setSelectedVendor } = useVendors();
  const { theme, setTheme } = useTheme();
  const { user, logout } = useAuth();

  const isHealthy = health?.status === "ok";
  const dbOk = health?.database ?? false;

  return (
    <header className="h-14 border-b border-[var(--border)] bg-[var(--card)] flex items-center px-4 gap-4 shrink-0">
      {/* Left: Logo + Nav Tabs */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-[var(--agent)]" />
          <span className="font-bold text-sm tracking-tight">ARGUS</span>
        </div>
        <nav className="flex items-center gap-1 ml-2">
          <button
            onClick={() => onTabChange?.("dashboard")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs transition-colors ${
              activeTab === "dashboard"
                ? "bg-[var(--agent)]/10 text-[var(--agent)]"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--surface)]"
            }`}
          >
            <LayoutDashboard className="h-3.5 w-3.5" />
            Dashboard
          </button>
          <button
            onClick={() => onTabChange?.("vendors")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs transition-colors ${
              activeTab === "vendors"
                ? "bg-[var(--agent)]/10 text-[var(--agent)]"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--surface)]"
            }`}
          >
            <Store className="h-3.5 w-3.5" />
            Vendors
          </button>
        </nav>
        <div className="flex items-center gap-1.5 ml-2">
          <div
            className={`w-2 h-2 rounded-full animate-pulse-dot ${
              isHealthy && dbOk
                ? "bg-[var(--passed)]"
                : isHealthy
                  ? "bg-amber-400"
                  : "bg-[var(--breaking)]"
            }`}
          />
        </div>
      </div>

      {/* Center: Vendor Selector (only on dashboard) */}
      {activeTab === "dashboard" && (
        <div className="flex-1 flex justify-center">
          <Select
            value={selectedVendor ?? "all"}
            onValueChange={(v) => setSelectedVendor(v === "all" ? null : v)}
          >
            <SelectTrigger className="w-48 h-8 text-xs bg-[var(--surface)] border-[var(--border)]">
              <SelectValue placeholder="All Vendors" />
            </SelectTrigger>
            <SelectContent className="bg-[var(--card)] border-[var(--border)]">
              <SelectItem value="all">All Vendors</SelectItem>
              {vendors.map((v) => (
                <SelectItem key={v.slug} value={v.slug}>
                  {v.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Right: User Info + Theme Toggle */}
      <div className="flex items-center gap-3 ml-auto">
        {user && (
          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--surface)] border border-[var(--border)] text-[10px] text-[var(--muted-foreground)]">
              <User className="h-3 w-3" />
              <span>{user.email}</span>
              {user.is_admin && (
                <span className="ml-1 rounded bg-[var(--agent)]/20 px-1 py-0.5 text-[var(--agent)]">
                  admin
                </span>
              )}
            </div>
            <button
              onClick={logout}
              className="p-2 rounded-md hover:bg-[var(--surface-hover)] transition-colors"
              title="Sign out"
            >
              <LogOut className="h-4 w-4 text-[var(--muted-foreground)]" />
            </button>
          </div>
        )}
        <motion.button
          whileTap={{ rotate: 180, scale: 0.9 }}
          transition={{ duration: 0.3 }}
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-2 rounded-md hover:bg-[var(--surface-hover)] transition-colors"
        >
          {theme === "dark" ? (
            <Sun className="h-4 w-4 text-[var(--muted-foreground)]" />
          ) : (
            <Moon className="h-4 w-4 text-[var(--muted-foreground)]" />
          )}
        </motion.button>
      </div>
    </header>
  );
}
