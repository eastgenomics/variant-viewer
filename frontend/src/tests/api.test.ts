import { describe, it, expect, vi, beforeEach } from "vitest";
import { listPatients, getPatient, ApiError, updateWorkflow, authHeaders } from "../lib/api";

beforeEach(() => { vi.restoreAllMocks(); });

describe("listPatients", () => {
  it("calls GET /api/patients and returns data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
    }));
    const result = await listPatients();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/patients"),
      expect.any(Object)
    );
    expect(result.total).toBe(0);
  });

  it("throws ApiError on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Unauthorised" }),
    }));
    await expect(listPatients()).rejects.toThrow(ApiError);
    await expect(listPatients()).rejects.toMatchObject({ status: 401 });
  });
});

describe("getPatient", () => {
  it("calls GET /api/patients/:id", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 1, lab_number: "LAB-001", name: null, created_at: null,
        samples: [],
      }),
    }));
    const result = await getPatient(1);
    expect(result.id).toBe(1);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/patients/1"),
      expect.any(Object)
    );
  });
});

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const e = new ApiError(404, "not found");
    expect(e).toBeInstanceOf(Error);
    expect(e.status).toBe(404);
    expect(e.detail).toBe("not found");
  });
});

describe("updateWorkflow", () => {
  it("calls PUT /api/workflow/{sampleId}", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ sample_id: 10, status: "reviewing" }),
    }));
    await updateWorkflow(10, "reviewing", "analyst-1");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/workflow/10"),
      expect.objectContaining({ method: "PUT" })
    );
  });
});

describe("authHeaders", () => {
  it("returns empty object when VITE_API_KEY is not set", () => {
    // In the test environment VITE_API_KEY is not set, so authHeaders returns {}
    const h = authHeaders();
    expect(h["X-API-Key"]).toBeUndefined();
    expect(Object.keys(h).length).toBe(0);
  });
});
