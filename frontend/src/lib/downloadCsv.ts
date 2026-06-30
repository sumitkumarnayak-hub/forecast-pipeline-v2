/** Export row objects to a CSV file download (client-side). */
export function downloadCsv(
  rows: Record<string, unknown>[],
  columns: string[],
  filename: string,
): void {
  if (!rows.length || !columns.length) return;

  const escape = (val: unknown) => {
    const s = val == null ? "" : String(val);
    if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  };

  const lines = [
    columns.join(","),
    ...rows.map(row => columns.map(c => escape(row[c])).join(",")),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
