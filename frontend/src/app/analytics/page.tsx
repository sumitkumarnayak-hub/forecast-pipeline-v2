"use client";

import { Suspense } from "react";
import AppShell from "@/components/layout/AppShell";
import { UrlTabs } from "@/components/ui/UrlTabs";
import InsightsPanel from "@/components/analytics/InsightsPanel";
import ReportsPanel from "@/components/analytics/ReportsPanel";

function AnalyticsContent() {
  return (
    <AppShell title="Analytics" subtitle="Insights and reports">
      <UrlTabs
        defaultTab="insights"
        keepMounted={false}
        tabs={[
          { id: "insights", label: "Insights", content: <InsightsPanel /> },
          { id: "reports", label: "Reports", content: <ReportsPanel /> },
        ]}
      />
    </AppShell>
  );
}

export default function AnalyticsPage() {
  return (
    <Suspense>
      <AnalyticsContent />
    </Suspense>
  );
}
