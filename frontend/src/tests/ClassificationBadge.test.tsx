import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ClassificationBadge from "../components/ClassificationBadge";

describe("ClassificationBadge", () => {
  it.each([
    ["Pathogenic",        "Pathogenic",       "badge-pathogenic"],
    ["Likely_Pathogenic", "Likely Pathogenic", "badge-likely-pathogenic"],
    ["VUS",               "VUS",               "badge-vus"],
    ["Likely_Benign",     "Likely Benign",     "badge-likely-benign"],
    ["Benign",            "Benign",            "badge-benign"],
    ["Oncogenic",         "Oncogenic",         "badge-oncogenic"],
    ["Likely_Oncogenic",  "Likely Oncogenic",  "badge-likely-oncogenic"],
  ])("renders %s correctly", (cls, label, cssClass) => {
    render(<ClassificationBadge classification={cls} />);
    expect(screen.getByText(label)).toHaveClass(cssClass);
  });

  it("renders em-dash for null", () => {
    render(<ClassificationBadge classification={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
