"use client";

import { useState, useEffect } from "react";
import { Upload, File as FileIcon, CheckCircle2 } from "lucide-react";
import SectionCard from "@/components/baseline/SectionCard";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export default function FestiveUploadSection() {
  const { readOnly } = useAuth();
  
  const [festiveFile, setFestiveFile] = useState<File | null>(null);
  const [festiveTask, setFestiveTask] = useState<string>("");
  const [festiveStatus, setFestiveStatus] = useState<{progress: number, status: string, error: string | null}>({progress: 0, status: "", error: null});

  useEffect(() => {
    if (!festiveTask || festiveStatus.status === "completed" || festiveStatus.status === "error") return;
    
    const iv = setInterval(async () => {
      try {
        const { data } = await api.get(`/api/baseline/festive-upload/status/${festiveTask}`);
        setFestiveStatus(data);
      } catch (err) {
        // Only fail if we get 404, might just be network blip
      }
    }, 1000);
    return () => clearInterval(iv);
  }, [festiveTask, festiveStatus.status]);

  const handleFestiveUpload = async () => {
    if (!festiveFile) return;
    setFestiveStatus({ progress: 0, status: "uploading", error: null });
    const formData = new FormData();
    formData.append("file", festiveFile);

    try {
      const { data } = await api.post("/api/baseline/festive-upload", formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setFestiveTask(data.task_id);
      setFestiveStatus({ progress: 0, status: "queued", error: null });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setFestiveStatus({ 
        progress: 0, 
        status: "error", 
        error: err?.response?.data?.detail || "Failed to start upload" 
      });
    }
  };

  return (
    <SectionCard title="Festive Upload" description="Upload an Excel or CSV file. It will be converted to Parquet and uploaded directly to Google Drive.">
      <div className="flex flex-col gap-4 max-w-xl">
        <div className="flex items-center gap-3">
          <label className="flex-1 border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl p-4 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors flex items-center justify-center gap-2">
            <FileIcon size={16} className="text-slate-500" />
            <span className="text-sm text-slate-600 dark:text-slate-300 font-medium">
              {festiveFile ? festiveFile.name : "Select Excel or CSV file"}
            </span>
            <input 
              type="file" 
              className="hidden" 
              accept=".csv, .xlsx, .xls"
              onChange={(e) => setFestiveFile(e.target.files?.[0] || null)}
              disabled={readOnly || festiveStatus.status === "uploading" || festiveStatus.status === "queued" || festiveStatus.status === "processing"}
            />
          </label>
          <button
            type="button"
            className="btn btn-primary whitespace-nowrap"
            disabled={!festiveFile || readOnly || festiveStatus.status === "uploading" || festiveStatus.status === "queued" || festiveStatus.status === "processing"}
            onClick={handleFestiveUpload}
          >
            <Upload size={14} />
            Upload to Drive
          </button>
        </div>

        {festiveStatus.status && (
          <div className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg p-4">
            <div className="flex justify-between text-xs font-semibold mb-2">
              <span className="text-slate-700 dark:text-slate-300 capitalize">
                {festiveStatus.status === "uploading" ? "Uploading to server..." : festiveStatus.status === "queued" ? "Queued for processing..." : festiveStatus.status === "processing" ? "Uploading to Google Drive..." : festiveStatus.status === "completed" ? "Upload Completed Successfully!" : "Upload Failed"}
              </span>
              <span className="text-blue-600 dark:text-blue-400">{festiveStatus.progress}%</span>
            </div>
            <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2.5 overflow-hidden">
              <div 
                className={`h-2.5 rounded-full transition-all duration-300 ${festiveStatus.status === "error" ? "bg-red-500" : festiveStatus.status === "completed" ? "bg-emerald-500" : "bg-blue-600"}`}
                style={{ width: `${festiveStatus.progress}%` }}
              ></div>
            </div>
            {festiveStatus.error && (
              <p className="mt-2 text-xs text-red-600 dark:text-red-400 font-medium">{festiveStatus.error}</p>
            )}
            {festiveStatus.status === "completed" && (
              <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                <CheckCircle2 size={12} /> Saved as Parquet to Google Drive.
              </p>
            )}
          </div>
        )}
      </div>
    </SectionCard>
  );
}
