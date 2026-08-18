"use client";
import { Suspense } from "react";
import AppShell from "@/components/layout/AppShell";
import BaseSheetsSection from "@/components/master-data/BaseSheetsSection";

import FestiveUploadSection from "@/components/master-data/FestiveUploadSection";

export default function MasterDataPage() {
  return (
    <Suspense>
      <MasterDataPageInner />
    </Suspense>
  );
}

function MasterDataPageInner() {
  return (
    <AppShell
      title="Master Data"
      subtitle="Sync Google Sheets to Google Drive as parquet files"
    >
      <BaseSheetsSection />
      <FestiveUploadSection />
    </AppShell>
  );
}
