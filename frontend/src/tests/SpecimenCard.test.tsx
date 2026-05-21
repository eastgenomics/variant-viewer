import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import SpecimenCard from "../components/SpecimenCard";
import type { SampleDetail } from "../lib/api";

vi.mock("../lib/api");

beforeEach(() => {
  // Stub fetch so VariantTable's useEffect doesn't cause act() warnings
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
  }));
});

afterEach(() => { vi.restoreAllMocks(); });

const specimen: SampleDetail = {
  id: 5,
  name: "SPEC_001",
  s3_key: "runs/2026-01-01/sample.vcf.gz",
  pipeline_key: "dragen_germline",
  case_type: "germline",
  tissue: "blood",
  sequencing_date: "2026-01-01",
  ingested_at: "2026-01-02T10:00:00Z",
  patient: { id: 1, lab_number: "LAB-001", name: null },
  workflow_status: "pending",
  variant_count: 42,
};

describe("SpecimenCard", () => {
  it("renders specimen name", async () => {
    render(
      <MemoryRouter>
        <SpecimenCard specimen={specimen} patientId={1} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("SPEC_001")).toBeInTheDocument());
  });

  it("renders variant count", async () => {
    render(
      <MemoryRouter>
        <SpecimenCard specimen={specimen} patientId={1} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/42 variants/i)).toBeInTheDocument());
  });

  it("renders case type badge", async () => {
    render(
      <MemoryRouter>
        <SpecimenCard specimen={specimen} patientId={1} />
      </MemoryRouter>
    );
    await waitFor(() => {
      const germlineEls = screen.getAllByText(/germline/i);
      expect(germlineEls.length).toBeGreaterThan(0);
    });
  });
});
