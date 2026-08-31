"use client";

import { useHealth } from "@/hooks/use-health";
import { useVendors } from "@/hooks/use-vendors";
import { useTheme } from "next-themes";
import { Sun, Moon, Activity, Zap } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function Header() {
  const { data: health } = useHealth();
  const { vendors, selectedVendor, setSelectedVendor } = useVendors();
  const { theme, setTheme } = useTheme();

  const isHealthy = health?.status === "ok";
  const dbOk = health?.database ?? false;

  return (
    <header className="h-14 border-b border-[var(--border)] bg-[var(--card)] flex items-center px-4 gap-4 shrink-0">
      {/* Left: Logo + Status */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-[var(--agent)]" />
          <span className="font-bold text-sm tracking-tight">ARGUS</span>
        </div>
        <span className="text-xs text-[var(--muted-foreground)] hidden md:block">
          The changelog that reads your codebase
        </span>
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
          <span className="text-[10px] text-[var(--muted-foreground)] hidden lg:block">
            Celery Beat Active &bull; Redis Connected &bull; AWS ECS
          </span>
        </div>
      </div>

      {/* Center: Vendor Selector */}
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

      {/* Right: Provider Pill + Theme Toggle */}
      <div className="flex items-center gap-3">
        <div className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--surface)] border border-[var(--border)] text-[10px] text-[var(--muted-foreground)]">
          <Activity className="h-3 w-3 text-[var(--passed)]" />
          <span>Primary: OpenAI / Gemini | Fallback: OpenRouter Nemotron-3 (Ready)</span>
        </div>
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-2 rounded-md hover:bg-[var(--surface-hover)] transition-colors"
        >
          {theme === "dark" ? (
            <Sun className="h-4 w-4 text-[var(--muted-foreground)]" />
          ) : (
            <Moon className="h-4 w-4 text-[var(--muted-foreground)]" />
          )}
        </button>
      </div>
    </header>
  );
}
