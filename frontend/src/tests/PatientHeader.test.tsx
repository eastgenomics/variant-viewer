import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PatientHeader from "../components/PatientHeader";
import type { PatientDetailResponse } from "../lib/api";

const patient: PatientDetailResponse = {
  id: 1,
  lab_number: "LAB-2026-001",
  name: "Jane Smith",
  created_at: null,
  // dob removed — migration 004
  samples: [],
};

describe("PatientHeader", () => {
  it("displays lab_number", () => {
    render(<PatientHeader patient={patient} />);
    expect(screen.getByText("LAB-2026-001")).toBeInTheDocument();
  });

  it("does not display patient name", () => {
    render(<PatientHeader patient={patient} />);
    expect(screen.queryByText("Jane Smith")).not.toBeInTheDocument();
  });

});
