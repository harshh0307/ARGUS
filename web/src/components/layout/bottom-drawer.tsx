"use client";

import { useState } from "react";
import { useRepositories } from "@/hooks/use-repositories";
import { api } from "@/lib/api";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import {
  GitPullRequest,
  Webhook,
  ChevronUp,
  ExternalLink,
  RotateCcw,
  Merge,
} from "lucide-react";

export function BottomDrawer() {
  const { repositories } = useRepositories();
  const [isOpen, setIsOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const activeRepos = repositories.filter((r) => r.is_active);

  const handleAction = async (action: string, fn: () => Promise<void>) => {
    setActionLoading(action);
    try {
      await fn();
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>
        <button className="fixed bottom-0 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-1.5 bg-[var(--card)] border border-[var(--border)] border-b-0 rounded-t-lg text-xs text-[var(--muted-foreground)] hover:bg-[var(--surface-hover)] transition-colors z-50">
          <Webhook className="h-3 w-3" />
          Webhook Log &amp; Actions
          <ChevronUp className="h-3 w-3" />
        </button>
      </SheetTrigger>
      <SheetContent
        side="bottom"
        className="bg-[var(--card)] border-[var(--border)] h-[40vh]"
      >
        <SheetTitle className="text-sm font-semibold mb-4">
          Self-Healing PR &amp; Webhook Center
        </SheetTitle>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 overflow-y-auto max-h-[calc(40vh-80px)]">
          {/* Webhook Event Log */}
          <div className="space-y-2">
            <h3 className="text-xs font-medium text-[var(--muted-foreground)]">
              Webhook Event Log
            </h3>
            <div className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)] font-mono text-xs space-y-1">
              <div className="text-[var(--muted-foreground)]">
                No recent webhook events
              </div>
              <div className="text-[10px] text-[var(--muted-foreground)]">
                Events will appear here when GitHub webhooks are received
              </div>
            </div>
          </div>

          {/* Active Repos & PR Card */}
          <div className="space-y-2">
            <h3 className="text-xs font-medium text-[var(--muted-foreground)]">
              Active Repositories
            </h3>
            {activeRepos.length === 0 ? (
              <div className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)] text-xs text-[var(--muted-foreground)]">
                No repositories registered
              </div>
            ) : (
              <div className="space-y-2">
                {activeRepos.slice(0, 3).map((repo) => (
                  <div
                    key={repo.id}
                    className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)]"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono">
                        {repo.owner}/{repo.name}
                      </span>
                      <span className="text-[10px] text-[var(--muted-foreground)]">
                        {repo.vendor_slug}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex gap-2 pt-2">
              <Button
                size="sm"
                variant="outline"
                className="text-[10px] h-7 border-[var(--border)] bg-[var(--surface)]"
                disabled={!activeRepos[0] || actionLoading === "view"}
                onClick={() =>
                  handleAction("view", async () => {
                    window.open(
                      `https://github.com/${activeRepos[0]?.owner}/${activeRepos[0]?.name}`,
                      "_blank"
                    );
                  })
                }
              >
                <ExternalLink className="h-3 w-3 mr-1" />
                View on GitHub
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-[10px] h-7 border-[var(--border)] bg-[var(--surface)]"
                disabled={!activeRepos[0] || actionLoading === "rerun"}
                onClick={() =>
                  handleAction("rerun", async () => {
                    if (activeRepos[0]) {
                      await api.triggerRerun(activeRepos[0].id);
                    }
                  })
                }
              >
                <RotateCcw className="h-3 w-3 mr-1" />
                {actionLoading === "rerun" ? "Running..." : "Re-run Agent"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-[10px] h-7 border-[var(--border)] bg-[var(--surface)]"
                disabled
              >
                <Merge className="h-3 w-3 mr-1" />
                Squash &amp; Merge
              </Button>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
