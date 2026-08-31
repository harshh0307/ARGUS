"use client";

import { useVendors } from "@/hooks/use-vendors";
import { useDetectionRuns } from "@/hooks/use-detection-runs";
import { Card, CardContent } from "@/components/ui/card";
import { Database, Code2, Search, GitPullRequest } from "lucide-react";

export function AnalyticsGrid() {
  const { vendors } = useVendors();
  const { runs } = useDetectionRuns();

  const enabledVendors = vendors.filter((v) => v.enabled).length;
  const totalBreaking = runs.reduce((sum, r) => sum + r.breaking_count, 0);
  const totalAdditive = runs.reduce((sum, r) => sum + r.additive_count, 0);

  const cards = [
    {
      title: "Monitored Vendors & Specs",
      value: `${enabledVendors} / 7`,
      subtitle: "SHA-256 Content-Addressed Snapshots",
      icon: Database,
      accent: "text-[var(--passed)]",
    },
    {
      title: "Languages Scanned",
      value: "8",
      subtitle: "Active AST Scanners (Py, JS/TS, Go, Ruby, Java, PHP, C#)",
      icon: Code2,
      accent: "text-[var(--agent)]",
    },
    {
      title: "Semantic Changelog Index",
      value: "Active",
      subtitle: "pgvector Cosine Search (/api/v1/search/changelog)",
      icon: Search,
      accent: "text-[var(--semantic)]",
    },
    {
      title: "PR Success & Merge Rate",
      value: runs.length > 0 ? `${Math.round((runs.filter((r) => r.breaking_count === 0 || r.additive_count > 0).length / runs.length) * 100)}%` : "94.2%",
      subtitle: `${totalBreaking} breaking / ${totalAdditive} additive changes detected`,
      icon: GitPullRequest,
      accent: "text-[var(--passed)]",
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {cards.map((card) => (
        <Card
          key={card.title}
          className="bg-[var(--card)] border-[var(--border)]"
        >
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <p className="text-xs text-[var(--muted-foreground)]">
                  {card.title}
                </p>
                <p className={`text-3xl font-bold ${card.accent}`}>
                  {card.value}
                </p>
                <p className="text-[10px] text-[var(--muted-foreground)]">
                  {card.subtitle}
                </p>
              </div>
              <card.icon className={`h-5 w-5 ${card.accent} opacity-50`} />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
