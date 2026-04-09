import { render, screen } from "@testing-library/react";
import PatientHeader from "@/components/PatientHeader";

const patient = {
  id: 1,
  name: "Jane Smith",
  lab_number: "LAB-2026-001",
  nhs_number: "9000000009",
  dob: "1990-05-14",
};

describe("PatientHeader", () => {
  beforeEach(() => {
    render(<PatientHeader patient={patient} />);
  });

  it("shows the MRN (lab_number) as the primary heading", () => {
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("LAB-2026-001");
  });

  it("does not display the patient name", () => {
    expect(screen.queryByText("Jane Smith")).not.toBeInTheDocument();
  });

  it("does not display the NHS number", () => {
    expect(screen.queryByText("9000000009")).not.toBeInTheDocument();
    expect(screen.queryByText(/nhs/i)).not.toBeInTheDocument();
  });

  it("shows year of birth only, not full DOB", () => {
    expect(screen.getByText(/1990/)).toBeInTheDocument();
    expect(screen.queryByText("14/05/1990")).not.toBeInTheDocument();
    // Should be labelled YOB not DOB
    expect(screen.getByText(/yob/i)).toBeInTheDocument();
    expect(screen.queryByText(/^dob$/i)).not.toBeInTheDocument();
  });
});

describe("PatientHeader with null DOB", () => {
  it('shows "—" when DOB is null', () => {
    render(
      <PatientHeader patient={{ ...patient, dob: null }} />
    );
    // Should not crash and should show dash
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
