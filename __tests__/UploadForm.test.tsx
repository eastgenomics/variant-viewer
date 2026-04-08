import { render, screen } from "@testing-library/react";
import UploadForm from "@/app/upload/UploadForm";

describe("UploadForm", () => {
  beforeEach(() => {
    render(
      <UploadForm
        pipelineOptions={[{ key: "dragen_germline", label: "Dragen Germline" }]}
      />
    );
  });

  it('shows "Specimen" section heading instead of "Sample"', () => {
    expect(screen.getByText("Specimen")).toBeInTheDocument();
    expect(screen.queryByText("Sample")).not.toBeInTheDocument();
  });

  it('shows "Specimen name" label instead of "Sample name"', () => {
    expect(screen.getByText("Specimen name")).toBeInTheDocument();
    expect(screen.queryByText("Sample name")).not.toBeInTheDocument();
  });

  it("does not show NHS number field", () => {
    expect(screen.queryByText(/nhs number/i)).not.toBeInTheDocument();
  });

  it("does not show patient name field", () => {
    expect(screen.queryByText(/patient name/i)).not.toBeInTheDocument();
  });
});
