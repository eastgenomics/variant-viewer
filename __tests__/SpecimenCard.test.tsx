import { render, screen } from "@testing-library/react";
import SpecimenCard from "@/components/SpecimenCard";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: jest.fn(), push: jest.fn() }),
}));

jest.mock("@/app/patients/[id]/VariantTable", () => {
  return function MockVariantTable() {
    return <div data-testid="variant-table" />;
  };
});

const specimen = {
  id: 1,
  name: "SPEC_001",
  vcf_filename: "test.vcf.gz",
  s3_key: "uploads/test.vcf.gz",
  pipeline_key: "dragen_germline",
  case_type: "germline",
  tissue: "blood",
  sequencing_date: "2026-01-15",
  ingested_at: "2026-04-01T12:00:00Z",
  workflow_status: "pending",
  workflow_updated_at: null,
  variant_count: 500,
};

describe("SpecimenCard", () => {
  it("does not contain the word 'sample' anywhere", () => {
    const { container } = render(
      <SpecimenCard specimen={specimen} patientId={1} defaultFilters={{}} pipelineKey="dragen_germline" />
    );
    const text = container.textContent?.toLowerCase() ?? "";
    expect(text).not.toContain("sample");
  });
});
