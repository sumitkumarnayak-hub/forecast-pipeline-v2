"use client";

import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

type Props = {
  label: string;
  options: string[];
  selected: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  maxHeight?: number;
};

export default function FilterChipSelect({
  label,
  options,
  selected,
  onChange,
  placeholder = "Search…",
  maxHeight = 160,
}: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(o => o.toLowerCase().includes(q));
  }, [options, query]);

  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter(v => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  const clearAll = () => onChange([]);

  return (
    <div className="filter-chip-select">
      <div className="filter-chip-label">{label}</div>

      {selected.length > 0 && (
        <div className="filter-chip-row">
          {selected.map(v => (
            <button key={v} type="button" className="filter-chip" onClick={() => toggle(v)} title="Remove">
              <span>{v}</span>
              <X size={12} />
            </button>
          ))}
          <button type="button" className="filter-chip-clear" onClick={clearAll}>
            Clear
          </button>
        </div>
      )}

      <div className="filter-chip-search-wrap">
        <Search size={14} className="filter-chip-search-icon" />
        <input
          className="filter-chip-search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
        />
      </div>

      {(open || query) && (
        <div className="filter-chip-options" style={{ maxHeight }}>
          {filtered.length === 0 ? (
            <div className="filter-chip-empty text-xs text-muted">No matches</div>
          ) : (
            filtered.map(opt => {
              const active = selected.includes(opt);
              return (
                <button
                  key={opt}
                  type="button"
                  className={`filter-chip-option${active ? " active" : ""}`}
                  onClick={() => toggle(opt)}
                >
                  <span className="filter-chip-check">{active ? "✓" : ""}</span>
                  <span className="truncate">{opt}</span>
                </button>
              );
            })
          )}
        </div>
      )}

      {open && !query && (
        <button type="button" className="filter-chip-dismiss" onClick={() => setOpen(false)}>
          Done
        </button>
      )}
    </div>
  );
}
