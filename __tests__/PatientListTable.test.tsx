import { render, screen } from "@testing-library/react";
import PatientListTable from "@/components/PatientListTable";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: jest.fn(), push: jest.fn() }),
}));

const patient = {
  id: 1,
  name: "Jane Smith",
  lab_number: "LAB-2026-001",
  nhs_number: "9000000009",
  dob: "1990-05-14",
  sample_count: 2,
  latest_sample_id: 10,
  latest_sample_name: "SPECIMEN_A",
  latest_workflow_status: "pending",
  latest_ingested_at: "2026-04-01T12:00:00Z",
  pipeline_key: "dragen_germline",
};

describe("PatientListTable", () => {
  beforeEach(() => {
    render(<PatientListTable patients={[patient]} />);
  });

  it("shows MRN column header", () => {
    expect(
      screen.getByRole("columnheader", { name: /mrn/i })
    ).toBeInTheDocument();
  });

  it("does not show a Patient name column header", () => {
    expect(
      screen.queryByRole("columnheader", { name: /^patient$/i })
    ).not.toBeInTheDocument();
  });

  it("displays the lab_number (MRN) as primary identifier", () => {
    expect(screen.getByText("LAB-2026-001")).toBeInTheDocument();
  });

  it("does not display patient name in the table", () => {
    expect(screen.queryByText("Jane Smith")).not.toBeInTheDocument();
  });

  it("does not show NHS number column header", () => {
    expect(
      screen.queryByRole("columnheader", { name: /nhs/i })
    ).not.toBeInTheDocument();
  });

  it("does not display NHS number value", () => {
    expect(screen.queryByText("9000000009")).not.toBeInTheDocument();
  });

  it("shows Specimens column header instead of Samples", () => {
    expect(
      screen.getByRole("columnheader", { name: /specimens/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: /^samples$/i })
    ).not.toBeInTheDocument();
  });

  it("shows Latest Specimen column header instead of Latest Sample", () => {
    expect(
      screen.getByRole("columnheader", { name: /latest specimen/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: /latest sample/i })
    ).not.toBeInTheDocument();
  });

  it("shows YOB column header instead of DOB", () => {
    expect(
      screen.getByRole("columnheader", { name: /yob/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: /^dob$/i })
    ).not.toBeInTheDocument();
  });

  it("displays only the year of birth, not the full date", () => {
    expect(screen.getByText("1990")).toBeInTheDocument();
    // Full date should not appear
    expect(screen.queryByText("14/05/1990")).not.toBeInTheDocument();
  });
});
