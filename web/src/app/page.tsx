"use client";

import { Header } from "@/components/layout/header";
import { BottomDrawer } from "@/components/layout/bottom-drawer";
import { AnalyticsGrid } from "@/components/dashboard/analytics-grid";
import { Workspace } from "@/components/dashboard/workspace";
import { FadeIn } from "@/components/ui/motion";

export default function DashboardPage() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header />
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        <FadeIn delay={0}>
          <AnalyticsGrid />
        </FadeIn>
        <FadeIn delay={0.1}>
          <Workspace />
        </FadeIn>
      </main>
      <BottomDrawer />
    </div>
  );
}
