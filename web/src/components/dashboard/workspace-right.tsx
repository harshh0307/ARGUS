"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Label } from "@/components/ui/label";
import { StaggerContainer, StaggerItem } from "@/components/ui/motion";
import { useActivity } from "@/hooks/use-activity";
import { useHealth } from "@/hooks/use-health";
import { useDetectionRuns } from "@/hooks/use-detection-runs";
import { formatRelativeTime } from "@/lib/utils";
import { PipelinePanel } from "./pipeline-panel";
import {
  Activity,
  Check,
  AlertCircle,
  Clock,
  GitPullRequest,
  Zap,
  Server,
} from "lucide-react";

const STATUS_CONFIG: Record<string, { color: string; icon: typeof Check; label: string }> = {
  success: { color: "text-[var(--passed)]", icon: Check, label: "Complete" },
  failed: { color: "text-[var(--breaking)]", icon: AlertCircle, label: "Failed" },
  running: { color: "text-[var(--agent)]", icon: Clock, label: "Running" },
  idle: { color: "text-[var(--muted-foreground)]", icon: Clock, label: "Idle" },
};

export function WorkspaceRight() {
  const { events, pipelineStatus, isLoading } = useActivity();
  const { data: health } = useHealth();
  const { runs } = useDetectionRuns();

  const statusInfo = STATUS_CONFIG[pipelineStatus] ?? STATUS_CONFIG.idle;
  const StatusIcon = statusInfo.icon;

  const todayRuns = runs.filter((r) => {
    const d = new Date(r.created_at);
    const now = new Date();
    return d.toDateString() === now.toDateString();
  });
  const todayBreaking = todayRuns.reduce((s, r) => s + r.breaking_count, 0);
  const todayAdditive = todayRuns.reduce((s, r) => s + r.additive_count, 0);

  return (
    <div className="flex flex-col h-full bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[var(--border)]">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Agent Status</h2>
          <Badge variant="outline" className="text-[9px]">
            <StatusIcon className={`h-2.5 w-2.5 mr-1 ${statusInfo.color}`} />
            {statusInfo.label}
          </Badge>
        </div>
      </div>

      <ScrollArea className="flex-1 p-4 space-y-6">
        {/* System Status */}
        <div className="space-y-3">
          <Label className="text-[10px] font-medium text-[var(--muted-foreground)] uppercase tracking-wider">
            System
          </Label>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)]">
              <div className="flex items-center gap-2 mb-1">
                <Server className="h-3 w-3 text-[var(--muted-foreground)]" />
                <span className="text-[10px] text-[var(--muted-foreground)]">API</span>
              </div>
              <div className={`text-xs font-medium ${health?.status === "ok" ? "text-[var(--passed)]" : "text-[var(--breaking)]"}`}>
                {health?.status === "ok" ? "Healthy" : "Down"}
              </div>
            </div>
            <div className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)]">
              <div className="flex items-center gap-2 mb-1">
                <Zap className="h-3 w-3 text-[var(--muted-foreground)]" />
                <span className="text-[10px] text-[var(--muted-foreground)]">DB</span>
              </div>
              <div className={`text-xs font-medium ${health?.database ? "text-[var(--passed)]" : "text-amber-400"}`}>
                {health?.database ? "Connected" : "Not set"}
              </div>
            </div>
          </div>
        </div>

        <Separator />

        {/* Today's Activity */}
        <div className="space-y-3">
          <Label className="text-[10px] font-medium text-[var(--muted-foreground)] uppercase tracking-wider">
            Today&apos;s Activity
          </Label>
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)] text-center">
              <div className="text-2xl font-bold text-[var(--agent)]">{todayRuns.length}</div>
              <div className="text-[10px] text-[var(--muted-foreground)]">Runs</div>
            </div>
            <div className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)] text-center">
              <div className="text-2xl font-bold text-[var(--breaking)]">{todayBreaking}</div>
              <div className="text-[10px] text-[var(--muted-foreground)]">Breaking</div>
            </div>
            <div className="bg-[var(--surface)] rounded-lg p-3 border border-[var(--border)] text-center">
              <div className="text-2xl font-bold text-[var(--passed)]">{todayAdditive}</div>
              <div className="text-[10px] text-[var(--muted-foreground)]">Additive</div>
            </div>
          </div>
        </div>

        <Separator />

        {/* Pipeline Runs */}
        <PipelinePanel />

        <Separator />

        {/* Activity Feed */}
        <div className="space-y-1">
          <Label className="text-[10px] font-medium text-[var(--muted-foreground)] uppercase tracking-wider mb-3 block">
            Recent Activity
          </Label>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-12 bg-[var(--surface)] rounded animate-pulse" />
              ))}
            </div>
          ) : events.length === 0 ? (
            <div className="text-xs text-[var(--muted-foreground)] text-center py-8">
              No activity yet. Argus will detect changes automatically.
            </div>
          ) : (
            <StaggerContainer staggerDelay={0.04}>
              {events.slice(0, 10).map((event, i) => (
                <StaggerItem key={i}>
                  <div className="flex items-start gap-3 py-2 px-2 rounded hover:bg-[var(--surface-hover)]">
                    <div className="mt-0.5">
                      {event.kind === "detection" ? (
                        <Activity className="h-3.5 w-3.5 text-[var(--agent)]" />
                      ) : (
                        <GitPullRequest className="h-3.5 w-3.5 text-[var(--semantic)]" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium truncate">{event.title}</div>
                      {event.detail && (
                        <div className="text-[10px] text-[var(--muted-foreground)] truncate">
                          {event.detail}
                        </div>
                      )}
                      <div className="text-[10px] text-[var(--muted-foreground)]">
                        {formatRelativeTime(event.timestamp)}
                      </div>
                    </div>
                    {event.status && (
                      <Badge variant="outline" className={`text-[8px] shrink-0 ${
                        event.status === "breaking" ? "text-[var(--breaking)]" :
                        event.status === "success" ? "text-[var(--passed)]" :
                        event.status === "failed" ? "text-[var(--breaking)]" :
                        "text-[var(--muted-foreground)]"
                      }`}>
                        {event.status}
                      </Badge>
                    )}
                  </div>
                </StaggerItem>
              ))}
            </StaggerContainer>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
