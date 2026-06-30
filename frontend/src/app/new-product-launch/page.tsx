"use client";

import { Suspense } from "react";
import AppShell from "@/components/layout/AppShell";
import { UrlTabs } from "@/components/ui/UrlTabs";
import { NplProvider } from "@/context/NplContext";
import NplWizard from "@/components/npl/NplWizard";
import SubmissionHistory from "@/components/npl/SubmissionHistory";
import SyncPhTab from "@/components/npl/SyncPhTab";
import AutoSyncTab from "@/components/npl/AutoSyncTab";

function NewProductLaunchContent() {
  return (
    <AppShell title="Product Launch" subtitle="Launch planning, P-H sync, and automated new-product integration">
      <UrlTabs
        defaultTab="launch"
        keepMounted={false}
        tabs={[
          {
            id: "launch",
            label: "Launch Planning",
            content: (
              <NplProvider>
                <UrlTabs
                  param="type"
                  defaultTab="type1"
                  keepMounted={false}
                  tabs={[
                  {
                    id: "type1",
                    label: "New Product Launch",
                    content: (
                      <NplWizard
                        subType="New Launch"
                        title="New Product Launch"
                        description="4-stage wizard — category, template, hub split, launch date, submit to Launch_Output."
                      />
                    ),
                  },
                  {
                    id: "type2",
                    label: "Product Expansion",
                    content: (
                      <NplWizard
                        subType="Expansion"
                        title="Product Expansion"
                        description="Existing SKU expanding to new cities — same 4-stage flow with Expansion submission type."
                      />
                    ),
                  },
                  {
                    id: "type3",
                    label: "Product Replacement",
                    content: (
                      <NplWizard
                        subType="Replacement"
                        title="Product Replacement"
                        description="Replace old SKU with new — upload hub-level plan and submit as Replacement."
                      />
                    ),
                  },
                  { id: "history", label: "Submission History", content: <SubmissionHistory /> },
                ]}
                />
              </NplProvider>
            ),
          },
          { id: "sync-ph", label: "Sync to P-H Master", content: <SyncPhTab /> },
          { id: "auto-sync", label: "Auto Sync", content: <AutoSyncTab /> },
        ]}
      />
    </AppShell>
  );
}

export default function NewProductLaunchPage() {
  return (
    <Suspense>
      <NewProductLaunchContent />
    </Suspense>
  );
}
