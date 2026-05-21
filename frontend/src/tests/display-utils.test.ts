import { describe, it, expect } from "vitest";
import {
  formatYearOfBirth,
  formatGnomadAf,
  formatRevel,
  formatSpliceAi,
  gnomadAfClass,
  revelClass,
  spliceAiClass,
} from "../lib/display-utils";

describe("formatYearOfBirth", () => {
  it("extracts 4-digit year from ISO date", () => {
    expect(formatYearOfBirth("1990-05-14")).toBe("1990");
  });
  it("returns em-dash for null", () => {
    expect(formatYearOfBirth(null)).toBe("—");
  });
  it("returns em-dash for undefined", () => {
    expect(formatYearOfBirth(undefined)).toBe("—");
  });
  it("handles year-only string", () => {
    expect(formatYearOfBirth("1990")).toBe("1990");
  });
});

describe("formatGnomadAf", () => {
  it("uses exponential notation below 0.0001", () => {
    expect(formatGnomadAf(0.00001)).toBe("1.00e-5");
  });
  it("uses 4 decimal places at or above 0.0001", () => {
    expect(formatGnomadAf(0.0123)).toBe("0.0123");
  });
  it("boundary: 0.0001 → 4dp", () => {
    expect(formatGnomadAf(0.0001)).toBe("0.0001");
  });
  it("returns 'absent' for null", () => {
    expect(formatGnomadAf(null)).toBe("absent");
  });
});

describe("formatRevel", () => {
  it("formats to 3 decimal places", () => {
    expect(formatRevel(0.75)).toBe("0.750");
  });
  it("returns em-dash for null", () => {
    expect(formatRevel(null)).toBe("—");
  });
});

describe("formatSpliceAi", () => {
  it("formats to 3 decimal places", () => {
    expect(formatSpliceAi(0.8)).toBe("0.800");
  });
  it("returns em-dash for null", () => {
    expect(formatSpliceAi(null)).toBe("—");
  });
});

describe("gnomadAfClass", () => {
  it("returns amber class above 0.01", () => {
    expect(gnomadAfClass(0.05)).toBe("text-amber-600");
  });
  it("returns gray class at or below 0.01", () => {
    expect(gnomadAfClass(0.01)).toBe("text-gray-700");
  });
  it("returns gray class for null", () => {
    expect(gnomadAfClass(null)).toBe("text-gray-700");
  });
});

describe("revelClass", () => {
  it("returns red for score >= 0.7", () => {
    expect(revelClass(0.7)).toBe("text-red-600");
  });
  it("returns green for score <= 0.4", () => {
    expect(revelClass(0.4)).toBe("text-green-700");
  });
  it("returns gray for mid-range", () => {
    expect(revelClass(0.55)).toBe("text-gray-700");
  });
  it("returns gray for null", () => {
    expect(revelClass(null)).toBe("text-gray-700");
  });
});

describe("spliceAiClass", () => {
  it("returns orange for score >= 0.5", () => {
    expect(spliceAiClass(0.5)).toBe("text-orange-600");
  });
  it("returns gray below 0.5", () => {
    expect(spliceAiClass(0.3)).toBe("text-gray-700");
  });
  it("returns gray for null", () => {
    expect(spliceAiClass(null)).toBe("text-gray-700");
  });
});
