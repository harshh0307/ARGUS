"use client";

import { useDetectionRuns } from "@/hooks/use-detection-runs";
import { useChangelogSearch } from "@/hooks/use-changelog-search";
import { useState } from "react";
import { SEVERITY_BG } from "@/lib/constants";
import { truncateHash, formatRelativeTime } from "@/lib/utils";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  RefreshCw,
  Search,
  AlertTriangle,
  PlusCircle,
  ArrowDownCircle,
  Copy,
} from "lucide-react";

export function WorkspaceLeft() {
  const { runs, selectedRun, setSelectedRun, refresh } = useDetectionRuns();
  const [searchQuery, setSearchQuery] = useState("");
  const { results: searchResults, isLoading: searchLoading } =
    useChangelogSearch(searchQuery);
  const [polling, setPolling] = useState(false);

  const handlePoll = async () => {
    setPolling(true);
    try {
      await api.triggerPoll();
      setTimeout(refresh, 2000);
    } finally {
      setPolling(false);
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "breaking":
        return <AlertTriangle className="h-3 w-3" />;
      case "additive":
        return <PlusCircle className="h-3 w-3" />;
      case "deprecation":
        return <ArrowDownCircle className="h-3 w-3" />;
      default:
        return null;
    }
  };

  return (
    <div className="flex flex-col h-full bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[var(--border)] space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">OpenAPI Semantic Diff &amp; Ingestion</h2>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-[10px] border-[var(--border)] bg-[var(--surface)]"
            onClick={handlePoll}
            disabled={polling}
          >
            <RefreshCw
              className={`h-3 w-3 mr-1 ${polling ? "animate-spin" : ""}`}
            />
            {polling ? "Polling..." : "Trigger Poll"}
          </Button>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--muted-foreground)]" />
          <Input
            placeholder="Semantic changelog search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-8 text-xs pl-7 bg-[var(--surface)] border-[var(--border)]"
          />
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        {searchQuery ? (
          <div className="p-3 space-y-2">
            {searchLoading && (
              <div className="text-xs text-[var(--muted-foreground)] text-center py-4">
                Searching...
              </div>
            )}
            {searchResults.map((hit) => (
              <div
                key={hit.id}
                className="bg-[var(--surface)] rounded p-2 border border-[var(--border)] text-xs space-y-1"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--semantic)]/10 text-[var(--semantic)] border border-[var(--semantic)]/30">
                    {hit.vendor_slug}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${
                      SEVERITY_BG[hit.kind.includes("removed") ? "breaking" : "additive"] ?? ""
                    }`}
                  >
                    {hit.kind}
                  </span>
                  <span className="text-[10px] text-[var(--semantic)] ml-auto font-mono">
                    {(hit.score * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="font-mono text-[10px] text-[var(--muted-foreground)]">
                  {hit.method.toUpperCase()} {hit.path}
                </div>
                {hit.detail && (
                  <div className="text-[10px] text-[var(--muted-foreground)]">
                    {hit.detail}
                  </div>
                )}
              </div>
            ))}
            {!searchLoading && searchResults.length === 0 && searchQuery.length > 2 && (
              <div className="text-xs text-[var(--muted-foreground)] text-center py-4">
                No results found
              </div>
            )}
          </div>
        ) : (
          <div className="p-3 space-y-2">
            {runs.length === 0 ? (
              <div className="text-xs text-[var(--muted-foreground)] text-center py-8">
                No detection runs yet. Click &quot;Trigger Poll&quot; to start.
              </div>
            ) : (
              runs.map((run) => (
                <button
                  key={run.id}
                  onClick={() => setSelectedRun(run)}
                  className={`w-full text-left bg-[var(--surface)] rounded p-2 border text-xs space-y-1 transition-colors ${
                    selectedRun?.id === run.id
                      ? "border-[var(--agent)] bg-[var(--agent)]/5"
                      : "border-[var(--border)] hover:border-[var(--muted-foreground)]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-[var(--muted-foreground)]">
                      Run #{run.id}
                    </span>
                    <span className="text-[10px] text-[var(--muted-foreground)]">
                      {formatRelativeTime(run.created_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--semantic)]/10 text-[var(--semantic)]">
                      {run.vendor_slug}
                    </span>
                    {run.breaking_count > 0 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--breaking)]/10 text-[var(--breaking)]">
                        {run.breaking_count} breaking
                      </span>
                    )}
                    {run.additive_count > 0 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--passed)]/10 text-[var(--passed)]">
                        {run.additive_count} additive
                      </span>
                    )}
                  </div>
                  {run.old_digest && run.new_digest && (
                    <div className="flex items-center gap-1 text-[10px] font-mono text-[var(--muted-foreground)]">
                      <span>{truncateHash(run.old_digest)}</span>
                      <span>&rarr;</span>
                      <span>{truncateHash(run.new_digest)}</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigator.clipboard.writeText(run.new_digest ?? "");
                        }}
                        className="ml-1 hover:text-[var(--foreground)]"
                      >
                        <Copy className="h-2.5 w-2.5" />
                      </button>
                    </div>
                  )}
                </button>
              ))
            )}
          </div>
        )}
      </ScrollArea>

      {/* Selected Run Changes */}
      {selectedRun && !searchQuery && (
        <div className="border-t border-[var(--border)] p-3 max-h-48 overflow-y-auto space-y-1.5">
          <h3 className="text-[10px] font-medium text-[var(--muted-foreground)] uppercase tracking-wider">
            Changes ({selectedRun.changes.length})
          </h3>
          {selectedRun.changes.length === 0 ? (
            <div className="text-[10px] text-[var(--muted-foreground)]">
              No changes detected
            </div>
          ) : (
            selectedRun.changes.map((change, i) => (
              <div
                key={i}
                className="flex items-center gap-2 text-[10px] py-1"
              >
                <span
                  className={`flex items-center gap-1 px-1.5 py-0.5 rounded border ${
                    SEVERITY_BG[change.severity] ?? ""
                  }`}
                >
                  {getSeverityIcon(change.severity)}
                  {change.severity}
                </span>
                <span className="font-mono text-[var(--muted-foreground)]">
                  {change.method.toUpperCase()} {change.path}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
