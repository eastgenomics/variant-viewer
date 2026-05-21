import { describe, it, expect } from "vitest";
import { buildManifest } from "../lib/fhir-manifest";

const base = {
  labNumber: "LAB-001",
  specimenName: "SP-001",
  caseType: "germline" as const,
  pipelineKey: null,
  sequencingDate: null,
  vcfFilename: "sample.vcf.gz",
};

describe("buildManifest", () => {
  it("produces a FHIR R4 Bundle with three entries", () => {
    const m = buildManifest(base);
    expect(m.resourceType).toBe("Bundle");
    expect(m.type).toBe("collection");
    expect(m.entry).toHaveLength(3);
  });

  it("Patient has correct NHS lab system identifier", () => {
    const m = buildManifest(base);
    const patient = m.entry[0].resource;
    expect(patient.resourceType).toBe("Patient");
    expect(patient.identifier[0].system).toBe(
      "https://fhir.example-lab.org/Id/lab-number"
    );
    expect(patient.identifier[0].value).toBe("LAB-001");
  });

  it("Specimen has CASE_TYPE_EXT extension with correct valueCode", () => {
    const m = buildManifest(base);
    const specimen = m.entry[1].resource;
    expect(specimen.resourceType).toBe("Specimen");
    expect(specimen.identifier[0].value).toBe("SP-001");
    const ext = specimen.extension[0];
    expect(ext.url).toBe(
      "https://example.org/fhir/StructureDefinition/case-type"
    );
    expect(ext.valueCode).toBe("germline");
  });

  it("somatic caseType maps to correct extension valueCode", () => {
    const m = buildManifest({ ...base, caseType: "somatic" });
    const ext = m.entry[1].resource.extension[0];
    expect(ext.valueCode).toBe("somatic");
  });

  it("omits collection when sequencingDate is null", () => {
    const m = buildManifest(base);
    expect(m.entry[1].resource.collection).toBeUndefined();
  });

  it("includes collection when sequencingDate is provided", () => {
    const m = buildManifest({ ...base, sequencingDate: "2026-01-15" });
    expect(m.entry[1].resource.collection.collectedDateTime).toBe("2026-01-15");
  });

  it("Task has vcf filename in output", () => {
    const m = buildManifest(base);
    const task = m.entry[2].resource;
    expect(task.resourceType).toBe("Task");
    expect(task.output[0].type.text).toBe("vcf");
    expect(task.output[0].valueString).toBe("sample.vcf.gz");
  });

  it("includes pipelineKey in Task code when provided", () => {
    const m = buildManifest({ ...base, pipelineKey: "dragen_germline" });
    expect(m.entry[2].resource.code.text).toBe("dragen_germline");
  });

  it("omits Task code when pipelineKey is null", () => {
    const m = buildManifest(base);
    expect(m.entry[2].resource.code).toBeUndefined();
  });
});
