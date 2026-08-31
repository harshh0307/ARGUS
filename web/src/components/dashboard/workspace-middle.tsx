"use client";

import { useState } from "react";
import { useDetectionRuns } from "@/hooks/use-detection-runs";
import { LANGUAGES } from "@/lib/constants";
import { SEVERITY_BG } from "@/lib/constants";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Toggle } from "@/components/ui/toggle";
import { FileCode, FolderOpen } from "lucide-react";

export function WorkspaceMiddle() {
  const { selectedRun } = useDetectionRuns();
  const [activeLanguages, setActiveLanguages] = useState<string[]>(
    LANGUAGES.map((l) => l.id)
  );
  const [selectedChange, setSelectedChange] = useState<number | null>(null);

  const changes = selectedRun?.changes ?? [];
  const breakingChanges = changes.filter((c) => c.severity === "breaking");
  const additiveChanges = changes.filter((c) => c.severity !== "breaking");

  const toggleLanguage = (id: string) => {
    setActiveLanguages((prev) =>
      prev.includes(id) ? prev.filter((l) => l !== id) : [...prev, id]
    );
  };

  return (
    <div className="flex flex-col h-full bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold mb-3">
          AST Multi-Language Impact Scanner
        </h2>
        <div className="flex flex-wrap gap-1">
          {LANGUAGES.map((lang) => (
            <Toggle
              key={lang.id}
              size="sm"
              pressed={activeLanguages.includes(lang.id)}
              onPressedChange={() => toggleLanguage(lang.id)}
              className="h-6 text-[10px] px-2 data-[state=on]:bg-[var(--agent)]/20 data-[state=on]:text-[var(--agent)] data-[state=on]:border-[var(--agent)]/30 border border-[var(--border)] bg-[var(--surface)]"
            >
              <span className="mr-1">{lang.icon}</span>
              {lang.label}
            </Toggle>
          ))}
        </div>
      </div>

      {/* Content: File Tree + Code View */}
      <div className="flex flex-1 overflow-hidden">
        {/* File Tree */}
        <div className="w-1/3 border-r border-[var(--border)] overflow-y-auto p-3 space-y-1">
          <h3 className="text-[10px] font-medium text-[var(--muted-foreground)] uppercase tracking-wider mb-2">
            Impacted Files
          </h3>
          {changes.length === 0 ? (
            <div className="text-[10px] text-[var(--muted-foreground)] py-4 text-center">
              Select a detection run to view impacts
            </div>
          ) : (
            <>
              {breakingChanges.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[10px] text-[var(--breaking)] font-medium">
                    Breaking Changes
                  </div>
                  {breakingChanges.map((change, i) => (
                    <button
                      key={i}
                      onClick={() => setSelectedChange(i)}
                      className={`w-full text-left flex items-center gap-2 text-[10px] py-1.5 px-2 rounded transition-colors ${
                        selectedChange === i
                          ? "bg-[var(--breaking)]/10 text-[var(--breaking)]"
                          : "text-[var(--muted-foreground)] hover:bg-[var(--surface-hover)]"
                      }`}
                    >
                      <FileCode className="h-3 w-3 shrink-0" />
                      <span className="font-mono truncate">
                        {change.method.toUpperCase()} {change.path}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {additiveChanges.length > 0 && (
                <div className="space-y-1 mt-2">
                  <div className="text-[10px] text-[var(--passed)] font-medium">
                    Additive Changes
                  </div>
                  {additiveChanges.map((change, i) => (
                    <button
                      key={i}
                      onClick={() => setSelectedChange(breakingChanges.length + i)}
                      className={`w-full text-left flex items-center gap-2 text-[10px] py-1.5 px-2 rounded transition-colors ${
                        selectedChange === breakingChanges.length + i
                          ? "bg-[var(--passed)]/10 text-[var(--passed)]"
                          : "text-[var(--muted-foreground)] hover:bg-[var(--surface-hover)]"
                      }`}
                    >
                      <FolderOpen className="h-3 w-3 shrink-0" />
                      <span className="font-mono truncate">
                        {change.method.toUpperCase()} {change.path}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Code View */}
        <div className="flex-1 overflow-y-auto p-4">
          {selectedChange !== null && changes[selectedChange] ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span
                  className={`text-[10px] px-2 py-0.5 rounded border ${
                    SEVERITY_BG[changes[selectedChange].severity] ?? ""
                  }`}
                >
                  {changes[selectedChange].severity.toUpperCase()}
                </span>
                <span className="text-xs font-mono">
                  {changes[selectedChange].method.toUpperCase()}{" "}
                  {changes[selectedChange].path}
                </span>
              </div>
              <div className="bg-[var(--surface)] rounded-lg p-4 border border-[var(--border)]">
                <p className="text-xs text-[var(--muted-foreground)]">
                  {changes[selectedChange].detail}
                </p>
                {changes[selectedChange].schema_path && (
                  <div className="mt-2 text-[10px] font-mono text-[var(--semantic)]">
                    Schema: {changes[selectedChange].schema_path}
                  </div>
                )}
                {changes[selectedChange].old_value !== undefined && changes[selectedChange].old_value !== null && (
                  <div className="mt-2 text-[10px] font-mono text-[var(--breaking)]">
                    Old: {JSON.stringify(changes[selectedChange].old_value)}
                  </div>
                )}
                {changes[selectedChange].new_value !== undefined && changes[selectedChange].new_value !== null && (
                  <div className="mt-1 text-[10px] font-mono text-[var(--passed)]">
                    New: {JSON.stringify(changes[selectedChange].new_value)}
                  </div>
                )}
              </div>
              <div className="bg-black/30 rounded-lg p-4 font-mono text-xs text-[var(--muted-foreground)]">
                <div className="text-[10px] text-[var(--agent)] mb-2">
                  // Code with affected call site
                </div>
                <div className="space-y-0.5">
                  <div>
                    <span className="text-[var(--muted-foreground)]">1:</span>{" "}
                    <span className="text-[var(--semantic)]">
                      {changes[selectedChange].method.toUpperCase()}(
                    </span>
                  </div>
                  <div>
                    <span className="text-[var(--muted-foreground)]">2:</span>{" "}
                    <span className="text-[var(--semantic)]">
                      &quot;{changes[selectedChange].path}&quot;
                    </span>
                    <span className="text-[var(--muted-foreground)]">,</span>
                  </div>
                  <div>
                    <span className="text-[var(--muted-foreground)]">3:</span>{" "}
                    <span className="text-[var(--muted-foreground)]">{"// ..."}</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-xs text-[var(--muted-foreground)]">
              Select a change to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
