import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import UploadForm from "../components/UploadForm";

const pipelineOptions = [{ key: "dragen_germline", label: "DRAGEN Germline" }];

describe("UploadForm", () => {
  it('shows "Specimen" section heading', () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.getByText("Specimen")).toBeInTheDocument();
  });

  it('shows "Specimen name" label', () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.getByText("Specimen name")).toBeInTheDocument();
  });

  it("does not show NHS number field", () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.queryByText(/nhs number/i)).not.toBeInTheDocument();
  });

  it("does not show patient name field", () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.queryByText(/patient name/i)).not.toBeInTheDocument();
  });

  it("shows lab record number as required field", () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.getByText(/lab record number/i)).toBeInTheDocument();
  });

  it("shows Upload VCF submit button", () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /upload vcf/i })).toBeInTheDocument();
  });
});
