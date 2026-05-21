import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import PatientListTable from "../components/PatientListTable";
import type { PatientSummary } from "../lib/api";

vi.mock("../lib/api", () => ({ deletePatient: vi.fn() }));

const patient: PatientSummary = {
  id: 1,
  lab_number: "LAB-2026-001",
  name: "Jane Smith",
  // dob removed — migration 004
  sample_count: 2,
  latest_sample_id: 10,
  latest_sample_name: "SPECIMEN_A",
  latest_workflow_status: "pending",
  latest_ingested_at: "2026-04-01T12:00:00Z",
  pipeline_key: "dragen_germline",
};

function renderTable() {
  return render(
    <MemoryRouter>
      <PatientListTable patients={[patient]} onDelete={vi.fn()} />
    </MemoryRouter>
  );
}

describe("PatientListTable", () => {
  it("shows MRN column header", () => {
    renderTable();
    expect(screen.getByRole("columnheader", { name: /mrn/i })).toBeInTheDocument();
  });

  it("displays lab_number as primary identifier", () => {
    renderTable();
    expect(screen.getByText("LAB-2026-001")).toBeInTheDocument();
  });

  it("does not show NHS number column or value", () => {
    renderTable();
    expect(screen.queryByRole("columnheader", { name: /nhs/i })).not.toBeInTheDocument();
  });

  it("does not show patient name", () => {
    renderTable();
    expect(screen.queryByText("Jane Smith")).not.toBeInTheDocument();
  });

  it("renders WorkflowBadge for latest status", () => {
    renderTable();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders View → link", () => {
    renderTable();
    expect(screen.getByRole("link", { name: /view/i })).toHaveAttribute(
      "href",
      "/patients/1"
    );
  });
});
