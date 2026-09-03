"use client";

import { useState } from "react";
import { useRepositories } from "@/hooks/use-repositories";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StaggerContainer, StaggerItem } from "@/components/ui/motion";
import { formatRelativeTime } from "@/lib/utils";
import { AddRepoModal } from "@/components/dashboard/add-repo-modal";
import {
  Webhook,
  ChevronUp,
  ExternalLink,
  GitPullRequest,
  Play,
} from "lucide-react";

export function BottomDrawer() {
  const { repositories, refresh } = useRepositories();
  const [isOpen, setIsOpen] = useState(false);
  const [scanning, setScanning] = useState<number | null>(null);

  const activeRepos = repositories.filter((r) => r.is_active);

  const handleScan = async (repoId: number) => {
    setScanning(repoId);
    try {
      await api.triggerPipeline(repoId, true);
      toast.success("Pipeline triggered");
    } catch (err) {
      toast.error("Failed to trigger pipeline", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setScanning(null);
    }
  };

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>
        <button className="fixed bottom-0 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-1.5 bg-[var(--card)] border border-[var(--border)] border-b-0 rounded-t-lg text-xs text-[var(--muted-foreground)] hover:bg-[var(--surface-hover)] transition-colors z-50">
          <Webhook className="h-3 w-3" />
          Repositories ({activeRepos.length})
          <ChevronUp className="h-3 w-3" />
        </button>
      </SheetTrigger>
      <SheetContent
        side="bottom"
        className="bg-[var(--card)] border-[var(--border)] h-[40vh]"
      >
        <div className="flex items-center justify-between mb-4">
          <SheetTitle className="text-sm font-semibold">
            Monitored Repositories
          </SheetTitle>
          <AddRepoModal onRepoAdded={refresh} />
        </div>

        <div className="overflow-y-auto max-h-[calc(40vh-80px)]">
          {activeRepos.length === 0 ? (
            <div className="bg-[var(--surface)] rounded-lg p-6 border border-[var(--border)] text-center space-y-2">
              <GitPullRequest className="h-8 w-8 mx-auto text-[var(--muted-foreground)] opacity-50" />
              <div className="text-xs text-[var(--muted-foreground)]">
                No repositories registered yet
              </div>
              <div className="text-[10px] text-[var(--muted-foreground)]">
                Click &quot;Add Repository&quot; to get started
              </div>
            </div>
          ) : (
            <StaggerContainer staggerDelay={0.06} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {activeRepos.map((repo) => (
                <StaggerItem key={repo.id}>
                  <div className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)] space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-medium truncate">
                        {repo.owner}/{repo.name}
                      </span>
                      <Badge variant="outline" className="text-[9px] shrink-0">
                        {repo.vendor_slug}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-[var(--muted-foreground)]">
                      <span>
                        {repo.last_run_at
                          ? `Last scan: ${formatRelativeTime(repo.last_run_at)}`
                          : "Never scanned"}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleScan(repo.id)}
                          disabled={scanning === repo.id}
                          className="flex items-center gap-1 text-[var(--agent)] hover:text-[var(--agent)]/80 transition-colors disabled:opacity-50"
                          title="Trigger scan"
                        >
                          <Play className="h-2.5 w-2.5" />
                          {scanning === repo.id ? "..." : "Scan"}
                        </button>
                        <a
                          href={`https://github.com/${repo.owner}/${repo.name}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 hover:text-[var(--foreground)] transition-colors"
                        >
                          <ExternalLink className="h-2.5 w-2.5" />
                        </a>
                      </div>
                    </div>
                  </div>
                </StaggerItem>
              ))}
            </StaggerContainer>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
