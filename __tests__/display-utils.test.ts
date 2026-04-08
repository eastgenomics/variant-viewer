import { formatYearOfBirth } from "@/lib/display-utils";

describe("formatYearOfBirth", () => {
  it("extracts year from an ISO date string", () => {
    expect(formatYearOfBirth("1990-05-14")).toBe("1990");
  });

  it("extracts year from a full ISO datetime", () => {
    expect(formatYearOfBirth("1985-12-25T00:00:00.000Z")).toBe("1985");
  });

  it('returns "—" for null input', () => {
    expect(formatYearOfBirth(null)).toBe("—");
  });

  it('returns "—" for undefined input', () => {
    expect(formatYearOfBirth(undefined)).toBe("—");
  });
});
