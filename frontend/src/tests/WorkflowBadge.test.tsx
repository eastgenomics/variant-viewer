import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import WorkflowBadge from "../components/WorkflowBadge";

describe("WorkflowBadge", () => {
  it.each([
    ["pending",   "Pending",   "badge-pending"],
    ["reviewing", "Reviewing", "badge-reviewing"],
    ["reported",  "Reported",  "badge-reported"],
    ["archived",  "Archived",  "badge-archived"],
  ])("renders %s with correct label and class", (status, label, cls) => {
    render(<WorkflowBadge status={status} />);
    const badge = screen.getByText(label);
    expect(badge).toHaveClass(cls);
  });

  it("falls back gracefully for unknown status", () => {
    render(<WorkflowBadge status="unknown" />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });
});
