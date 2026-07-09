"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { ChevronDown, ChevronRight, Filter } from "lucide-react";

type DemoFilter = {
  city: string;
  hubs: string[];
  active: boolean;
  cities: string[];
  available_hubs: string[];
};

export default function DemoFilterPanel() {
  const { role, hydrated } = useAuth();
  const isVisible = hydrated && ["admin", "planner", "viewer", "product"].includes(role);
  const [data, setData] = useState<DemoFilter | null>(null);
  const [loading, setLoading] = useState(true);
  const [city, setCity] = useState("All Cities");
  const [hubs, setHubs] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    if (!isVisible) return;
    setLoading(true);
    try {
      const { data: res } = await api.get<DemoFilter>("/api/demo-filter");
      setData(res);
      setCity(res.city || "All Cities");
      setHubs(res.hubs || []);
      if (res.active) setOpen(true);
    } catch {
      setData({ city: "All Cities", hubs: [], active: false, cities: ["All Cities"], available_hubs: [] });
    } finally {
      setLoading(false);
    }
  }, [isVisible]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!isVisible) return null;

  const hubOptions = data?.available_hubs || [];

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/api/demo-filter", { city, hubs });
      await load();
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    setSaving(true);
    try {
      await api.delete("/api/demo-filter");
      setCity("All Cities");
      setHubs([]);
      await load();
    } finally {
      setSaving(false);
    }
  };

  const toggleHub = (hub: string) => {
    setHubs(prev => (prev.includes(hub) ? prev.filter(h => h !== hub) : [...prev, hub]));
  };

  return (
    <div className="sidebar-demo">
      <button
        type="button"
        className="sidebar-demo-toggle"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
      >
        <span className="sidebar-demo-toggle-left">
          <Filter size={14} />
          <span>Demo filter</span>
          {data?.active && <span className="sidebar-demo-badge">On</span>}
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {open && (
        <div className="sidebar-demo-body">
          <select
            className="form-input sidebar-demo-select"
            value={city}
            onChange={e => setCity(e.target.value)}
            disabled={loading}
          >
            {(data?.cities?.length ? data.cities : ["All Cities"]).map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          <div className="sidebar-demo-hubs">
            {hubOptions.length === 0 ? (
              <span className="text-muted text-xs">No hubs — fetch raw data first</span>
            ) : (
              hubOptions.slice(0, 40).map(h => (
                <label key={h} className="sidebar-demo-hub-row">
                  <input
                    type="checkbox"
                    checked={hubs.includes(h)}
                    onChange={() => toggleHub(h)}
                  />
                  <span>{h}</span>
                </label>
              ))
            )}
          </div>

          <div className="sidebar-demo-actions">
            <button type="button" className="btn btn-primary btn-sm" onClick={save} disabled={saving}>
              Apply
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={clear} disabled={saving}>
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
