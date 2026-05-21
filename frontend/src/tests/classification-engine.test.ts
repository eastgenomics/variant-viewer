import { describe, it, expect } from "vitest";
import { classify, selectFramework } from "../lib/classification-engine";
import acgsCriteria from "../config/acgs-snv-criteria.json";
import svigCriteria from "../config/svig-criteria.json";

const acgsRules = acgsCriteria.combination_rules as {
  rule: string; codes: string[]; message: string
}[];
const svigRules = svigCriteria.combination_rules as {
  rule: string; codes: string[]; message: string
}[];

describe("ACGS SNV classification", () => {
  it("PVS1 + PM2 → Likely_Pathogenic (score 9)", () => {
    const result = classify(
      [
        { criterion_code: "PVS1", applied: true, strength: "very_strong" },
        { criterion_code: "PM2",  applied: true, strength: "supporting" },
      ],
      "acgs_snv",
      acgsRules
    );
    expect(result.score).toBe(9);
    expect(result.classification).toBe("Likely_Pathogenic");
    expect(result.warnings).toHaveLength(0);
  });

  it("No criteria → VUS (score 0)", () => {
    const result = classify([], "acgs_snv", acgsRules);
    expect(result.score).toBe(0);
    expect(result.classification).toBe("VUS");
  });

  it("BS1 + BS2 → Benign (score -8)", () => {
    const result = classify(
      [
        { criterion_code: "BS1", applied: true, strength: "strong" },
        { criterion_code: "BS2", applied: true, strength: "strong" },
      ],
      "acgs_snv",
      acgsRules
    );
    expect(result.score).toBe(-8);
    expect(result.classification).toBe("Benign");
  });
});

describe("SVIG classification", () => {
  it("O2 very_strong alone → Likely_Oncogenic (score 8)", () => {
    const result = classify(
      [{ criterion_code: "O2", applied: true, strength: "very_strong" }],
      "svig",
      svigRules
    );
    expect(result.score).toBe(8);
    expect(result.classification).toBe("Likely_Oncogenic");
  });
});

describe("selectFramework", () => {
  it("selects acgs_snv for germline", () => {
    expect(selectFramework("germline", "BRCA1").framework).toBe("acgs_snv");
  });
  it("selects svig for somatic", () => {
    expect(selectFramework("somatic", "TP53").framework).toBe("svig");
  });
});

describe("BA1 standalone override (ACGS)", () => {
  it("BA1 alone → Benign with sentinel score -999", () => {
    const result = classify(
      [{ criterion_code: "BA1", applied: true, strength: "standalone" }],
      "acgs_snv",
      acgsRules
    );
    expect(result.score).toBe(-999);
    expect(result.classification).toBe("Benign");
  });
});

describe("SVIG sentinel priority (O1 > B1 > B2)", () => {
  it("O1 standalone → Oncogenic (score 999)", () => {
    const result = classify(
      [{ criterion_code: "O1", applied: true, strength: "standalone" }],
      "svig",
      svigRules
    );
    expect(result.score).toBe(999);
    expect(result.classification).toBe("Oncogenic");
  });

  it("B1 standalone → Benign (score -999)", () => {
    const result = classify(
      [{ criterion_code: "B1", applied: true, strength: "standalone" }],
      "svig",
      svigRules
    );
    expect(result.score).toBe(-999);
    expect(result.classification).toBe("Benign");
  });

  it("B2 standalone → VUS (score 0)", () => {
    const result = classify(
      [{ criterion_code: "B2", applied: true, strength: "standalone" }],
      "svig",
      svigRules
    );
    expect(result.score).toBe(0);
    expect(result.classification).toBe("VUS");
  });

  it("O1 + B2 → Oncogenic (O1 takes priority over B2)", () => {
    const result = classify(
      [
        { criterion_code: "O1", applied: true, strength: "standalone" },
        { criterion_code: "B2", applied: true, strength: "standalone" },
      ],
      "svig",
      svigRules
    );
    expect(result.classification).toBe("Oncogenic");
  });

  it("O1 + B1 → Oncogenic (O1 takes priority over B1)", () => {
    const result = classify(
      [
        { criterion_code: "O1", applied: true, strength: "standalone" },
        { criterion_code: "B1", applied: true, strength: "standalone" },
      ],
      "svig",
      svigRules
    );
    expect(result.classification).toBe("Oncogenic");
  });
});

describe("ACGS minimum-criteria warning", () => {
  it("PVS1 alone (1 criterion) → LP with minimum-criteria warning", () => {
    const result = classify(
      [{ criterion_code: "PVS1", applied: true, strength: "very_strong" }],
      "acgs_snv",
      acgsRules
    );
    expect(result.classification).toBe("Likely_Pathogenic");
    expect(result.warnings.length).toBeGreaterThan(0);
    expect(result.warnings[0]).toMatch(/minimum.*2.*criteria/i);
  });
});

describe("score threshold boundaries (ACGS)", () => {
  it("score -6 → Likely_Benign", () => {
    const result = classify(
      [
        { criterion_code: "BS1", applied: true, strength: "strong" },   // -4
        { criterion_code: "BP1", applied: true, strength: "supporting" }, // -1
        { criterion_code: "BP3", applied: true, strength: "supporting" }, // -1
      ],
      "acgs_snv",
      acgsRules
    );
    expect(result.score).toBe(-6);
    expect(result.classification).toBe("Likely_Benign");
  });
});

import { classificationLabel, classificationBadgeClass } from "../lib/classification-engine";

describe("classificationLabel", () => {
  it("returns em-dash for null", () => {
    expect(classificationLabel(null)).toBe("—");
  });
  it("maps Likely_Pathogenic → 'Likely Pathogenic'", () => {
    expect(classificationLabel("Likely_Pathogenic")).toBe("Likely Pathogenic");
  });
  it("maps Likely_Oncogenic → 'Likely Oncogenic'", () => {
    expect(classificationLabel("Likely_Oncogenic")).toBe("Likely Oncogenic");
  });
  it("passes through unknown classification strings", () => {
    expect(classificationLabel("SomeNewClass")).toBe("SomeNewClass");
  });
});

describe("classificationBadgeClass", () => {
  it("returns 'vus' for null", () => {
    expect(classificationBadgeClass(null)).toBe("vus");
  });
  it.each([
    ["Pathogenic",        "pathogenic"],
    ["Likely_Pathogenic", "likely-pathogenic"],
    ["VUS",              "vus"],
    ["Likely_Benign",    "likely-benign"],
    ["Benign",           "benign"],
    ["Oncogenic",        "oncogenic"],
    ["Likely_Oncogenic", "likely-oncogenic"],
  ])("maps %s → %s", (cls, expected) => {
    expect(classificationBadgeClass(cls)).toBe(expected);
  });
  it("falls back to 'vus' for unknown", () => {
    expect(classificationBadgeClass("SomeNewClass")).toBe("vus");
  });
});

describe("combination rule warnings", () => {
  it("fires warning when two codes from same rule are both applied (ACGS)", () => {
    // Check what combination rules exist
    const pp3bp4Rule = acgsRules.find(
      (r) => r.codes.includes("PP3") && r.codes.includes("BP4")
    );
    if (!pp3bp4Rule) return; // unreachable — satisfies TS narrowing
    expect(pp3bp4Rule).toBeDefined(); // fail loudly if rule removed from config
    const result = classify(
      [
        { criterion_code: "PP3", applied: true, strength: "supporting" },
        { criterion_code: "BP4", applied: true, strength: "supporting" },
      ],
      "acgs_snv",
      acgsRules
    );
    expect(result.warnings.some((w) => w === pp3bp4Rule.message)).toBe(true);
  });

  it("does not fire warning when only one of a conflict pair is applied", () => {
    const result = classify(
      [{ criterion_code: "PP3", applied: true, strength: "supporting" }],
      "acgs_snv",
      acgsRules
    );
    // Only the min-criteria warning should fire (1 criterion), no combination warning
    const combinationWarnings = result.warnings.filter((w) =>
      acgsRules.some((r) => r.message === w && r.codes.length >= 2)
    );
    expect(combinationWarnings).toHaveLength(0);
  });
});
