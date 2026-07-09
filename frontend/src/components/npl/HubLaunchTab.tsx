"use client";

import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { RefreshCw, CheckCircle2, XCircle, Info, Landmark, Eye } from "lucide-react";

interface PreviewData {
  success: boolean;
  validation_errors: string[];
  rows_to_add: Record<string, any>[];
  ph_headers: string[];
  duplicates_skipped: number;
  mapping_report: Array<{
    new_hub: string;
    source_hub: string;
    status: string;
    rows_inserted?: number;
    duplicates_skipped?: number;
    message?: string;
  }>;
  total_to_insert: number;
}

export default function HubLaunchTab() {
  const { canWrite } = useAuth();
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [step, setStep] = useState<"idle" | "preview" | "success">("idle");
  const [syncedCount, setSyncedCount] = useState(0);

  const fetchPreview = async () => {
    setRunning(true);
    setMsg({ text: "", type: "" });
    setPreview(null);
    try {
      const { data } = await api.get("/api/new-product-launch/sync-new-hub/preview");
      setPreview(data);
      setStep("preview");
      if (data.validation_errors && data.validation_errors.length > 0) {
        setMsg({
          text: `Found ${data.validation_errors.length} Hub Mapping configuration issue(s). Resolve them in Google Sheets and refresh.`,
          type: "warning",
        });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Failed to load sync preview.", type: "danger" });
    } finally {
      setRunning(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setRunning(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/new-product-launch/sync-new-hub/confirm", {
        rows_to_add: preview.rows_to_add,
        ph_headers: preview.ph_headers,
      });
      setSyncedCount(data.rows_inserted);
      setStep("success");
      setMsg({ text: data.detail || "New Hub settings successfully synced.", type: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Sync confirmation failed", type: "danger" });
    } finally {
      setRunning(false);
    }
  };

  const resetFlow = () => {
    setPreview(null);
    setStep("idle");
    setMsg({ text: "", type: "" });
  };

  return (
    <div className="w-full max-w-5xl space-y-6 text-slate-800">
      {/* Dynamic Header Info Card */}
      <div className="flex gap-4 p-5 bg-white border border-slate-100 rounded-2xl shadow-sm leading-relaxed">
        <Info className="w-5 h-5 text-blue-500 shrink-0 mt-0.5" />
        <div className="text-sm text-slate-600">
          <strong className="text-slate-900 block font-semibold mb-1">New Hub Launch Sync (FF Input Parameter Drive)</strong>
          Reads target mapping pairs directly from the <span className="font-semibold text-slate-800">FF Input</span> tab of the New Hub Launch spreadsheet. 
          It auto-generates cloned product forecast configurations from reference source hubs to target hubs inside the <span className="font-semibold text-slate-800">P-H Master</span> sheet.
        </div>
      </div>

      {/* Message Notifications */}
      {msg.text && (
        <div className={`p-4 rounded-xl border flex items-start gap-3 text-sm ${
          msg.type === "success" ? "bg-emerald-50 border-emerald-100 text-emerald-800" :
          msg.type === "warning" ? "bg-amber-50 border-amber-100 text-amber-800" :
          "bg-red-50 border-red-100 text-red-800"
        }`}>
          {msg.type === "success" ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          ) : (
            <XCircle className="w-5 h-5 shrink-0 text-amber-600" />
          )}
          <span>{msg.text}</span>
        </div>
      )}

      {/* STEP 1: Idle (Trigger Preview Load) */}
      {step === "idle" && (
        <div className="bg-white border border-slate-200/80 rounded-2xl p-8 text-center space-y-4">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-blue-50 text-blue-600 mb-2">
            <Landmark className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-slate-800">Review Launch Parameters</h3>
          <p className="text-sm text-slate-500 max-w-lg mx-auto">
            Loads pending launch hub settings from the configuration sheet, runs validations, and outputs skipped/new records before merging.
          </p>
          <button
            onClick={fetchPreview}
            disabled={running}
            className="inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium text-sm px-6 py-2.5 rounded-xl transition-all shadow-sm"
          >
            {running ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Reading Sheets...
              </>
            ) : (
              <>
                <Eye className="w-4 h-4" />
                Fetch & Preview Sync Mappings
              </>
            )}
          </button>
        </div>
      )}

      {/* STEP 2: Preview Results Grid */}
      {step === "preview" && preview && (
        <div className="space-y-6">
          {/* Summary KPI Widgets */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white border border-slate-200/60 rounded-xl p-5 shadow-sm text-center">
              <div className="text-3xl font-bold text-blue-600">{preview.total_to_insert}</div>
              <div className="text-xs font-medium text-slate-500 mt-1 uppercase tracking-wider">Rows to Sync</div>
            </div>
            <div className="bg-white border border-slate-200/60 rounded-xl p-5 shadow-sm text-center">
              <div className="text-3xl font-bold text-slate-600">{preview.duplicates_skipped}</div>
              <div className="text-xs font-medium text-slate-500 mt-1 uppercase tracking-wider">Duplicates Skipped</div>
            </div>
            <div className="bg-white border border-slate-200/60 rounded-xl p-5 shadow-sm text-center">
              <div className="text-3xl font-bold text-purple-600">{preview.mapping_report.length}</div>
              <div className="text-xs font-medium text-slate-500 mt-1 uppercase tracking-wider">Mappings Found</div>
            </div>
          </div>

          {/* Validation Warnings Panel */}
          {preview.validation_errors.length > 0 && (
            <div className="bg-red-50/50 border border-red-100 rounded-xl p-5 space-y-2">
              <h4 className="text-sm font-semibold text-red-900 flex items-center gap-1.5">
                <XCircle className="w-4 h-4 text-red-600" /> Validation Failures in Hub Mapping
              </h4>
              <ul className="list-disc pl-5 text-xs text-red-700 space-y-1">
                {preview.validation_errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Mapping Report Table */}
          <div className="bg-white border border-slate-200/60 rounded-2xl overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
              <h4 className="text-sm font-semibold text-slate-800">Launch Configuration Sync Report</h4>
            </div>
            <div className="overflow-x-auto max-h-[300px]">
              <table className="w-full text-left border-collapse text-xs">
                <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-100">
                  <tr>
                    <th className="px-6 py-3">New Hub</th>
                    <th className="px-6 py-3">Source Hub</th>
                    <th className="px-6 py-3">Status</th>
                    <th className="px-6 py-3 text-right">Rows Added</th>
                    <th className="px-6 py-3 text-right">Skipped</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {preview.mapping_report.map((rep, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/50">
                      <td className="px-6 py-3.5 font-medium text-slate-900">{rep.new_hub}</td>
                      <td className="px-6 py-3.5">{rep.source_hub}</td>
                      <td className="px-6 py-3.5">
                        {rep.status === "ok" ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-100">
                            Valid
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-red-50 text-red-700 border border-red-100">
                            Missing Row
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-3.5 text-right font-medium text-slate-900">{rep.rows_inserted ?? 0}</td>
                      <td className="px-6 py-3.5 text-right text-slate-400">{rep.duplicates_skipped ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center justify-between pt-2">
            <button
              onClick={resetFlow}
              className="px-5 py-2.5 border border-slate-200 hover:bg-slate-50 text-slate-600 text-sm font-medium rounded-xl transition-colors"
            >
              Reset Configuration
            </button>
            <button
              onClick={handleConfirm}
              disabled={running || preview.rows_to_add.length === 0 || !canWrite}
              className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium text-sm px-6 py-2.5 rounded-xl transition-all shadow-sm cursor-pointer"
            >
              {running ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Syncing to P-H Master...
                </>
              ) : (
                <>
                  <Landmark className="w-4 h-4" />
                  Confirm & Sync Hubs
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: Success Screen */}
      {step === "success" && (
        <div className="bg-white border border-emerald-100 rounded-2xl p-8 text-center space-y-4">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 mb-2">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-slate-800">Sync Successful</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto">
            Successfully synced <span className="font-semibold text-slate-800">{syncedCount}</span> product-hub forecast configurations into target master tables.
          </p>
          <button
            onClick={resetFlow}
            className="inline-flex items-center justify-center bg-slate-900 hover:bg-slate-800 text-white font-medium text-sm px-6 py-2.5 rounded-xl transition-all shadow-sm cursor-pointer"
          >
            Start New Run
          </button>
        </div>
      )}
    </div>
  );
}
