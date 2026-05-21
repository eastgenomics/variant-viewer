import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ClassificationPanel from "../components/ClassificationPanel";
import { putClassification, resetClassification, ApiError } from "../lib/api";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    putClassification: vi.fn(),
    resetClassification: vi.fn(),
  };
});

const baseProps = {
  variantId: 100,
  caseType: "germline" as const,
  gene: "BRCA1",
  initialClassification: null,
  initialCriteria: [],
};

describe("ClassificationPanel", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("shows score of 0 and VUS with no criteria applied", () => {
    render(<ClassificationPanel {...baseProps} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText(/variant of uncertain significance/i)).toBeInTheDocument();
  });

  it("shows framework selector (unlocked initially)", () => {
    render(<ClassificationPanel {...baseProps} />);
    const selector = screen.getByRole("combobox");
    expect(selector).not.toBeDisabled();
  });

  it("renders Save draft and Confirm buttons", () => {
    render(<ClassificationPanel {...baseProps} />);
    expect(screen.getByRole("button", { name: /save draft/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm/i })).toBeInTheDocument();
  });

  it("calls putClassification on Confirm", async () => {
    vi.mocked(putClassification).mockResolvedValue({
      score: 0,
      classification: "VUS",
      classification_id: 1,
      warnings: [],
    });
    render(<ClassificationPanel {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() =>
      expect(putClassification).toHaveBeenCalledWith(
        100,
        expect.objectContaining({ locked_by: expect.any(String) })
      )
    );
  });

  it("calls putClassification with locked_by=null on Save draft", async () => {
    vi.mocked(putClassification).mockResolvedValue({
      score: 0,
      classification: "VUS",
      classification_id: 1,
      warnings: [],
    });
    render(<ClassificationPanel {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /save draft/i }));
    await waitFor(() =>
      expect(putClassification).toHaveBeenCalledWith(
        100,
        expect.objectContaining({ locked_by: null })
      )
    );
    // Panel should remain unlocked after draft save
    expect(screen.getByRole("button", { name: /save draft/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm/i })).toBeInTheDocument();
    expect(screen.queryByText(/confirmed \d/i)).not.toBeInTheDocument();
  });

  it("shows error banner when putClassification rejects", async () => {
    vi.mocked(putClassification).mockRejectedValue(
      new ApiError(409, "Concurrent modification")
    );
    render(<ClassificationPanel {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() =>
      expect(screen.getByText(/concurrent modification/i)).toBeInTheDocument()
    );
  });

  it("shows Reset button when locked", () => {
    render(
      <ClassificationPanel
        {...baseProps}
        initialClassification={{
          id: 1,
          framework: "acgs_snv",
          framework_version: "ACGS 2024",
          score: 9,
          classification: "Likely_Pathogenic",
          locked_at: "2026-05-01T10:00:00Z",
          locked_by: "analyst-1",
        }}
        initialCriteria={[]}
      />
    );
    expect(screen.getByRole("button", { name: /reset/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save draft/i })).not.toBeInTheDocument();
  });

  it("calls resetClassification on confirmed reset", async () => {
    vi.mocked(resetClassification).mockResolvedValue({
      new_classification_id: 2,
    });
    render(
      <ClassificationPanel
        {...baseProps}
        initialClassification={{
          id: 1,
          framework: "acgs_snv",
          framework_version: "ACGS 2024",
          score: 0,
          classification: "VUS",
          locked_at: "2026-05-01T10:00:00Z",
          locked_by: "analyst-1",
        }}
        initialCriteria={[]}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /reset/i }));
    fireEvent.click(await screen.findByRole("button", { name: /yes, reset/i }));
    await waitFor(() =>
      expect(resetClassification).toHaveBeenCalledWith(100, 1, expect.any(String))
    );
  });

  it("shows error banner when resetClassification rejects", async () => {
    vi.mocked(resetClassification).mockRejectedValue(
      new ApiError(503, "Service unavailable")
    );
    render(
      <ClassificationPanel
        {...baseProps}
        initialClassification={{
          id: 1,
          framework: "acgs_snv",
          framework_version: "ACGS 2024",
          score: 0,
          classification: "VUS",
          locked_at: "2026-05-01T10:00:00Z",
          locked_by: "analyst-1",
        }}
        initialCriteria={[]}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /reset/i }));
    fireEvent.click(await screen.findByRole("button", { name: /yes, reset/i }));
    await waitFor(() =>
      expect(screen.getByText(/service unavailable/i)).toBeInTheDocument()
    );
    // Panel should remain locked on reset failure
    expect(screen.getByRole("button", { name: /reset classification/i })).toBeInTheDocument();
  });
});
