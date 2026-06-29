"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { getUser, canWrite } from "@/lib/auth";
import { RefreshCw, Upload, Database, Users, Box, List, History, Search, Download, HelpCircle, AlertTriangle, ShieldCheck, Check, Info } from "lucide-react";

function fmt(dt: string | null) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export default function MasterDataPage() {
  const user = getUser();
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState({ text: "", type: "" });

  // P Master State
  const [pData, setPData] = useState<{ rows: any[]; columns: string[] }>({ rows: [], columns: [] });
  const [pLoading, setPLoading] = useState(false);
  const [pSearch, setPSearch] = useState("");
  const [pCategory, setPCategory] = useState("All");

  // P-H Master State
  const [phData, setPhData] = useState<{ rows: any[]; columns: string[] }>({ rows: [], columns: [] });
  const [phLoading, setPhLoading] = useState(false);
  const [phSearch, setPhSearch] = useState("");
  const [phCity, setPhCity] = useState("All");
  const [phPlan, setPhPlan] = useState("All");
  const [phViewMode, setPhViewMode] = useState<"key" | "all">("key");

  // P-H Master Sync State
  const [pidsInput, setPidsInput] = useState("");
  const [syncPreview, setSyncPreview] = useState<any>(null);
  const [syncingPH, setSyncingPH] = useState(false);
  const [confirmingPH, setConfirmingPH] = useState(false);

  // Hub Master State
  const [hubData, setHubData] = useState<{ rows: any[]; columns: string[] }>({ rows: [], columns: [] });
  const [hubLoading, setHubLoading] = useState(false);
  const [hubCity, setHubCity] = useState("All");
  const [hubStatus, setHubStatus] = useState("All");

  // Hub Changes (Editable) State
  const [hubChanges, setHubChanges] = useState<{ rows: any[]; columns: string[] }>({ rows: [], columns: [] });
  const [editedChanges, setEditedChanges] = useState<any[]>([]);
  const [savingChanges, setSavingChanges] = useState(false);

  // Inventory Buffer State
  const [invData, setInvData] = useState<Record<string, any[]>>({});
  const [invOrder, setInvOrder] = useState<string[]>([]);
  const [invSelectedTab, setInvSelectedTab] = useState("");
  const [invLoading, setInvLoading] = useState(false);
  const [syncingInv, setSyncingInv] = useState(false);

  // Snapshot Rollback State
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [restoring, setRestoring] = useState(false);

  const loadBaseData = async () => {
    setLoading(true);
    try {
      const [hist, hc, rns] = await Promise.all([
        api.get("/api/master-data/sync-history"),
        api.get("/api/master-data/hub-changes"),
        api.get("/api/master-data/snapshot-runs"),
      ]);
      setHistory(hist.data);
      setHubChanges(hc.data);
      setEditedChanges(hc.data.rows || []);
      setRuns(rns.data || []);
      if (rns.data?.length > 0) setSelectedRun(rns.data[0].id);
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    loadBaseData();
  }, []);

  // Actions
  const loadPMaster = async () => {
    setPLoading(true);
    try {
      const { data } = await api.get("/api/master-data/p-master");
      setPData(data);
    } catch {
      setMsg({ text: "❌ Failed to load P Master", type: "danger" });
    }
    setPLoading(false);
  };

  const loadPHMaster = async () => {
    setPhLoading(true);
    try {
      const { data } = await api.get("/api/master-data/ph-master");
      setPhData(data);
    } catch {
      setMsg({ text: "❌ Failed to load P-H Master", type: "danger" });
    }
    setPhLoading(false);
  };

  const loadHubMaster = async () => {
    setHubLoading(true);
    try {
      const { data } = await api.get("/api/master-data/hub-master");
      setHubData(data);
    } catch {
      setMsg({ text: "❌ Failed to load Hub Mapping", type: "danger" });
    }
    setHubLoading(false);
  };

  const loadInventoryBuffer = async () => {
    setInvLoading(true);
    try {
      const { data } = await api.get("/api/master-data/inventory-buffer");
      setInvData(data.tabs || {});
      setInvOrder(data.order || []);
      if (data.order?.length > 0) setInvSelectedTab(data.order[0]);
    } catch {
      setMsg({ text: "❌ Failed to load Inventory Buffer", type: "danger" });
    }
    setInvLoading(false);
  };

  const handlePHPreview = async () => {
    if (!pidsInput.trim()) return;
    setSyncingPH(true);
    setSyncPreview(null);
    try {
      const pids = pidsInput.split(",").map(p => p.trim()).filter(Boolean);
      const { data } = await api.post("/api/master-data/preview-ph-sync", { product_ids: pids });
      setSyncPreview(data);
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Preview failed"}`, type: "danger" });
    }
    setSyncingPH(false);
  };

  const handlePHConfirm = async () => {
    if (!syncPreview) return;
    setConfirmingPH(true);
    try {
      const { data } = await api.post("/api/master-data/confirm-ph-sync", {
        rows_to_add: syncPreview.rows_to_add,
        ph_headers: syncPreview.ph_headers,
        product_ids: syncPreview.product_ids,
      });
      setMsg({ text: `✅ ${data.detail}`, type: "success" });
      setSyncPreview(null);
      setPidsInput("");
      loadPHMaster();
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Sync failed"}`, type: "danger" });
    }
    setConfirmingPH(false);
  };

  const handleSyncExcel = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/api/master-data/sync");
      setMsg({ text: `✅ Excel Master synced successfully!`, type: "success" });
      loadBaseData();
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Excel sync failed"}`, type: "danger" });
    }
    setLoading(false);
  };

  const handleSyncInventoryExcel = async () => {
    setSyncingInv(true);
    try {
      const { data } = await api.post("/api/master-data/sync-inventory-excel");
      setMsg({ text: `✅ Wrote ${data.files?.length} worksheets to Excel`, type: "success" });
      loadInventoryBuffer();
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Inventory Excel sync failed"}`, type: "danger" });
    }
    setSyncingInv(false);
  };

  const handleEditChange = (index: number, col: string, value: string) => {
    const updated = [...editedChanges];
    updated[index] = { ...updated[index], [col]: value };
    setEditedChanges(updated);
  };

  const handleAddHubRow = () => {
    const columns = hubChanges.columns?.length > 0 ? hubChanges.columns : ["Type", "Hub_name", "Source_Hub", "Percentage", "Start_date", "End_date", "Hub_id", "product_ids", "add_hub_mapping"];
    const newRow = columns.reduce((acc, col) => ({ ...acc, [col]: "" }), {});
    setEditedChanges([...editedChanges, newRow]);
  };

  const handleDeleteHubRow = (index: number) => {
    setEditedChanges(editedChanges.filter((_, idx) => idx !== index));
  };

  const handleRestoreSnapshot = async () => {
    if (!selectedRun) return;
    setRestoring(true);
    try {
      const { data } = await api.post("/api/master-data/restore-snapshot", { run_id: selectedRun });
      setMsg({ text: `✅ ${data.detail}`, type: "success" });
      setConfirmRollback(false);
      loadBaseData();
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Snapshot restore failed"}`, type: "danger" });
    }
    setRestoring(false);
  };

  const handleSaveHubChanges = async () => {
    setSavingChanges(true);
    try {
      await api.post("/api/master-data/hub-changes", { rows: editedChanges });
      setMsg({ text: "✅ Hub changes saved to Pipeline Params Google Sheet.", type: "success" });
      loadBaseData();
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Failed to save changes"}`, type: "danger" });
    }
    setSavingChanges(false);
  };

  // UI - P Master Tab
  const pCategories = ["All", ...Array.from(new Set(pData.rows?.map(r => r["Sub-category"]).filter(Boolean)))].sort() as string[];
  const filteredPData = pData.rows?.filter(r => {
    const matchesSearch = Object.values(r).some(val => String(val).toLowerCase().includes(pSearch.toLowerCase()));
    const matchesCat = pCategory === "All" || r["Sub-category"] === pCategory;
    return matchesSearch && matchesCat;
  }) || [];

  const pMasterTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)", paddingBottom: "1rem", marginBottom: "1.25rem" }}>
          <div>
            <h4 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>Product Master (P Master)</h4>
            <div className="text-xs text-muted mt-1">ReadOnly data loaded from central master worksheets. Update products in Google Sheets.</div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadPMaster} disabled={pLoading}>
            <RefreshCw size={13} className={pLoading ? "animate-spin" : ""} /> Load / Refresh
          </button>
        </div>

        {pData.rows?.length > 0 && (
          <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
            <div className="stat-card">
              <div className="stat-label">Total Products</div>
              <div className="stat-value" style={{ color: "var(--blue)" }}>{pData.rows.length}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Sub-categories</div>
              <div className="stat-value" style={{ color: "var(--indigo)" }}>{pCategories.length - 1}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">SKU Classes</div>
              <div className="stat-value" style={{ color: "var(--green)" }}>{new Set(pData.rows.map(r => r["SKU Class Prod"]).filter(Boolean)).size}</div>
            </div>
          </div>
        )}

        {pData.rows?.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 240px", gap: "1rem", marginBottom: "1rem" }}>
            <div style={{ position: "relative" }}>
              <span style={{ position: "absolute", left: "0.85rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}>
                <Search size={15} />
              </span>
              <input
                type="text"
                placeholder="Search Product ID, Anchor Name, etc..."
                className="form-input text-sm"
                style={{ paddingLeft: "2.5rem" }}
                value={pSearch}
                onChange={e => setPSearch(e.target.value)}
              />
            </div>
            <div>
              <select className="form-input text-sm" value={pCategory} onChange={e => setPCategory(e.target.value)}>
                <option value="All">All Sub-categories</option>
                {pCategories.filter(c => c !== "All").map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {pLoading ? (
          <div style={{ textAlign: "center", padding: "4rem" }}><span className="spinner" /></div>
        ) : pData.rows?.length === 0 ? (
          <div className="text-sm text-muted text-center" style={{ padding: "3rem 1.5rem" }}>
            <Info size={24} style={{ display: "block", margin: "0 auto 0.75rem", opacity: 0.5 }} />
            Click **Load / Refresh** to retrieve Product Master worksheets.
          </div>
        ) : (
          <div>
            <div className="text-xs text-muted mb-3" style={{ fontWeight: 500 }}>Showing {filteredPData.length} of {pData.rows.length} records</div>
            <div className="table-wrap" style={{ maxHeight: "420px" }}>
              <table>
                <thead>
                  <tr>
                    {pData.columns.map(col => <th key={col}>{col}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {filteredPData.map((row, idx) => (
                    <tr key={idx}>
                      {pData.columns.map(col => <td key={col} style={{ fontSize: "0.75rem" }}>{String(row[col] ?? "—")}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  // UI - P-H Master Tab
  const phCities = ["All", ...Array.from(new Set(phData.rows?.map(r => r["city_name"]).filter(Boolean)))].sort() as string[];
  const phPlans = ["All", ...Array.from(new Set(phData.rows?.map(r => r["Plan Design"]).filter(Boolean)))].sort() as string[];
  const filteredPHData = phData.rows?.filter(r => {
    const matchesSearch = Object.values(r).some(val => String(val).toLowerCase().includes(phSearch.toLowerCase()));
    const matchesCity = phCity === "All" || r["city_name"] === phCity;
    const matchesPlan = phPlan === "All" || r["Plan Design"] === phPlan;
    return matchesSearch && matchesCity && matchesPlan;
  }) || [];

  const phMasterTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)", paddingBottom: "1rem", marginBottom: "1.25rem" }}>
          <div>
            <h4 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>Product-Hub Master (P-H Master)</h4>
            <div className="text-xs text-muted mt-1">Manage SKU allocation, Day-wise Active configurations, Split ratios, and Custom Prices by Hub.</div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadPHMaster} disabled={phLoading}>
            <RefreshCw size={13} className={phLoading ? "animate-spin" : ""} /> Load / Refresh
          </button>
        </div>

        {phData.rows?.length > 0 && (
          <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
            <div className="stat-card">
              <div className="stat-label">Total Combinations</div>
              <div className="stat-value" style={{ color: "var(--indigo)" }}>{phData.rows.length}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Unique SKUs</div>
              <div className="stat-value">{new Set(phData.rows.map(r => r["product_id"]).filter(Boolean)).size}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Assigned Hubs</div>
              <div className="stat-value">{new Set(phData.rows.map(r => r["hub_name"]).filter(Boolean)).size}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Active (Plan ≠ I)</div>
              <div className="stat-value" style={{ color: "var(--green)" }}>{phData.rows.filter(r => r["Plan Design"] !== "I").length}</div>
            </div>
          </div>
        )}

        {phData.rows?.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginBottom: "1rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 180px 180px", gap: "1rem" }}>
              <div style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: "0.85rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}>
                  <Search size={15} />
                </span>
                <input
                  type="text"
                  placeholder="Search products, hubs or cities..."
                  className="form-input text-sm"
                  style={{ paddingLeft: "2.5rem" }}
                  value={phSearch}
                  onChange={e => setPhSearch(e.target.value)}
                />
              </div>
              <div>
                <select className="form-input text-sm" value={phCity} onChange={e => setPhCity(e.target.value)}>
                  <option value="All">All Cities</option>
                  {phCities.filter(c => c !== "All").map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <select className="form-input text-sm" value={phPlan} onChange={e => setPhPlan(e.target.value)}>
                  <option value="All">All Plans</option>
                  {phPlans.filter(p => p !== "All").map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </div>

            <div style={{ display: "flex", gap: "1.25rem", alignItems: "center", padding: "0.25rem 0" }}>
              <span className="text-xs text-muted" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>View Mode:</span>
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", cursor: "pointer", color: "var(--text-secondary)" }}>
                <input type="radio" checked={phViewMode === "key"} onChange={() => setPhViewMode("key")} style={{ accentColor: "var(--blue)" }} /> Key Columns
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", cursor: "pointer", color: "var(--text-secondary)" }}>
                <input type="radio" checked={phViewMode === "all"} onChange={() => setPhViewMode("all")} style={{ accentColor: "var(--blue)" }} /> All Columns
              </label>
            </div>
          </div>
        )}

        {phLoading ? (
          <div style={{ textAlign: "center", padding: "4rem" }}><span className="spinner" /></div>
        ) : phData.rows?.length === 0 ? (
          <div className="text-sm text-muted text-center" style={{ padding: "3rem 1.5rem" }}>
            <Info size={24} style={{ display: "block", margin: "0 auto 0.75rem", opacity: 0.5 }} />
            Click **Load / Refresh** to view Product-Hub Master.
          </div>
        ) : (
          <div>
            <div className="text-xs text-muted mb-3" style={{ fontWeight: 500 }}>Showing {filteredPHData.length} of {phData.rows.length} rows</div>
            <div className="table-wrap" style={{ maxHeight: "380px" }}>
              <table>
                <thead>
                  <tr>
                    {(phViewMode === "key" ? keyPHCols : phData.columns).map(col => <th key={col}>{col}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {filteredPHData.map((row, idx) => (
                    <tr key={idx}>
                      {(phViewMode === "key" ? keyPHCols : phData.columns).map(col => <td key={col} style={{ fontSize: "0.75rem" }}>{String(row[col] ?? "—")}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Sync Section */}
      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>🔄 Sync New Products → P-H Master</h4>
        <p className="text-xs text-muted mb-4" style={{ lineHeight: 1.6 }}>
          Sync newly added Product IDs from P Master into P-H Master for all active hub configurations. Appended rows default to Plan Design 'I' (Inactive) for safety.
        </p>

        {canWrite(user?.role) ? (
          <div style={{ display: "flex", gap: "1rem", alignItems: "flex-end", borderBottom: syncPreview ? "1px solid var(--border)" : "none", paddingBottom: syncPreview ? "1.25rem" : "0", marginBottom: syncPreview ? "1.25rem" : "0" }}>
            <div style={{ flex: 1 }}>
              <label className="form-label" style={{ fontWeight: 600 }}>Product ID(s) — comma-separated</label>
              <input
                type="text"
                placeholder="e.g. PR_001, PR_002"
                className="form-input text-sm"
                value={pidsInput}
                onChange={e => setPidsInput(e.target.value)}
              />
            </div>
            <button className="btn btn-primary text-sm" onClick={handlePHPreview} disabled={syncingPH || !pidsInput.trim()}>
              {syncingPH ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "Preview Sync"}
            </button>
            {syncPreview && (
              <button className="btn btn-secondary text-sm" onClick={() => setSyncPreview(null)}>Reset</button>
            )}
          </div>
        ) : (
          <div className="alert alert-warning">Viewer role — sync not permitted.</div>
        )}

        {/* Sync Preview Panel */}
        {syncPreview && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div className="stat-grid">
              <div className="stat-card" style={{ padding: "0.85rem 1rem" }}>
                <div className="stat-label" style={{ fontSize: "0.62rem" }}>Schema Check</div>
                <div className="stat-value" style={{ fontSize: "1.2rem", color: syncPreview.schema_errors?.length > 0 ? "var(--red)" : "var(--green)" }}>
                  {syncPreview.schema_errors?.length > 0 ? "❌ Failed" : "✅ Passed"}
                </div>
              </div>
              <div className="stat-card" style={{ padding: "0.85rem 1rem" }}>
                <div className="stat-label" style={{ fontSize: "0.62rem" }}>Field Validation</div>
                <div className="stat-value" style={{ fontSize: "1.2rem", color: syncPreview.validation_errors?.length > 0 ? "var(--red)" : "var(--green)" }}>
                  {syncPreview.validation_errors?.length > 0 ? "⚠️ Issues Found" : "✅ Passed"}
                </div>
              </div>
              <div className="stat-card" style={{ padding: "0.85rem 1rem" }}>
                <div className="stat-label" style={{ fontSize: "0.62rem" }}>Rows to Append</div>
                <div className="stat-value" style={{ fontSize: "1.2rem", color: "var(--blue)" }}>{syncPreview.rows_to_add?.length}</div>
              </div>
            </div>

            {syncPreview.schema_errors?.length > 0 && (
              <div className="alert alert-danger" style={{ fontSize: "0.78rem" }}>
                <strong style={{ display: "block", marginBottom: "0.3rem" }}>Schema errors must be resolved:</strong>
                {syncPreview.schema_errors.map((e: string, i: number) => <div key={i}>• {e}</div>)}
              </div>
            )}

            {syncPreview.not_in_p_master?.length > 0 && (
              <div className="alert alert-warning" style={{ fontSize: "0.78rem" }}>
                <strong>Product IDs missing from P Master (skipped):</strong> {syncPreview.not_in_p_master.join(", ")}
              </div>
            )}

            {syncPreview.validation_errors?.length > 0 && (
              <div className="alert alert-danger" style={{ fontSize: "0.78rem" }}>
                <strong style={{ display: "block", marginBottom: "0.3rem" }}>Format errors must be resolved:</strong>
                {syncPreview.validation_errors.map((e: string, i: number) => <div key={i}>• {e}</div>)}
              </div>
            )}

            {syncPreview.rows_to_add?.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div>
                  <div className="text-xs text-muted mb-2" style={{ fontWeight: 600 }}>Proposed rows to add (Plan Design = I):</div>
                  <div className="table-wrap" style={{ maxHeight: "220px" }}>
                    <table>
                      <thead>
                        <tr>
                          {keyPHCols.map(c => <th key={c}>{c}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {syncPreview.rows_to_add.map((r: any, idx: number) => (
                          <tr key={idx}>
                            {keyPHCols.map(c => <td key={c} style={{ fontSize: "0.72rem" }}>{String(r[c] ?? "—")}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="alert alert-warning" style={{ fontSize: "0.78rem", lineHeight: 1.6, background: "var(--yellow-dim)", borderColor: "rgba(217,119,6,0.2)" }}>
                  <strong style={{ display: "block", marginBottom: "0.2rem" }}>⚠️ Google Sheets Reminder:</strong>
                  The new rows will write successfully, but you must manually fill Split %, price, HTT, and active flags directly in Google Sheets to fully activate the SKUs.
                </div>

                {canWrite(user?.role) && (
                  <button className="btn btn-primary text-sm" onClick={handlePHConfirm} disabled={confirmingPH} style={{ width: "100%", padding: "0.7rem" }}>
                    {confirmingPH ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <><Check size={14} /> Confirm & Write to P-H Master</>}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Sync Masters to Excel */}
      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>📥 Sync Masters to Excel (Backend)</h4>
        <p className="text-xs text-muted mb-4" style={{ lineHeight: 1.6 }}>
          Export the latest Google Sheets master sheets to a local file (`Product_Masters.xlsx`). This updates core reference databases on the server.
        </p>
        <button className="btn btn-secondary text-sm" onClick={handleSyncExcel} disabled={loading || !canWrite(user?.role)}>
          📥 Sync Masters to Excel
        </button>
      </div>
    </div>
  );

  // UI - Hub Master Tab
  const hubCities = ["All", ...Array.from(new Set(hubData.rows?.map(r => r["city_name"]).filter(Boolean)))].sort() as string[];
  const filteredHubData = hubData.rows?.filter(r => {
    const matchesCity = hubCity === "All" || r["city_name"] === hubCity;
    const matchesStatus = hubStatus === "All" ||
      (hubStatus === "Active (A)" && String(r["Hub_active"]).toUpperCase() === "A") ||
      (hubStatus === "Inactive (I)" && String(r["Hub_active"]).toUpperCase() !== "A");
    return matchesCity && matchesStatus;
  }) || [];

  const hubMasterTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)", paddingBottom: "1rem", marginBottom: "1.25rem" }}>
          <div>
            <h4 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>Hub Master (Hub Mapping)</h4>
            <div className="text-xs text-muted mt-1">Active hubs (Hub_active = A) mapped by cities and regions.</div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadHubMaster} disabled={hubLoading}>
            <RefreshCw size={13} className={hubLoading ? "animate-spin" : ""} /> Load / Refresh
          </button>
        </div>

        {hubData.rows?.length > 0 && (
          <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
            <div className="stat-card">
              <div className="stat-label">Total Hubs</div>
              <div className="stat-value" style={{ color: "var(--blue)" }}>{hubData.rows.length}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Active Hubs</div>
              <div className="stat-value" style={{ color: "var(--green)" }}>{hubData.rows.filter(r => String(r["Hub_active"]).toUpperCase() === "A").length}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Inactive Hubs</div>
              <div className="stat-value" style={{ color: "var(--text-muted)" }}>{hubData.rows.filter(r => String(r["Hub_active"]).toUpperCase() !== "A").length}</div>
            </div>
          </div>
        )}

        {hubData.rows?.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <select className="form-input text-sm" value={hubCity} onChange={e => setHubCity(e.target.value)}>
                <option value="All">All Cities</option>
                {hubCities.filter(c => c !== "All").map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <select className="form-input text-sm" value={hubStatus} onChange={e => setHubStatus(e.target.value)}>
                <option value="All">All Statuses</option>
                <option value="Active (A)">Active (A)</option>
                <option value="Inactive (I)">Inactive (I)</option>
              </select>
            </div>
          </div>
        )}

        {hubLoading ? (
          <div style={{ textAlign: "center", padding: "4rem" }}><span className="spinner" /></div>
        ) : hubData.rows?.length === 0 ? (
          <div className="text-sm text-muted text-center" style={{ padding: "3rem 1.5rem" }}>
            <Info size={24} style={{ display: "block", margin: "0 auto 0.75rem", opacity: 0.5 }} />
            Click **Load / Refresh** to view Hub Mapping.
          </div>
        ) : (
          <div>
            <div className="text-xs text-muted mb-3" style={{ fontWeight: 500 }}>Showing {filteredHubData.length} of {hubData.rows.length} hubs</div>
            <div className="table-wrap" style={{ maxHeight: "300px" }}>
              <table>
                <thead>
                  <tr>
                    {hubData.columns.map(col => <th key={col}>{col}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {filteredHubData.map((row, idx) => (
                    <tr key={idx}>
                      {hubData.columns.map(col => <td key={col} style={{ fontSize: "0.75rem" }}>{String(row[col] ?? "—")}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Hub Changes Editor */}
      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 0.4rem 0", fontSize: "1.05rem", fontWeight: 700, color: "var(--text-primary)" }}>✏️ Edit Configuration (saved to Pipeline Params)</h4>
        <p className="text-xs text-muted mb-4">Edit new hub config launches and KML remapping rules here.</p>

        <div className="table-wrap mb-4" style={{ maxHeight: "360px" }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: "120px" }}>Type</th>
                <th>Hub Name</th>
                <th>Source Hub</th>
                <th style={{ width: "90px" }}>Percentage</th>
                <th>Start Date</th>
                <th>End Date</th>
                <th>Hub ID</th>
                <th>Product IDs</th>
                <th style={{ width: "100px" }}>Add Hub Map</th>
                {canWrite(user?.role) && <th style={{ width: "80px", textAlign: "center" }}>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {editedChanges.map((row, idx) => (
                <tr key={idx}>
                  <td>
                    <select
                      className="form-input text-xs font-medium"
                      style={{ padding: "0.3rem 0.5rem" }}
                      value={row["Type"] || ""}
                      onChange={e => handleEditChange(idx, "Type", e.target.value)}
                      disabled={!canWrite(user?.role)}
                    >
                      <option value=""></option>
                      <option value="New Hub">New Hub</option>
                      <option value="KML Remapping">KML Remapping</option>
                    </select>
                  </td>
                  {["Hub_name", "Source_Hub", "Percentage", "Start_date", "End_date", "Hub_id", "product_ids"].map(field => (
                    <td key={field}>
                      <input
                        type="text"
                        className="form-input text-xs font-mono"
                        style={{ padding: "0.3rem 0.5rem" }}
                        value={row[field] ?? ""}
                        onChange={e => handleEditChange(idx, field, e.target.value)}
                        disabled={!canWrite(user?.role)}
                      />
                    </td>
                  ))}
                  <td>
                    <select
                      className="form-input text-xs font-medium"
                      style={{ padding: "0.3rem 0.5rem" }}
                      value={row["add_hub_mapping"] || ""}
                      onChange={e => handleEditChange(idx, "add_hub_mapping", e.target.value)}
                      disabled={!canWrite(user?.role)}
                    >
                      <option value=""></option>
                      <option value="TRUE">TRUE</option>
                      <option value="FALSE">FALSE</option>
                    </select>
                  </td>
                  {canWrite(user?.role) && (
                    <td style={{ textAlign: "center" }}>
                      <button className="btn btn-danger btn-sm text-xs" style={{ padding: "0.2rem 0.5rem" }} onClick={() => handleDeleteHubRow(idx)}>Delete</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {canWrite(user?.role) && (
          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button className="btn btn-secondary text-sm" onClick={handleAddHubRow}>＋ Add Row</button>
            <button className="btn btn-primary text-sm" onClick={handleSaveHubChanges} disabled={savingChanges}>
              {savingChanges ? "Saving..." : "Save Hub Changes"}
            </button>
          </div>
        )}
      </div>
    </div>
  );

  // UI - Inventory Buffer Tab
  const invTableRows = invData[invSelectedTab] || [];

  const inventoryBufferTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)", paddingBottom: "1rem", marginBottom: "1.25rem" }}>
          <div>
            <h4 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>📦 Inventory Buffer Master</h4>
            <p className="text-xs text-muted mt-1">Export raw parameters from sheet tabs to individual local excels on the backend.</p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button className="btn btn-secondary btn-sm" onClick={loadInventoryBuffer} disabled={invLoading}>
              <RefreshCw size={13} className={invLoading ? "animate-spin" : ""} /> Load Preview
            </button>
            <button className="btn btn-primary btn-sm" onClick={handleSyncInventoryExcel} disabled={syncingInv || !canWrite(user?.role)}>
              {syncingInv ? "Syncing..." : "📥 Sync all to Excel"}
            </button>
          </div>
        </div>

        {invOrder.length > 0 && (
          <div style={{ marginBottom: "1.25rem" }}>
            <label className="form-label" style={{ fontWeight: 600 }}>Active Tab Preview:</label>
            <select
              className="form-input text-sm"
              style={{ width: "260px" }}
              value={invSelectedTab}
              onChange={e => setInvSelectedTab(e.target.value)}
            >
              {invOrder.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        )}

        {invLoading ? (
          <div style={{ textAlign: "center", padding: "4rem" }}><span className="spinner" /></div>
        ) : invOrder.length === 0 ? (
          <div className="text-sm text-muted text-center" style={{ padding: "3rem 1.5rem" }}>
            <Info size={24} style={{ display: "block", margin: "0 auto 0.75rem", opacity: 0.5 }} />
            Click **Load Preview** or sync worksheet tabs.
          </div>
        ) : (
          <div>
            <div className="text-xs text-muted mb-3" style={{ fontWeight: 500 }}>Showing {invTableRows.length} rows inside "{invSelectedTab}"</div>
            <div className="table-wrap" style={{ maxHeight: "380px" }}>
              <table>
                <thead>
                  <tr>
                    {invTableRows[0] ? Object.keys(invTableRows[0]).map(k => <th key={k}>{k}</th>) : <th>Data</th>}
                  </tr>
                </thead>
                <tbody>
                  {invTableRows.map((row, idx) => (
                    <tr key={idx}>
                      {Object.keys(row).map(k => <td key={k} style={{ fontSize: "0.75rem" }}>{String(row[k] ?? "—")}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  // UI - Sync History / Snapshot Rollback Tab
  const historyTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 1rem 0", fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>📜 Master Sync History</h4>
        {loading ? (
          <div style={{ textAlign: "center", padding: "3.5rem" }}><span className="spinner" /></div>
        ) : history.length === 0 ? (
          <div className="text-xs text-muted text-center" style={{ padding: "2rem" }}>No sync history logs found.</div>
        ) : (
          <div className="table-wrap" style={{ maxHeight: "350px" }}>
            <table>
              <thead>
                <tr>
                  <th>Sync Date</th>
                  <th>Master Type</th>
                  <th>Status</th>
                  <th>Records Synced</th>
                  <th>Synced By</th>
                  <th>Error Message</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h: any) => (
                  <tr key={h.id}>
                    <td style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>{fmt(h.sync_date)}</td>
                    <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{h.master_type}</td>
                    <td>
                      <span className={`badge badge-${h.status === "success" ? "green" : "red"}`} style={{ padding: "0.15rem 0.5rem", borderRadius: "4px" }}>{h.status}</span>
                    </td>
                    <td>{h.records_synced ?? "—"}</td>
                    <td style={{ fontSize: "0.72rem" }}>{h.synced_by || "—"}</td>
                    <td style={{ fontSize: "0.7rem", color: "var(--red)", maxWidth: "240px", wordBreak: "break-all" }}>{h.error_message || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Snapshot Rollback Panel */}
      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>⏪ Snapshot Rollback</h4>
        <p className="text-xs text-muted mb-4">Restore Google Sheets master tables to a previous clean state from automated snapshots.</p>

        {runs.length === 0 ? (
          <div className="text-sm text-muted text-center" style={{ padding: "2rem" }}>No versioned master sync snapshots yet. Run Sync Masters first.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "1.25rem", alignItems: "flex-end" }}>
              <div>
                <label className="form-label" style={{ fontWeight: 600 }}>Select snapshot to restore:</label>
                <select className="form-input text-sm" value={selectedRun} onChange={e => setSelectedRun(e.target.value)}>
                  {runs.map((r: any) => (
                    <option key={r.id} value={r.id}>
                      {new Date(r.started_at).toLocaleString("en-IN")} · {r.id.slice(0, 8)}... ({r.triggered_by || "auto"})
                    </option>
                  ))}
                </select>
              </div>

              {canWrite(user?.role) && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.78rem", cursor: "pointer", color: "var(--text-secondary)" }}>
                    <input type="checkbox" checked={confirmRollback} onChange={e => setConfirmRollback(e.target.checked)} style={{ accentColor: "var(--blue)" }} />
                    Verify overwrite confirm
                  </label>
                  <button className="btn btn-danger text-sm w-full" onClick={handleRestoreSnapshot} disabled={restoring || !confirmRollback}>
                    {restoring ? "Restoring..." : "⏪ Restore Snapshot"}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  const mainTabs = [
    { id: "p-master", label: "📦 P Master", content: pMasterTab },
    { id: "ph-master", label: "🗂️ P-H Master", content: phMasterTab },
    { id: "hub-master", label: "🏪 Hub Master", content: hubMasterTab },
    { id: "inventory", label: "📦 Inventory Buffer Master", content: inventoryBufferTab },
    { id: "history", label: "📜 Master Sync History", content: historyTab },
  ];

  return (
    <AppShell
      title="Master Data Management"
      subtitle="Sync, validate, and manage Demand Planning & Inventory Masters"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={loadBaseData} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {msg.text && (
        <div className={`alert alert-${msg.type}`} style={{ marginBottom: "1.25rem" }}>{msg.text}</div>
      )}

      <Tabs tabs={mainTabs} defaultTab="p-master" />
    </AppShell>
  );
}
