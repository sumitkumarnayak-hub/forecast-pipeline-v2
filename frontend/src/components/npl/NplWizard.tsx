"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useNplBootstrap } from "@/context/NplContext";
import { ChevronRight, Download, Mail, Upload } from "lucide-react";

const BASE_STAGES = ["upload", "split", "dates", "confirm"] as const;
const REPLACEMENT_STAGES = ["setup", "upload", "split", "dates", "confirm"] as const;

type BaseStage = (typeof BASE_STAGES)[number];
type ReplacementStage = (typeof REPLACEMENT_STAGES)[number];
type WizardStage = BaseStage | ReplacementStage | "setup";

interface NplWizardProps {
  subType: "New Launch" | "Expansion" | "Replacement";
  title: string;
  description: string;
}

interface EmailResult {
  status?: string;
  recipients?: string[];
  error?: string;
  skipped?: boolean;
  reason?: string;
}

function stageLabels(subType: NplWizardProps["subType"]): string[] {
  if (subType === "Replacement") {
    return ["1 · Old & New SKU", "2 · Upload", "3 · Hub Split", "4 · Launch Date", "5 · Confirm"];
  }
  return ["1 · Upload", "2 · Hub Split", "3 · Launch Date", "4 · Confirm"];
}

export default function NplWizard({ subType, title, description }: NplWizardProps) {
  const { readOnly } = useAuth();
  const { context, products: allProducts, loading: nplLoading, error: nplError, getProductsByCategory } =
    useNplBootstrap();
  const categories = context?.categories ?? [];
  const cities = context?.cities ?? [];
  const isReplacement = subType === "Replacement";
  const isExpansion = subType === "Expansion";
  const stages = isReplacement ? REPLACEMENT_STAGES : BASE_STAGES;

  const [stage, setStage] = useState<WizardStage>(isReplacement ? "setup" : "upload");
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [busy, setBusy] = useState("");
  const [stepState, setStepState] = useState<{ step: string; status: "idle" | "loading" | "success" | "error"; message: string }>({ step: "", status: "idle", message: "" });

  const [category, setCategory] = useState("");
  const [planLevel, setPlanLevel] = useState<"city" | "hub">("city");
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [cityHubs, setCityHubs] = useState<Record<string, string[]>>({});
  const [hubRows, setHubRows] = useState<Record<string, unknown>[]>([]);
  const [hubColumns, setHubColumns] = useState<string[]>([]);
  const [zeroSal, setZeroSal] = useState<Record<string, string[]>>({});
  const [launchDate, setLaunchDate] = useState("");
  const [earliestDate, setEarliestDate] = useState("");

  const [expansionPid, setExpansionPid] = useState("");
  const [expansionName, setExpansionName] = useState("");
  const [expansionCategory, setExpansionCategory] = useState("");

  const [newLaunchPid, setNewLaunchPid] = useState("");
  const [newLaunchName, setNewLaunchName] = useState("");

  const [oldCategory, setOldCategory] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [oldProducts, setOldProducts] = useState<string[]>([]);
  const [newProducts, setNewProducts] = useState<string[]>([]);
  const [oldProductName, setOldProductName] = useState("");
  const [newProductName, setNewProductName] = useState("");
  const [oldPid, setOldPid] = useState("");
  const [newPid, setNewPid] = useState("");
  const [splitPct, setSplitPct] = useState(100);

  const [dupes, setDupes] = useState<Record<string, unknown>[] | null>(null);
  const [emailResult, setEmailResult] = useState<{
    planner?: EmailResult;
    admin?: EmailResult;
    skipped?: boolean;
    reason?: string;
  } | null>(null);

  useEffect(() => {
    if (!context) return;
    const minDate = context.earliest_launch_date || "";
    setEarliestDate(minDate);
    setLaunchDate(prev => prev || minDate);
    if (context.categories?.length) {
      const first = context.categories[0];
      setCategory(prev => prev || first);
      setOldCategory(prev => prev || first);
      setNewCategory(prev => prev || first);
    }
  }, [context]);

  useEffect(() => {
    if (!oldCategory) return;
    getProductsByCategory(oldCategory).then(setOldProducts);
  }, [oldCategory, getProductsByCategory]);

  useEffect(() => {
    if (!newCategory) return;
    getProductsByCategory(newCategory).then(setNewProducts);
  }, [newCategory, getProductsByCategory]);

  useEffect(() => {
    if (!selectedCities.length) return;
    selectedCities.forEach(city => {
      api
        .get("/api/new-product-launch/wizard/hubs", {
          params: { city, category: expansionCategory || category || undefined },
        })
        .then(({ data }) => {
          setCityHubs(prev => (prev[city]?.length ? prev : { ...prev, [city]: data.hubs || [] }));
        })
        .catch(() => {});
    });
  }, [selectedCities, category, expansionCategory]);

  const templateProductId = isExpansion ? expansionPid : isReplacement ? newPid : newLaunchPid;
  const templateProductName = isExpansion ? expansionName : isReplacement ? newProductName : newLaunchName;

  const downloadTemplate = async () => {
    if (!selectedCities.length) {
      setMsg({ text: "Select at least one city", type: "warning" });
      return;
    }
    setBusy("template");
    try {
      const path =
        planLevel === "city"
          ? "/api/new-product-launch/wizard/template/city"
          : "/api/new-product-launch/wizard/template/hub";
      const forcedHubs = Object.fromEntries(
        Object.entries(cityHubs).filter(([, hubs]) => hubs.length > 0),
      );
      const body =
        planLevel === "city"
          ? {
              cities: selectedCities,
              category: expansionCategory || category,
              product_id: templateProductId,
              product_name: templateProductName,
            }
          : {
              cities_hubs: Object.keys(forcedHubs).length ? forcedHubs : cityHubs,
              category: expansionCategory || category,
              product_id: templateProductId,
              product_name: templateProductName,
            };
      const res = await api.post(path, body, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${planLevel}_template_${expansionCategory || category}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setMsg({ text: "Template download failed", type: "danger" });
    }
    setBusy("");
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy("upload");
    setStepState({ step: "upload", status: "loading", message: "Parsing your file..." });
    setMsg({ text: "", type: "" });
    try {
      const form = new FormData();
      form.append("file", file);
      const path =
        planLevel === "city"
          ? "/api/new-product-launch/wizard/parse-city"
          : "/api/new-product-launch/wizard/parse-hub";
      const { data } = await api.post(path, form, { headers: { "Content-Type": "multipart/form-data" } });

      const forced = Object.fromEntries(
        Object.entries(cityHubs).filter(([, hubs]) => hubs.length > 0),
      );

      if (planLevel === "city") {
        setStepState({ step: "split", status: "loading", message: "Calculating hub split from salience data..." });
        const split = await api.post("/api/new-product-launch/wizard/split-city", {
          city_rows: data.rows,
          forced_hubs: Object.keys(forced).length ? forced : null,
        });
        setHubRows(split.data.hub_rows || []);
        setHubColumns(split.data.columns || []);
        setZeroSal(split.data.zero_salience || {});
      } else {
        setHubRows(data.rows || []);
        setHubColumns(data.columns || []);
      }
      setStage("split");
      setStepState({ step: "", status: "idle", message: "" });
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string | string[] } } };
      const d = error?.response?.data?.detail;
      const errorMsg = Array.isArray(d) ? d.join("; ") : String(d || "Upload failed");
      setStepState({ step: "upload", status: "error", message: errorMsg });
      setMsg({ text: errorMsg, type: "danger" });
    }
    setBusy("");
    e.target.value = "";
  };

  const editCell = (rowIdx: number, col: string, value: string) => {
    setHubRows(prev => {
      const next = [...prev];
      next[rowIdx] = { ...next[rowIdx], [col]: value };
      return next;
    });
  };

  const toggleCityHub = (city: string, hub: string) => {
    setCityHubs(prev => {
      const current = prev[city] || [];
      const next = current.includes(hub) ? current.filter(h => h !== hub) : [...current, hub];
      return { ...prev, [city]: next };
    });
  };

  const checkDuplicates = async () => {
    setBusy("dupes");
    setStepState({ step: "dupes", status: "loading", message: "Checking for existing submissions..." });
    setDupes(null);
    try {
      const { data } = await api.post(
        "/api/new-product-launch/wizard/check-duplicates",
        { hub_rows: hubRows },
        { params: { sub_type: subType, plan_level: planLevel } },
      );
      if (data.has_duplicates) {
        setDupes(data.existing_rows || []);
        setMsg({ text: "Duplicate submission(s) found in log — review before submitting", type: "warning" });
        setStepState({ step: "dupes", status: "success", message: "Duplicates found" });
      } else {
        setMsg({ text: "No duplicates in submission log", type: "success" });
        setStepState({ step: "dupes", status: "success", message: "No duplicates found" });
      }
    } catch {
      setMsg({ text: "Duplicate check failed", type: "danger" });
      setStepState({ step: "dupes", status: "error", message: "Duplicate check failed" });
    }
    setBusy("");
  };

  const submit = async () => {
    setBusy("submit");
    setStepState({ step: "submit", status: "loading", message: "Submitting to DB and Google Sheets..." });
    try {
      const dated = hubRows.map(r => ({ ...r, launch_date: launchDate }));
      const { data } = await api.post("/api/new-product-launch/wizard/submit", {
        hub_rows: dated,
        sub_type: subType,
        launch_date: launchDate,
      });
      setEmailResult(data.email || null);
      setMsg({ text: `Submitted — ID ${data.submission_id}`, type: "success" });
      setStepState({ step: "submit", status: "success", message: "Successfully submitted" });
      setStage(isReplacement ? "setup" : "upload");
      setHubRows([]);
      setDupes(null);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      const errDetail = error?.response?.data?.detail || "Submit failed";
      setMsg({ text: errDetail, type: "danger" });
      setStepState({ step: "submit", status: "error", message: errDetail });
    }
    setBusy("");
  };

  const toggleCity = (c: string) => {
    setSelectedCities(prev => (prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]));
  };

  const onExpansionPidChange = (pid: string) => {
    setExpansionPid(pid);
    const row = allProducts.find(p => p.product_id === pid);
    if (row) {
      setExpansionName(row.product_name);
      setExpansionCategory(row.category);
      setCategory(row.category);
    }
  };

  const resolveProductId = async (cat: string, name: string): Promise<string> => {
    const match = allProducts.find(p => p.product_name === name && p.category === cat);
    if (match) return match.product_id;
    const names = await getProductsByCategory(cat);
    if (!names.includes(name)) return "";
    return allProducts.find(p => p.product_name === name && p.category === cat)?.product_id || "";
  };

  const finishReplacementSetup = async () => {
    if (!oldProductName || !newProductName || !selectedCities.length) {
      setMsg({ text: "Select old/new products and at least one city", type: "warning" });
      return;
    }
    const oPid = allProducts.find(p => p.product_name === oldProductName && p.category === oldCategory)?.product_id
      || await resolveProductId(oldCategory, oldProductName);
    const nPid = allProducts.find(p => p.product_name === newProductName && p.category === newCategory)?.product_id
      || await resolveProductId(newCategory, newProductName);
    setOldPid(oPid);
    setNewPid(nPid);
    setCategory(newCategory);
    setStage("upload");
    setMsg({ text: "", type: "" });
  };

  const labels = stageLabels(subType);
  const categoryOptions =
    categories.length > 0
      ? categories
      : nplLoading
        ? ["Loading categories…"]
        : ["No categories available"];
  const categorySelectDisabled = readOnly || nplLoading || categories.length === 0;

  return (
    <div className="card" style={{ padding: "1.25rem" }}>
      <h4 style={{ margin: "0 0 0.25rem" }}>{title}</h4>
      <p className="text-xs text-muted mb-4">{description}</p>
      {nplLoading && !context && (
        <div className="alert alert-info mb-3 text-sm flex items-center gap-2">
          <span className="spinner" style={{ width: 14, height: 14 }} />
          Loading categories, cities, and products from master data…
        </div>
      )}
      {nplError && !context && (
        <div className="alert alert-danger mb-3 text-sm">{nplError}</div>
      )}

      {stepState.status === "loading" && (
        <div className="alert alert-info mb-3 text-sm flex items-center gap-2">
          <span className="spinner" style={{ width: 14, height: 14 }} />
          {stepState.message}
        </div>
      )}
      {stepState.status === "error" && (
        <div className="alert alert-danger mb-3 text-sm flex justify-between items-center">
          <span><strong>Error:</strong> {stepState.message}</span>
          <button className="btn btn-sm btn-secondary" onClick={() => setStepState({ step: "", status: "idle", message: "" })}>Dismiss</button>
        </div>
      )}
      {msg.text && stepState.status !== "error" && <div className={`alert alert-${msg.type} mb-3 text-sm`}>{msg.text}</div>}

      <div className="flex flex-wrap gap-2 mb-4 text-xs">
        {labels.map((label, i) => {
          const s = stages[i];
          return (
            <span
              key={s}
              className={`badge ${stage === s ? "badge-blue" : "badge-gray"}`}
              style={{ cursor: "default" }}
            >
              {label}
            </span>
          );
        })}
      </div>

      {isReplacement && stage === "setup" && (
        <>
          <div className="grid-2 mb-3" style={{ maxWidth: 720 }}>
            <div>
              <p className="text-xs font-semibold mb-2">Old SKU (being replaced)</p>
              <select className="form-input text-sm mb-2" value={oldCategory} onChange={e => setOldCategory(e.target.value)} disabled={categorySelectDisabled}>
                {!oldCategory && <option value="">Select category</option>}
                {categoryOptions.map(c => (
                  <option key={c} value={c === "Loading categories…" || c === "No categories available" ? "" : c}>{c}</option>
                ))}
              </select>
              <select className="form-input text-sm" value={oldProductName} onChange={e => setOldProductName(e.target.value)} disabled={readOnly || !oldCategory}>
                <option value="">{oldProducts.length ? "Select product" : "Loading products…"}</option>
                {oldProducts.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <p className="text-xs font-semibold mb-2">New SKU (replacement)</p>
              <select className="form-input text-sm mb-2" value={newCategory} onChange={e => setNewCategory(e.target.value)} disabled={categorySelectDisabled}>
                {!newCategory && <option value="">Select category</option>}
                {categoryOptions.map(c => (
                  <option key={c} value={c === "Loading categories…" || c === "No categories available" ? "" : c}>{c}</option>
                ))}
              </select>
              <select className="form-input text-sm" value={newProductName} onChange={e => setNewProductName(e.target.value)} disabled={readOnly || !newCategory}>
                <option value="">{newProducts.length ? "Select product" : "Loading products…"}</option>
                {newProducts.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="form-group mb-3" style={{ maxWidth: 360 }}>
            <label className="form-label">% plan to new SKU ({splitPct}% new · {100 - splitPct}% old)</label>
            <input
              type="range"
              min={0}
              max={100}
              value={splitPct}
              onChange={e => setSplitPct(Number(e.target.value))}
              disabled={readOnly}
              className="w-full"
            />
          </div>
          <div className="form-group mb-3">
            <label className="form-label">Cities</label>
            <div className="flex flex-wrap gap-2">
              {cities.length ? (
                cities.map(c => (
                  <button
                    key={c}
                    type="button"
                    className={`btn btn-sm ${selectedCities.includes(c) ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => toggleCity(c)}
                    disabled={readOnly}
                  >
                    {c}
                  </button>
                ))
              ) : (
                <span className="text-xs text-muted">{nplLoading ? "Loading cities…" : "No cities available"}</span>
              )}
            </div>
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={finishReplacementSetup} disabled={readOnly}>
            Next: Upload plan <ChevronRight size={13} />
          </button>
        </>
      )}

      {stage === "upload" && (
        <>
          {isExpansion && (
            <div className="form-group mb-3" style={{ maxWidth: 420 }}>
              <label className="form-label">Existing Product ID</label>
              <select
                className="form-input text-sm"
                value={expansionPid}
                onChange={e => onExpansionPidChange(e.target.value)}
                disabled={readOnly || (nplLoading && allProducts.length === 0)}
              >
                <option value="">{allProducts.length ? "Select product" : "Loading products…"}</option>
                {allProducts.map(p => (
                  <option key={p.product_id} value={p.product_id}>
                    {p.product_id} — {p.product_name}
                  </option>
                ))}
              </select>
              {expansionName && (
                <p className="text-xs text-muted mt-1">
                  {expansionName} · {expansionCategory}
                </p>
              )}
            </div>
          )}
          {!isExpansion && null}
          <div className="grid-2 mb-3" style={{ maxWidth: 560 }}>
            {!isExpansion && (
              <div className="form-group">
                <label className="form-label">Sub-Category</label>
                <select className="form-input text-sm" value={category} onChange={e => setCategory(e.target.value)} disabled={categorySelectDisabled || isExpansion}>
                  {!category && <option value="">Select category</option>}
                  {categoryOptions.map(c => (
                    <option key={c} value={c === "Loading categories…" || c === "No categories available" ? "" : c}>{c}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="form-group">
              <label className="form-label">Plan Level</label>
              <select
                className="form-input text-sm"
                value={planLevel}
                onChange={e => setPlanLevel(e.target.value as "city" | "hub")}
                disabled={readOnly}
              >
                <option value="city">City Level</option>
                <option value="hub">Hub Level</option>
              </select>
            </div>
          </div>
          <div className="form-group mb-3">
            <label className="form-label">Cities</label>
            <div className="flex flex-wrap gap-2">
              {cities.length ? (
                cities.map(c => (
                  <button
                    key={c}
                    type="button"
                    className={`btn btn-sm ${selectedCities.includes(c) ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => toggleCity(c)}
                    disabled={readOnly || (isReplacement && selectedCities.length > 0 && !selectedCities.includes(c) && stage === "upload")}
                  >
                    {c}
                  </button>
                ))
              ) : (
                <span className="text-xs text-muted">{nplLoading ? "Loading cities…" : "No cities available"}</span>
              )}
            </div>
          </div>
          {selectedCities.length > 0 && (planLevel === "hub" || planLevel === "city") && (
            <div className="mb-4 rounded border p-3" style={{ borderColor: "var(--border)" }}>
              <p className="text-xs font-semibold mb-2">Hub multiselect per city (optional — forces split)</p>
              {selectedCities.map(city => (
                <div key={city} className="mb-2">
                  <div className="text-xs text-muted mb-1">{city}</div>
                  <div className="flex flex-wrap gap-1">
                    {(cityHubs[city] || []).map(hub => (
                      <button
                        key={hub}
                        type="button"
                        className={`btn btn-sm ${(cityHubs[city] || []).includes(hub) ? "btn-primary" : "btn-secondary"}`}
                        style={{ fontSize: "0.65rem", padding: "0.15rem 0.4rem" }}
                        onClick={() => toggleCityHub(city, hub)}
                        disabled={readOnly}
                      >
                        {hub}
                      </button>
                    ))}
                    {!cityHubs[city]?.length && <span className="text-xs text-muted">Loading hubs…</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-2 mb-4">
            <button type="button" className="btn btn-secondary btn-sm" onClick={downloadTemplate} disabled={readOnly || busy === "template"}>
              <Download size={13} /> Download template
            </button>
            <label className="btn btn-primary btn-sm" style={{ cursor: readOnly ? "not-allowed" : "pointer" }}>
              <Upload size={13} /> Upload filled file
              <input type="file" accept=".xlsx" style={{ display: "none" }} onChange={handleUpload} disabled={readOnly || !!busy} />
            </label>
          </div>
        </>
      )}

      {stage === "split" && hubRows.length > 0 && (
        <>
          {Object.keys(zeroSal).length > 0 && (
            <div className="alert alert-warning text-xs mb-3">
              Zero salience hubs (equal split): {JSON.stringify(zeroSal)}
            </div>
          )}
          <div className="table-wrap mb-3" style={{ maxHeight: 360, overflow: "auto" }}>
            <table>
              <thead>
                <tr>
                  {hubColumns.map(c => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {hubRows.map((row, i) => (
                  <tr key={i}>
                    {hubColumns.map(c => (
                      <td key={c}>
                        <input
                          className="form-input"
                          style={{ fontSize: "0.72rem", padding: "0.2rem 0.35rem", minWidth: 48 }}
                          value={String(row[c] ?? "")}
                          onChange={e => editCell(i, c, e.target.value)}
                          disabled={readOnly}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setStage("dates")} disabled={readOnly}>
            Next: Launch dates <ChevronRight size={13} />
          </button>
        </>
      )}

      {stage === "dates" && (
        <>
          <div className="form-group mb-3" style={{ maxWidth: 280 }}>
            <label className="form-label">Launch date (Monday, min T+4)</label>
            <input
              type="date"
              className="form-input"
              value={launchDate}
              min={earliestDate}
              onChange={e => setLaunchDate(e.target.value)}
              disabled={readOnly}
            />
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setStage("confirm")} disabled={readOnly}>
            Review &amp; confirm <ChevronRight size={13} />
          </button>
        </>
      )}

      {stage === "confirm" && (
        <>
          <p className="text-sm mb-3">
            Submit <strong>{hubRows.length}</strong> hub rows as <strong>{subType}</strong> · launch {launchDate}
            {isReplacement && oldPid && newPid && (
              <> · replace {oldPid} → {newPid} ({splitPct}% to new)</>
            )}
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            <button type="button" className="btn btn-secondary btn-sm" onClick={checkDuplicates} disabled={readOnly || busy === "dupes"}>
              Check duplicates
            </button>
            <button type="button" className="btn btn-success" onClick={submit} disabled={readOnly || busy === "submit"}>
              {busy === "submit" ? "Submitting…" : "Confirm & Submit"}
            </button>
          </div>
          {dupes && dupes.length > 0 && (
            <div className="alert alert-warning text-xs mb-3">
              <strong>Existing log entries:</strong>
              <ul className="mt-1 pl-4">
                {dupes.slice(0, 5).map((d, i) => (
                  <li key={i}>{JSON.stringify(d)}</li>
                ))}
              </ul>
            </div>
          )}
          {emailResult && (
            <div className="alert alert-info text-xs">
              <div className="flex items-center gap-1 font-semibold mb-1">
                <Mail size={13} /> Email notification
              </div>
              {emailResult.skipped ? (
                <p>{emailResult.reason || "Emails skipped — configure SMTP in Settings."}</p>
              ) : (
                <div className="grid-2 gap-2">
                  <div>
                    <strong>Planners:</strong>{" "}
                    {emailResult.planner?.status === "sent"
                      ? `Sent to ${(emailResult.planner.recipients || []).join(", ")}`
                      : emailResult.planner?.error || "Not sent"}
                  </div>
                  <div>
                    <strong>Admin:</strong>{" "}
                    {emailResult.admin?.status === "sent"
                      ? `Sent to ${(emailResult.admin.recipients || []).join(", ")}`
                      : emailResult.admin?.error || "Not sent"}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
