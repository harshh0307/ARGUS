"use client";

import { Header } from "@/components/layout/header";
import { BottomDrawer } from "@/components/layout/bottom-drawer";
import { AnalyticsGrid } from "@/components/dashboard/analytics-grid";
import { Workspace } from "@/components/dashboard/workspace";

export default function DashboardPage() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header />
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        <AnalyticsGrid />
        <Workspace />
      </main>
      <BottomDrawer />
    </div>
  );
}
