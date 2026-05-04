"use client";

import { useState, useCallback, useEffect } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
  SortingState,
  PaginationState,
} from "@tanstack/react-table";
import Link from "next/link";
import ClassificationBadge from "@/components/ClassificationBadge";
import GmsConcordance from "@/components/GmsConcordance";
import type { PipelineFilters } from "@/lib/pipeline-config";

interface VariantRow {
  id: number;
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  qual: number | null;
  filter: string | null;
  gene: string | null;
  consequence: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  gnomad_af: number | null;
  clinvar_sig: string | null;
  revel_score: number | null;
  spliceai_max: number | null;
  classification: string | null;
  classification_id: number | null;
  classification_locked_at: string | null;
  gms_concordance: [number, number, number] | null;
}

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
        <span className={`font-mono text-xs ${v > 0.01 ? "text-amber-600" : "text-gray-700"}`}>
          {v < 0.0001 ? v.toExponential(2) : v.toFixed(4)}
        </span>
      );
    },
  }),
  col.accessor("revel_score", {
    header: "REVEL",
    cell: (i) => {
      const v = i.getValue();
      if (v == null) return <span className="text-gray-400">—</span>;
      const cls =
        v >= 0.7 ? "text-red-600" : v <= 0.4 ? "text-green-700" : "text-gray-700";
      return <span className={`font-mono text-xs ${cls}`}>{v.toFixed(3)}</span>;
    },
  }),
  col.accessor("spliceai_max", {
    header: "SpliceAI",
    cell: (i) => {
      const v = i.getValue();
      if (v == null) return <span className="text-gray-400">—</span>;
      const cls = v >= 0.5 ? "text-orange-600" : "text-gray-700";
      return <span className={`font-mono text-xs ${cls}`}>{v.toFixed(3)}</span>;
    },
  }),
  col.accessor("gms_concordance", {
    header: "GMS",
    cell: (i) => <GmsConcordance value={i.getValue()} />,
    enableSorting: false,
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
        {i.getValue()}:{i.row.original.pos} {i.row.original.ref}&gt;{i.row.original.alt}
      </span>
    ),
  }),
  col.accessor("classification", {
    header: "Classification",
    cell: (i) => <ClassificationBadge classification={i.getValue() ?? null} />,
  }),
];

function formatAf(af: number | null): string {
  if (af == null) return "";
  return af < 0.0001 ? af.toExponential(2) : af.toFixed(4);
}

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
  // Filter state (initialised from pipeline preset)
  const [gnomadAfMax, setGnomadAfMax] = useState(
    String(defaultFilters.gnomad_af_max)
  );
  const [consequences, setConsequences] = useState(
    defaultFilters.consequences.join(",")
  );
  const [clinvarExclude, setClinvarExclude] = useState(
    defaultFilters.clinvar_exclude.join(",")
  );
  const [geneFilter, setGeneFilter] = useState("");

  const [data, setData] = useState<VariantRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });

  const fetchVariants = useCallback(async () => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      sample_id: String(sampleId),
      limit: String(pagination.pageSize),
      offset: String(pagination.pageIndex * pagination.pageSize),
    });

    if (sorting.length > 0) {
      params.set("sort_by", sorting[0].id);
      params.set("sort_dir", sorting[0].desc ? "DESC" : "ASC");
    }
    if (gnomadAfMax) params.set("gnomad_af_max", gnomadAfMax);
    if (consequences) params.set("consequences", consequences);
    if (clinvarExclude) params.set("clinvar_exclude", clinvarExclude);
    if (geneFilter) params.set("gene", geneFilter);

    try {
      const resp = await fetch(`/api/variants?${params}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      setData(json.rows);
      setTotal(json.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load variants");
    } finally {
      setLoading(false);
    }
  }, [
    sampleId,
    pagination,
    sorting,
    gnomadAfMax,
    consequences,
    clinvarExclude,
    geneFilter,
  ]);

  useEffect(() => {
    fetchVariants();
  }, [fetchVariants]);

  const table = useReactTable({
    data,
    columns: COLUMNS,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    rowCount: total,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    state: { pagination, sorting },
  });

  const pageCount = Math.ceil(total / pagination.pageSize);

  return (
    <div>
      {/* Filter bar */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-3">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">gnomAD AF max</label>
            <input
              type="number"
              step="0.001"
              min="0"
              max="1"
              value={gnomadAfMax}
              onChange={(e) => {
                setGnomadAfMax(e.target.value);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm w-28"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Consequences (comma-sep)
            </label>
            <input
              type="text"
              value={consequences}
              onChange={(e) => {
                setConsequences(e.target.value);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm w-64"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Exclude ClinVar (comma-sep)
            </label>
            <input
              type="text"
              value={clinvarExclude}
              onChange={(e) => {
                setClinvarExclude(e.target.value);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm w-40"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Gene</label>
            <input
              type="text"
              value={geneFilter}
              onChange={(e) => {
                setGeneFilter(e.target.value);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm w-24"
              placeholder="e.g. BRCA1"
            />
          </div>
          {pipelineKey && (
            <div className="text-xs text-gray-400 self-end pb-1.5">
              Preset: {pipelineKey.replace(/_/g, " ")}
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      {error && (
        <div className="text-sm text-red-600 mb-2">{error}</div>
      )}

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {table.getHeaderGroups().map((hg) =>
                  hg.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                      {header.column.getIsSorted() === "asc" ? " ↑" : ""}
                      {header.column.getIsSorted() === "desc" ? " ↓" : ""}
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
                        href={`/patients/${patientId}/variants/${row.original.id}`}
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

        {/* Pagination */}
        <div className="border-t border-gray-200 px-4 py-2 flex items-center justify-between text-sm text-gray-600">
          <span>
            {total.toLocaleString()} variant{total !== 1 ? "s" : ""} total
            {total > 0 &&
              ` — showing ${pagination.pageIndex * pagination.pageSize + 1}–${Math.min(
                (pagination.pageIndex + 1) * pagination.pageSize,
                total
              )}`}
          </span>
          <div className="flex items-center gap-2">
            <button
              className="btn btn-secondary text-xs"
              disabled={!table.getCanPreviousPage()}
              onClick={() => table.previousPage()}
            >
              ← Prev
            </button>
            <span className="text-xs">
              Page {pagination.pageIndex + 1} of {pageCount || 1}
            </span>
            <button
              className="btn btn-secondary text-xs"
              disabled={!table.getCanNextPage()}
              onClick={() => table.nextPage()}
            >
              Next →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
