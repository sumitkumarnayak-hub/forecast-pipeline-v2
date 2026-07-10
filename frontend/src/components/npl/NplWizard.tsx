"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

/**
 * Structured error logger. Keeps a consistent, greppable shape
 * (`[NplWizard:<scope>]`) so failures are easy to trace in aggregated
 * logs (e.g. Sentry / Datadog / browser console) instead of being
 * swallowed silently.
 */
function logError(scope: string, error: unknown, context?: Record<string, unknown>) {
  // eslint-disable-next-line no-console
  console.error(`[NplWizard:${scope}]`, { error, ...context });
}

function extractErrorMessage(err: unknown, fallback: string): string {
  const error = err as { response?: { data?: { detail?: string | string[] } }; message?: string };
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.join("; ");
  if (typeof detail === "string" && detail) return detail;
  if (error?.message) return error.message;
  return fallback;
}

function stageLabels(subType: NplWizardProps["subType"]): string[] {
  if (subType === "Replacement") {
    return ["1 · Old & New SKU", "2 · Upload", "3 · Hub Split", "4 · Launch Date", "5 · Confirm"];
  }
  return ["1 · Upload", "2 · Hub Split", "3 · Launch Date", "4 · Confirm"];
}

interface SyncStep {
  id: "sheets" | "db" | "email";
  label: string;
  status: "idle" | "loading" | "success" | "error";
  message?: string;
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
  const [planLevel, setPlanLevel] = useState<"city" | "hub" | "">("");
  const [selectedCities, setSelectedCities] = useState<string[]>([]);

  // --- Hub catalog vs. hub selection --------------------------------------
  // These used to be conflated into a single `cityHubs` object, which caused
  // the "hub disappears when clicked" bug: the button list was rendered from
  // the same array used to test "is this hub selected", so toggling a hub
  // filtered it out of its own render source.
  //
  // `availableHubs`  -> the catalog of hubs returned by the API for a city.
  // `selectedHubs`   -> the subset of those hubs the user has chosen (this is
  //                     what actually gets sent to the backend as forced_hubs).
  // `hubsLoading` / `hubsError` -> per-city fetch status so the UI can show a
  //                     spinner or a retry action instead of failing silently.
  const [availableHubs, setAvailableHubs] = useState<Record<string, string[]>>({});
  const [selectedHubs, setSelectedHubs] = useState<Record<string, string[]>>({});
  const [hubsLoading, setHubsLoading] = useState<Record<string, boolean>>({});
  const [hubsError, setHubsError] = useState<Record<string, string>>({});

  // Tracks, per city, which category the currently-cached hubs belong to and
  // the latest in-flight request id. Used to (a) invalidate the cache when
  // the category changes and (b) discard stale responses if a fetch for the
  // same city is superseded by a newer one (race protection).
  const hubLoadStateRef = useRef<Record<string, { category: string; requestId: number }>>({});

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
  const [previewRows, setPreviewRows] = useState<Record<string, unknown>[] | null>(null);
  const [previewCols, setPreviewCols] = useState<string[]>([]);
  const [emailResult, setEmailResult] = useState<{
    planner?: EmailResult;
    admin?: EmailResult;
    skipped?: boolean;
    reason?: string;
  } | null>(null);

  const SYNC_STEPS_DEFAULT: SyncStep[] = [
    { id: "sheets", label: "Sync to Google Sheets (Launch_Output & Submission_Log)", status: "idle" },
    { id: "db", label: "Save submission record to Database", status: "idle" },
    { id: "email", label: "Trigger email notification workflow", status: "idle" },
  ];

  const [syncSteps, setSyncSteps] = useState<SyncStep[]>(SYNC_STEPS_DEFAULT);
  const [showSyncSteps, setShowSyncSteps] = useState(false);
  const [showSyncBanner, setShowSyncBanner] = useState(false);

  // Use a ref so the stage-change effect captures the latest function references
  const confirmActionsRef = useRef<{ checkDuplicates: () => void; previewSync: () => void } | null>(null);

  useEffect(() => {
    if (stage === "confirm") {
      // Small defer so the functions are defined and ref is updated
      const timer = setTimeout(() => {
        confirmActionsRef.current?.checkDuplicates();
        confirmActionsRef.current?.previewSync();
      }, 50);
      return () => clearTimeout(timer);
    } else {
      setShowSyncSteps(false);
      setSyncSteps(SYNC_STEPS_DEFAULT);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

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

  const hubCategory = expansionCategory || category || "";

  /**
   * Fetches the hub catalog for a single city + category, guarded against
   * stale responses via a per-city request id. Exposed (not just used
   * inline in the effect) so the "Retry" button can call it directly.
   */
  const fetchHubsForCity = useCallback((city: string, cat: string) => {
    const prevState = hubLoadStateRef.current[city];
    const requestId = (prevState?.requestId ?? 0) + 1;
    hubLoadStateRef.current[city] = { category: cat, requestId };

    setHubsLoading(prev => ({ ...prev, [city]: true }));
    setHubsError(prev => ({ ...prev, [city]: "" }));

    api
      .get("/api/new-product-launch/wizard/hubs", { params: { city, category: cat || undefined } })
      .then(({ data }) => {
        // A newer request for this city has already superseded this one
        // (e.g. category changed again while this call was in flight) —
        // drop the response rather than overwrite fresher data.
        if (hubLoadStateRef.current[city]?.requestId !== requestId) return;
        setAvailableHubs(prev => ({ ...prev, [city]: data.hubs || [] }));
        setHubsLoading(prev => ({ ...prev, [city]: false }));
      })
      .catch((err: unknown) => {
        if (hubLoadStateRef.current[city]?.requestId !== requestId) return;
        logError("fetchHubsForCity", err, { city, category: cat });
        setHubsError(prev => ({ ...prev, [city]: extractErrorMessage(err, "Failed to load hubs") }));
        setHubsLoading(prev => ({ ...prev, [city]: false }));
      });
  }, []);

  useEffect(() => {
    if (!selectedCities.length) return;
    selectedCities.forEach(city => {
      const loadState = hubLoadStateRef.current[city];
      const isCachedForCurrentCategory = loadState?.category === hubCategory && (availableHubs[city]?.length ?? 0) > 0;
      const isAlreadyInFlight = hubsLoading[city];
      if (isCachedForCurrentCategory || isAlreadyInFlight) return;
      fetchHubsForCity(city, hubCategory);
    });
    // availableHubs / hubsLoading are read for the cache/in-flight guard only;
    // including them here would re-run this effect on every fetch completion.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCities, hubCategory, fetchHubsForCity]);

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
        Object.entries(selectedHubs).filter(([, hubs]) => hubs.length > 0),
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
              cities_hubs: forcedHubs,
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
    } catch (err) {
      logError("downloadTemplate", err, { planLevel, category: expansionCategory || category, selectedCities });
      setMsg({ text: extractErrorMessage(err, "Template download failed"), type: "danger" });
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

      const forcedHubs = Object.fromEntries(
        Object.entries(selectedHubs).filter(([, hubs]) => hubs.length > 0),
      );

      if (planLevel === "city") {
        setStepState({ step: "split", status: "loading", message: "Calculating hub split from salience data..." });
        const split = await api.post("/api/new-product-launch/wizard/split-city", {
          city_rows: data.rows,
          forced_hubs: Object.keys(forcedHubs).length ? forcedHubs : null,
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
      const errorMsg = extractErrorMessage(err, "Upload failed");
      logError("handleUpload", err, { planLevel, fileName: file.name });
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

  /** Toggles a hub in/out of the user's *selection* for a city. Never
   * touches `availableHubs`, which always remains the full catalog fetched
   * from the API — this is the fix for the "hub vanishes on click" bug. */
  const toggleSelectedHub = (city: string, hub: string) => {
    setSelectedHubs(prev => {
      const current = prev[city] || [];
      const next = current.includes(hub) ? current.filter(h => h !== hub) : [...current, hub];
      return { ...prev, [city]: next };
    });
  };

  const checkDuplicates = async () => {
    if (busy) return;
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
    } catch (err) {
      logError("checkDuplicates", err, { subType, planLevel });
      setMsg({ text: extractErrorMessage(err, "Duplicate check failed"), type: "danger" });
      setStepState({ step: "dupes", status: "error", message: "Duplicate check failed" });
    }
    setBusy("");
  };

  const previewSync = async () => {
    if (busy) return;
    setBusy("preview");
    setStepState({ step: "preview", status: "loading", message: "Generating sync preview..." });
    setPreviewRows(null);
    try {
      const dated = hubRows.map(r => ({ ...r, launch_date: launchDate }));
      const { data } = await api.post("/api/new-product-launch/wizard/preview-sync", {
        hub_rows: dated,
        sub_type: subType,
        launch_date: launchDate,
      });
      setPreviewRows(data.rows || []);
      setPreviewCols(data.columns || []);
      setMsg({ text: `Sync preview generated successfully (${data.rows?.length || 0} rows)`, type: "success" });
      setStepState({ step: "preview", status: "success", message: "Preview loaded" });
    } catch (err: unknown) {
      logError("previewSync", err, { subType, launchDate });
      setMsg({ text: extractErrorMessage(err, "Preview sync failed"), type: "danger" });
      setStepState({ step: "preview", status: "error", message: "Preview sync failed" });
    }
    setBusy("");
  };

  // Keep ref in sync so stage-change useEffect can call these safely
  confirmActionsRef.current = { checkDuplicates, previewSync };

  const submit = async () => {
    if (busy) return;
    setBusy("submit");
    setShowSyncSteps(true);
    setSyncSteps([
      { id: "sheets", label: "Sync to Google Sheets (Launch_Output & Submission_Log)", status: "loading" },
      { id: "db", label: "Save submission record to Database", status: "idle" },
      { id: "email", label: "Trigger email notification workflow", status: "idle" },
    ]);
    setStepState({ step: "submit", status: "loading", message: "Syncing data to Google Sheets & database..." });

    try {
      const dated = hubRows.map(r => ({ ...r, launch_date: launchDate }));
      const { data } = await api.post("/api/new-product-launch/wizard/submit", {
        hub_rows: dated,
        sub_type: subType,
        launch_date: launchDate,
      });

      // Update steps to success
      setSyncSteps([
        { id: "sheets", label: "Sync to Google Sheets (Launch_Output & Submission_Log)", status: "success", message: `${data.steps?.sheets?.duration_ms || 0}ms` },
        { id: "db", label: "Save submission record to Database", status: "success", message: `${data.steps?.db?.duration_ms || 0}ms` },
        { id: "email", label: "Trigger email notification workflow", status: data.email?.status === "skipped" ? "idle" : "success", message: data.email?.status === "skipped" ? "Skipped" : "Queued" },
      ]);

      setEmailResult(data.email || null);
      setMsg({ text: `Synced successfully! Submission ID: ${data.submission_id}`, type: "success" });
      setStepState({ step: "submit", status: "success", message: "Successfully synced" });
      setShowSyncBanner(true);

      // Reset the wizard after a short delay (e.g. 2.5 seconds) so user can see step-wise green checkmarks
      setTimeout(() => {
        setStage(isReplacement ? "setup" : "upload");
        setHubRows([]);
        setDupes(null);
        setPreviewRows(null);
        setPreviewCols([]);
        setShowSyncSteps(false);
      }, 2500);

    } catch (err: any) {
      logError("submit", err, { subType, launchDate });
      const errDetail = extractErrorMessage(err, "Sync failed");
      setMsg({ text: errDetail, type: "danger" });
      setStepState({ step: "submit", status: "error", message: errDetail });

      // Handle step-wise error mapping from backend HTTPException
      const backendSteps = err.response?.data?.detail?.steps;
      if (backendSteps) {
        setSyncSteps([
          {
            id: "sheets",
            label: "Sync to Google Sheets (Launch_Output & Submission_Log)",
            status: backendSteps.sheets?.status || "error",
            message: backendSteps.sheets?.error || (backendSteps.sheets?.status === "success" ? "Success" : undefined)
          },
          {
            id: "db",
            label: "Save submission record to Database",
            status: backendSteps.db?.status || "idle",
            message: backendSteps.db?.error || (backendSteps.db?.status === "success" ? "Success" : undefined)
          },
          {
            id: "email",
            label: "Trigger email notification workflow",
            status: backendSteps.email?.status || "idle",
            message: backendSteps.email?.error || (backendSteps.email?.status === "success" ? "Success" : undefined)
          },
        ]);
      } else {
        // Fallback: mark current/active step as error
        setSyncSteps(prev =>
          prev.map(step => (step.status === "loading" || step.status === "idle" ? { ...step, status: "error", message: errDetail } : step))
        );
      }
    }
    setBusy("");
  };

  const toggleCity = (c: string) => {
    setSelectedCities(prev => {
      const isCurrentlySelected = prev.includes(c);
      if (isCurrentlySelected) {
        // Clean up hub selections for a city removed from the plan so a
        // stale selection can't leak into forced_hubs / cities_hubs later.
        setSelectedHubs(prevHubs => {
          if (!(c in prevHubs)) return prevHubs;
          const next = { ...prevHubs };
          delete next[c];
          return next;
        });
        return prev.filter(x => x !== c);
      }
      return [...prev, c];
    });
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
    try {
      const oPid = allProducts.find(p => p.product_name === oldProductName && p.category === oldCategory)?.product_id
        || await resolveProductId(oldCategory, oldProductName);
      const nPid = allProducts.find(p => p.product_name === newProductName && p.category === newCategory)?.product_id
        || await resolveProductId(newCategory, newProductName);
      setOldPid(oPid);
      setNewPid(nPid);
      setCategory(newCategory);
      setStage("upload");
      setMsg({ text: "", type: "" });
    } catch (err) {
      logError("finishReplacementSetup", err, { oldCategory, newCategory, oldProductName, newProductName });
      setMsg({ text: extractErrorMessage(err, "Failed to resolve product IDs"), type: "danger" });
    }
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
      {showSyncBanner && (
        <div className="alert alert-warning mb-4 text-sm flex flex-col gap-2 p-4 border border-amber-200 rounded-xl bg-amber-50 text-amber-900 shadow-sm animate-fade-in">
          <div className="flex items-center justify-between w-full">
            <span className="font-semibold flex items-center gap-2">
              {planLevel === "hub" 
                ? "⚠️ Hub Plan is synced! Please update the masters list and send email."
                : "⚠️ FF Input is synced! Please update the masters list and send email."
              }
            </span>
            <button 
              className="btn btn-sm btn-secondary cursor-pointer"
              onClick={() => setShowSyncBanner(false)}
              style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
            >
              Dismiss
            </button>
          </div>
          <p className="text-xs text-amber-800 leading-normal">
            The wizard has successfully synced new product configurations to the {planLevel === "hub" ? "Hub_Plan" : "City_Plan (FF Input)"} sheet. Please update the master worksheets to reflect the new configurations.
          </p>
        </div>
      )}
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
              <label className="form-label">Plan Level <span className="text-danger">*</span></label>
              <select
                className="form-input text-sm"
                value={planLevel}
                onChange={e => setPlanLevel(e.target.value as "city" | "hub" | "")}
                disabled={readOnly}
              >
                <option value="">Select Plan Level</option>
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
          {selectedCities.length > 0 && (
            <div className="mb-4 rounded border p-3" style={{ borderColor: "var(--border)" }}>
              <p className="text-xs font-semibold mb-2">Hub multiselect per city (optional — forces split)</p>
              {selectedCities.map(city => {
                const hubs = availableHubs[city] || [];
                const selected = selectedHubs[city] || [];
                const loading = hubsLoading[city];
                const error = hubsError[city];
                return (
                  <div key={city} className="mb-2">
                    <div className="text-xs text-muted mb-1 flex items-center gap-2">
                      <span>{city}</span>
                      {selected.length > 0 && (
                        <span className="badge badge-blue" style={{ fontSize: "0.6rem" }}>
                          {selected.length} selected
                        </span>
                      )}
                    </div>
                    {loading && (
                      <div className="flex items-center gap-2 text-xs text-muted">
                        <span className="spinner" style={{ width: 12, height: 12 }} />
                        Loading hubs…
                      </div>
                    )}
                    {!loading && error && (
                      <div className="flex items-center gap-2 text-xs" style={{ color: "var(--danger, #c0392b)" }}>
                        <span>{error}</span>
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          style={{ fontSize: "0.65rem", padding: "0.1rem 0.4rem" }}
                          onClick={() => fetchHubsForCity(city, hubCategory)}
                        >
                          Retry
                        </button>
                      </div>
                    )}
                    {!loading && !error && (
                      <div className="flex flex-wrap gap-1">
                        {hubs.length ? (
                          hubs.map(hub => {
                            const isSelected = selected.includes(hub);
                            return (
                              <button
                                key={hub}
                                type="button"
                                className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-secondary"}`}
                                style={{ fontSize: "0.65rem", padding: "0.15rem 0.4rem" }}
                                onClick={() => toggleSelectedHub(city, hub)}
                                disabled={readOnly}
                                aria-pressed={isSelected}
                              >
                                {isSelected ? "✓ " : ""}{hub}
                              </button>
                            );
                          })
                        ) : (
                          <span className="text-xs text-muted">No hubs found for this city/category</span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div className="flex gap-2 mb-4">
            <button 
              type="button" 
              className="btn btn-secondary btn-sm" 
              onClick={downloadTemplate} 
              disabled={readOnly || busy === "template" || !planLevel}
            >
              <Download size={13} /> Download template
            </button>
            <label 
              className="btn btn-primary btn-sm" 
              style={{ cursor: (readOnly || !planLevel) ? "not-allowed" : "pointer", opacity: (!planLevel) ? 0.6 : 1 }}
            >
              <Upload size={13} /> {(!planLevel) ? "Select Plan Level first" : "Upload filled file"}
              {planLevel && (
                <input type="file" accept=".xlsx" style={{ display: "none" }} onChange={handleUpload} disabled={readOnly || !!busy} />
              )}
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
          <p className="text-sm mb-2">
            Sync <strong>{hubRows.length}</strong> hub rows as <strong>{subType}</strong> · launch {launchDate}
            {isReplacement && oldPid && newPid && (
              <> · replace {oldPid} → {newPid} ({splitPct}% to new)</>
            )}
          </p>

          {/* Duplicate check status banner */}
          {busy === "dupes" && (
            <div className="alert alert-info text-xs mb-3 flex items-center gap-2">
              <span className="spinner" style={{ width: 12, height: 12 }} />
              Checking for duplicate submissions in log…
            </div>
          )}
          {dupes && dupes.length > 0 && (
            <div className="alert alert-warning text-xs mb-3">
              <strong>⚠ Duplicate submissions detected ({dupes.length}):</strong>
              <ul className="mt-1 pl-4">
                {dupes.slice(0, 5).map((d, i) => (
                  <li key={i} style={{ fontFamily: "monospace" }}>{JSON.stringify(d)}</li>
                ))}
              </ul>
              <p className="mt-1">Review the existing entries before syncing.</p>
            </div>
          )}
          {!busy && dupes !== null && dupes.length === 0 && (
            <div className="alert alert-success text-xs mb-3">✓ No duplicate submissions found</div>
          )}

          {/* Preview loading status */}
          {busy === "preview" && (
            <div className="alert alert-info text-xs mb-3 flex items-center gap-2">
              <span className="spinner" style={{ width: 12, height: 12 }} />
              Generating sync preview…
            </div>
          )}

          {/* Step-wise sync progress tracker */}
          {showSyncSteps && (
            <div className="mb-4 p-3 border rounded" style={{ background: "rgba(0,0,0,0.1)" }}>
              <p className="text-xs font-semibold mb-2 uppercase tracking-wider text-muted">Sync Progress</p>
              <div className="flex flex-col gap-2">
                {syncSteps.map((step) => {
                  const icon =
                    step.status === "loading" ? <span className="spinner" style={{ width: 12, height: 12, display: "inline-block" }} /> :
                    step.status === "success" ? <span style={{ color: "var(--color-success, #22c55e)", fontWeight: 700 }}>✓</span> :
                    step.status === "error" ? <span style={{ color: "var(--color-danger, #ef4444)", fontWeight: 700 }}>✗</span> :
                    <span style={{ opacity: 0.35 }}>○</span>;
                  return (
                    <div key={step.id} className="flex items-start gap-2 text-xs">
                      <span style={{ minWidth: 16, marginTop: 1 }}>{icon}</span>
                      <div>
                        <span className={step.status === "error" ? "text-danger font-semibold" : step.status === "success" ? "font-semibold" : "text-muted"}>
                          {step.label}
                        </span>
                        {step.message && (
                          <span className="text-muted ml-1">
                            — {step.message}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex flex-wrap gap-2 mb-3">
            <button type="button" className="btn btn-secondary btn-sm" onClick={previewSync} disabled={readOnly || !!busy}>
              {busy === "preview" ? "Loading Preview…" : "Preview Sync"}
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={checkDuplicates} disabled={readOnly || !!busy}>
              {busy === "dupes" ? "Checking…" : "Re-check Duplicates"}
            </button>
            <button type="button" className="btn btn-success btn-sm" onClick={submit} disabled={readOnly || !!busy}>
              {busy === "submit" ? "Syncing…" : "Sync Now"}
            </button>
          </div>

          {/* Sheet log preview table */}
          {previewRows && previewRows.length > 0 && (
            <div className="mb-4">
              <h5 className="text-xs font-semibold mb-2 text-muted uppercase tracking-wider">
                Log Preview — Exact columns to be written to Google Sheets
              </h5>
              <div className="table-wrap border rounded" style={{ maxHeight: 280, overflow: "auto" }}>
                <table className="table-sm">
                  <thead>
                    <tr style={{ background: "rgba(255, 255, 255, 0.05)" }}>
                      {previewCols.map(c => (
                        <th key={c} style={{ fontSize: "0.68rem", padding: "0.35rem 0.4rem", whiteSpace: "nowrap" }}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, i) => (
                      <tr key={i}>
                        {previewCols.map(c => (
                          <td key={c} style={{ fontSize: "0.65rem", padding: "0.25rem 0.4rem", whiteSpace: "nowrap" }}>
                            {String(row[c] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}