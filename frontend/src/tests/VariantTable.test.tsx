import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import VariantTable from "../components/VariantTable";

beforeEach(() => { vi.restoreAllMocks(); });

describe("VariantTable", () => {
  it("renders rows after fetch", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [{
          id: 1, chrom: "17", pos: 43094077, ref: "A", alt: "T",
          gene: "BRCA1", consequence: "missense_variant",
          hgvs_c: "c.5096G>A", hgvs_p: "p.Arg1699Gln",
          gnomad_af: 0.000012, clinvar_sig: null,
          revel_score: 0.892, spliceai_max: 0.01,
          classification: null, score: null, framework: null, locked_at: null,
        }],
        total: 1, limit: 50, offset: 0,
      }),
    }));
    render(
      <MemoryRouter>
        <VariantTable
          sampleId={10}
          patientId={1}
          defaultFilters={{ gnomad_af_max: 0.01, consequences: "", clinvar_exclude: "" }}
          pipelineKey="dragen_germline"
        />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("BRCA1")).toBeInTheDocument());
  });

  it("shows empty state when no variants match", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
    }));
    render(
      <MemoryRouter>
        <VariantTable
          sampleId={10}
          patientId={1}
          defaultFilters={{ gnomad_af_max: 0.01, consequences: "", clinvar_exclude: "" }}
          pipelineKey={null}
        />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByText(/no variants match/i)).toBeInTheDocument()
    );
  });
});
