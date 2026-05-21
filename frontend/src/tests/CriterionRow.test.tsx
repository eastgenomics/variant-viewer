import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import CriterionRow from "../components/CriterionRow";

const def = {
  code: "PVS1",
  description: "Null variant",
  category: "population",
  direction: "pathogenic",
  default_strength: "very_strong",
  adjustable: false,
  permitted_strengths: ["very_strong"],
};

const crit = {
  criterion_code: "PVS1",
  applied: true,
  strength: "very_strong",
  notes: "",
  evidence_links: [] as string[],
  pre_computed: false,
  pre_computed_value: null,
};

describe("CriterionRow", () => {
  it("renders criterion code and description", () => {
    render(<CriterionRow def={def} crit={crit} locked={false} onChange={vi.fn()} />);
    expect(screen.getByText("PVS1")).toBeInTheDocument();
  });

  it("rejects javascript: evidence links (Invariant 3)", () => {
    const onChange = vi.fn();
    render(<CriterionRow def={def} crit={crit} locked={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /add notes/i }));
    const input = screen.getByPlaceholderText(/https/i);
    fireEvent.change(input, { target: { value: "javascript:alert(1)" } });
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    // Implementation returns early without calling onChange on invalid URL
    expect(onChange).not.toHaveBeenCalled();
  });

  it("accepts https: evidence links", () => {
    const onChange = vi.fn();
    render(<CriterionRow def={def} crit={crit} locked={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /add notes/i }));
    const input = screen.getByPlaceholderText(/https/i);
    fireEvent.change(input, { target: { value: "https://www.ncbi.nlm.nih.gov/snp/rs12345" } });
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        evidence_links: ["https://www.ncbi.nlm.nih.gov/snp/rs12345"],
      })
    );
  });

  it("disables all inputs when locked", () => {
    render(<CriterionRow def={def} crit={crit} locked={true} onChange={vi.fn()} />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });

  it("clears linkError and pendingLink when notes panel is closed", () => {
    render(<CriterionRow def={def} crit={crit} locked={false} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /add notes/i }));
    const input = screen.getByPlaceholderText(/https/i);
    fireEvent.change(input, { target: { value: "ftp://bad-protocol" } });
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect(screen.getByText(/only http/i)).toBeInTheDocument();
    // Close the panel
    fireEvent.click(screen.getByRole("button", { name: /hide notes/i }));
    // Reopen — error and input should be cleared
    fireEvent.click(screen.getByRole("button", { name: /add notes/i }));
    expect(screen.queryByText(/only http/i)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/https/i)).toHaveValue("");
  });

  it("clears pendingLink input after successful link add", () => {
    render(<CriterionRow def={def} crit={crit} locked={false} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /add notes/i }));
    const input = screen.getByPlaceholderText(/https/i);
    fireEvent.change(input, { target: { value: "https://pubmed.ncbi.nlm.nih.gov/12345" } });
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect(input).toHaveValue("");
  });
});
