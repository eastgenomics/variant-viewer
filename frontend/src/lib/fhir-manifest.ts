/**
 * Lightweight FHIR R4 Bundle builder for the variant-viewer upload manifest.
 * Ported from discovery/nextjs:lib/fhir-manifest.ts.
 * NHS number and patient name fields are omitted (not collected by this SPA).
 */

const NHS_LAB_SYSTEM = "https://fhir.example-lab.org/Id/lab-number";
const CASE_TYPE_EXT =
  "https://example.org/fhir/StructureDefinition/case-type";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FhirBundle = Record<string, any>;

export function buildManifest(params: {
  labNumber: string;
  specimenName: string;
  caseType: "germline" | "somatic";
  pipelineKey: string | null;
  sequencingDate: string | null;
  vcfFilename: string;
}): FhirBundle {
  const { labNumber, specimenName, caseType, pipelineKey, sequencingDate, vcfFilename } = params;
  return {
    resourceType: "Bundle",
    type: "collection",
    entry: [
      {
        resource: {
          resourceType: "Patient",
          identifier: [{ system: NHS_LAB_SYSTEM, value: labNumber }],
        },
      },
      {
        resource: {
          resourceType: "Specimen",
          identifier: [{ value: specimenName }],
          collection: sequencingDate
            ? { collectedDateTime: sequencingDate }
            : undefined,
          extension: [
            { url: CASE_TYPE_EXT, valueCode: caseType },
          ],
        },
      },
      {
        resource: {
          resourceType: "Task",
          status: "completed",
          identifier: [],
          code: pipelineKey ? { text: pipelineKey } : undefined,
          output: [{ type: { text: "vcf" }, valueString: vcfFilename }],
        },
      },
    ],
  };
}
