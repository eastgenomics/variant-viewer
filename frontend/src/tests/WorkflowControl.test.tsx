import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import WorkflowControl from "../components/WorkflowControl";
import { ApiError } from "../lib/api";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, updateWorkflow: vi.fn() };
});

import { updateWorkflow } from "../lib/api";

describe("WorkflowControl", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders transition buttons for pending status", () => {
    render(<WorkflowControl sampleId={1} currentStatus="pending" />);
    expect(screen.getByRole("button", { name: /reviewing/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /archived/i })).toBeInTheDocument();
  });

  it("renders no buttons for archived status (terminal)", () => {
    render(<WorkflowControl sampleId={1} currentStatus="archived" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls updateWorkflow and updates status on success", async () => {
    vi.mocked(updateWorkflow).mockResolvedValue({ sample_id: 1, status: "reviewing" });
    render(<WorkflowControl sampleId={1} currentStatus="pending" />);
    fireEvent.click(screen.getByRole("button", { name: /reviewing/i }));
    await waitFor(() =>
      expect(updateWorkflow).toHaveBeenCalledWith(1, "reviewing", expect.any(String))
    );
  });

  it("shows error message on API failure", async () => {
    vi.mocked(updateWorkflow).mockRejectedValue(
      new ApiError(409, "Concurrent modification")
    );
    render(<WorkflowControl sampleId={1} currentStatus="pending" />);
    fireEvent.click(screen.getByRole("button", { name: /reviewing/i }));
    await waitFor(() =>
      expect(screen.getByText(/concurrent modification/i)).toBeInTheDocument()
    );
  });
});
