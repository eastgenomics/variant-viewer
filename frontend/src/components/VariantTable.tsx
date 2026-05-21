import { useState, useEffect, useCallback } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import { Link } from "react-router-dom";
import ClassificationBadge from "./ClassificationBadge";
import { authHeaders } from "../lib/api";
import {
  formatGnomadAf, gnomadAfClass,
  formatRevel, revelClass,
  formatSpliceAi, spliceAiClass,
} from "../lib/display-utils";
import type { VariantRow, PipelineFilters } from "../lib/api";

const col = createColumnHelper<VariantRow>();

const COLUMNS = [
  col.accessor("gene", {
    header: "Gene",
    cell: (i) => (
      <span className="font-medium text-gray-900">{i.getValue() ?? "—"}</span>
    ),
  }),
  col.accessor("hgvs_c", {
    header: "HGVSc",
    cell: (i) => (
      <span className="font-mono text-xs text-gray-700">{i.getValue() ?? "—"}</span>
    ),
  }),
  col.accessor("hgvs_p", {
    header: "HGVSp",
    cell: (i) => (
      <span className="font-mono text-xs text-gray-700">{i.getValue() ?? "—"}</span>
    ),
  }),
  col.accessor("consequence", {
    header: "Consequence",
    cell: (i) => (
      <span className="text-xs text-gray-600">
        {i.getValue()?.replace(/_/g, " ") ?? "—"}
      </span>
    ),
  }),
  col.accessor("gnomad_af", {
    header: "gnomAD AF",
    cell: (i) => {
      const v = i.getValue();
      if (v == null) return <span className="text-gray-400">—</span>;
      return (
        <span className={`font-mono text-xs ${gnomadAfClass(v)}`}>
          {formatGnomadAf(v)}
        </span>
      );
    },
  }),
  col.accessor("revel_score", {
    header: "REVEL",
    cell: (i) => {
      const v = i.getValue();
      if (v == null) return <span className="text-gray-400">—</span>;
      return <span className={`font-mono text-xs ${revelClass(v)}`}>{formatRevel(v)}</span>;
    },
  }),
  col.accessor("spliceai_max", {
    header: "SpliceAI",
    cell: (i) => {
      const v = i.getValue();
      if (v == null) return <span className="text-gray-400">—</span>;
      return <span className={`font-mono text-xs ${spliceAiClass(v)}`}>{formatSpliceAi(v)}</span>;
    },
  }),
  col.accessor("clinvar_sig", {
    header: "ClinVar",
    cell: (i) => (
      <span className="text-xs text-gray-600">{i.getValue() ?? "—"}</span>
    ),
  }),
  col.accessor("chrom", {
    header: "Location",
    cell: (i) => (
      <span className="font-mono text-xs text-gray-500">
        {i.getValue()}:{i.row.original.pos} {i.row.original.ref}&gt;
        {i.row.original.alt}
      </span>
    ),
  }),
  col.accessor("classification", {
    header: "Classification",
    cell: (i) => <ClassificationBadge classification={i.getValue() ?? null} />,
  }),
];

const PAGE_SIZE = 50;

export default function VariantTable({
  sampleId,
  patientId,
  defaultFilters,
  pipelineKey,
}: {
  sampleId: number;
  patientId: number;
  defaultFilters: PipelineFilters;
  pipelineKey: string | null;
}) {
  const [data, setData] = useState<VariantRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [filters, setFilters] = useState<PipelineFilters>(defaultFilters);
  const [geneInput, setGeneInput] = useState("");
  const [sortBy, setSortBy] = useState("chrom"); // TODO: wire to column header clicks (PR 12)
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Reset filters and pagination when the sample changes
  useEffect(() => {
    setFilters(defaultFilters);
    setGeneInput("");
    setPageIndex(0);
  }, [sampleId, defaultFilters]); // defaultFilters is memoized in SpecimenCard — safe to include

  const fetchVariants = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(pageIndex * PAGE_SIZE),
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      if (filters.gnomad_af_max != null)
        q.set("gnomad_af_max", String(filters.gnomad_af_max));
      if (filters.consequences) q.set("consequences", filters.consequences);
      if (filters.clinvar_exclude) q.set("clinvar_exclude", filters.clinvar_exclude);
      if (geneInput.trim()) q.set("gene", geneInput.trim());

      const resp = await fetch(`/api/samples/${sampleId}/variants?${q}`, {
        headers: authHeaders(),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      setData(json.items);
      setTotal(json.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load variants");
    } finally {
      setLoading(false);
    }
  }, [sampleId, pageIndex, filters, geneInput, sortBy, sortDir]);

  useEffect(() => { fetchVariants(); }, [fetchVariants]);

  const pageCount = Math.ceil(total / PAGE_SIZE);

  const table = useReactTable({
    data,
    columns: COLUMNS,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    pageCount,
  });

  return (
    <div>
      {/* Filter bar */}
      <div className="bg-white border border-gray-200 rounded-lg p-3 mb-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1">
            <label className="text-xs text-gray-500">gnomAD AF ≤</label>
            <input
              type="number"
              step="0.001"
              min={0}
              max={1}
              value={filters.gnomad_af_max ?? ""}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                setFilters((f) => ({
                  ...f,
                  gnomad_af_max: Number.isNaN(val) ? null : val,
                }));
                setPageIndex(0);
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm w-20"
            />
          </div>
          <div className="flex items-center gap-1">
            <label className="text-xs text-gray-500">Gene</label>
            <input
              type="text"
              value={geneInput}
              onChange={(e) => {
                setGeneInput(e.target.value);
                setPageIndex(0);
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm w-24"
              placeholder="e.g. BRCA1"
            />
          </div>
          {pipelineKey && (
            <div className="text-xs text-gray-400 self-end pb-1">
              Preset: {pipelineKey.replace(/_/g, " ")}
            </div>
          )}
        </div>
      </div>

      {error && <div className="text-sm text-red-600 mb-2">{error}</div>}

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {table.getHeaderGroups().map((hg) =>
                  hg.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                    </th>
                  ))
                )}
                <th className="px-4 py-2 text-xs font-medium text-gray-500"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr>
                  <td
                    colSpan={COLUMNS.length + 1}
                    className="px-4 py-6 text-center text-gray-400"
                  >
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && data.length === 0 && (
                <tr>
                  <td
                    colSpan={COLUMNS.length + 1}
                    className="px-4 py-6 text-center text-gray-400"
                  >
                    No variants match the current filters.
                  </td>
                </tr>
              )}
              {!loading &&
                table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="hover:bg-gray-50">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-4 py-2">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                    <td className="px-4 py-2">
                      <Link
                        to={`/patients/${patientId}/variants/${row.original.id}`}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        Classify
                      </Link>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        <div className="border-t border-gray-200 px-4 py-2 flex items-center justify-between text-sm text-gray-600">
          <span>
            {total.toLocaleString()} variant{total !== 1 ? "s" : ""} total
          </span>
          <div className="flex items-center gap-2">
            <button
              className="btn btn-secondary text-xs"
              disabled={pageIndex === 0}
              onClick={() => setPageIndex((p) => p - 1)}
            >
              ← Prev
            </button>
            <span className="text-xs">
              Page {pageIndex + 1} of {pageCount || 1}
            </span>
            <button
              className="btn btn-secondary text-xs"
              disabled={pageIndex + 1 >= pageCount}
              onClick={() => setPageIndex((p) => p + 1)}
            >
              Next →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
