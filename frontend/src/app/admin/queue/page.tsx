"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

type JobStatus = "pending" | "processing" | "completed" | "failed";

interface QueueJob {
  id: string;
  task_name: string;
  status: JobStatus;
  created_at: string | null;
  locked_at: string | null;
  completed_at: string | null;
  retries: number;
  error_message: string | null;
}

interface QueueStats {
  pending: number;
  processing: number;
  failed: number;
  completed: number;
  total: number;
}

interface QueueStatusResponse {
  stats: QueueStats;
  recent_jobs: QueueJob[];
}

export default function QueueAdminPage() {
  const { user } = useAuth();
  const [data, setData] = useState<QueueStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = async () => {
    try {
      setError("");
      const response = await api.get<QueueStatusResponse>("/api/settings/queue/status");
      setData(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load queue status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.role === "admin") {
      fetchData();
      // Auto-refresh every 5 seconds
      const interval = setInterval(fetchData, 5000);
      return () => clearInterval(interval);
    } else if (user) {
      setError("Admin access required.");
      setLoading(false);
    }
  }, [user]);

  if (!user) return <div className="p-8">Loading auth...</div>;
  if (loading && !data) return <div className="p-8">Loading queue status...</div>;
  if (error) return <div className="p-8 text-red-500 font-medium">{error}</div>;
  if (!data) return null;

  const formatRelativeTime = (dateString: string) => {
    const date = new Date(dateString);
    const diff = Math.floor((new Date().getTime() - date.getTime()) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  };

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Queue Monitoring Dashboard</h1>
      
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center">
          <div className="text-sm font-medium text-gray-500 uppercase">Pending</div>
          <div className="text-3xl font-bold text-blue-600 mt-2">{data.stats.pending}</div>
        </div>
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center">
          <div className="text-sm font-medium text-gray-500 uppercase">Processing</div>
          <div className="text-3xl font-bold text-yellow-500 mt-2">{data.stats.processing}</div>
        </div>
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center">
          <div className="text-sm font-medium text-gray-500 uppercase">Failed</div>
          <div className="text-3xl font-bold text-red-500 mt-2">{data.stats.failed}</div>
        </div>
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center">
          <div className="text-sm font-medium text-gray-500 uppercase">Completed</div>
          <div className="text-3xl font-bold text-green-500 mt-2">{data.stats.completed}</div>
        </div>
      </div>

      {/* Jobs Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
          <h2 className="font-semibold text-gray-800">Recent Jobs</h2>
          <button 
            onClick={fetchData}
            className="text-sm px-3 py-1 bg-white border border-gray-200 rounded hover:bg-gray-50 transition-colors"
          >
            Refresh Now
          </button>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-500 uppercase bg-gray-50/50">
              <tr>
                <th className="px-6 py-3 font-medium">Job ID / Task</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Created</th>
                <th className="px-6 py-3 font-medium">Retries</th>
                <th className="px-6 py-3 font-medium">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.recent_jobs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-gray-500 italic">
                    No jobs found in the queue.
                  </td>
                </tr>
              ) : (
                data.recent_jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-50/50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium text-gray-900">{job.task_name}</div>
                      <div className="text-xs text-gray-500 font-mono mt-1" title={job.id}>
                        {job.id.split("-")[0]}...
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${
                        job.status === 'completed' ? 'bg-green-100 text-green-700' :
                        job.status === 'failed' ? 'bg-red-100 text-red-700' :
                        job.status === 'processing' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-blue-100 text-blue-700'
                      }`}>
                        {job.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-600">
                      {job.created_at ? formatRelativeTime(job.created_at) : '-'}
                    </td>
                    <td className="px-6 py-4">
                      {job.retries > 0 ? (
                        <span className="text-amber-600 font-medium">{job.retries}</span>
                      ) : (
                        <span className="text-gray-400">0</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {job.error_message ? (
                        <div className="text-red-600 text-xs truncate max-w-xs" title={job.error_message}>
                          {job.error_message.split('\n').pop()}
                        </div>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
