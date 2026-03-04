/**
 * FHIR R4 Bundle manifest parser/builder.
 * Lightweight typed JSON access — no full FHIR library.
 */

export interface ManifestPatient {
  lab_number: string;
  nhs_number: string | null;
  name: string | null;
  dob: string | null; // ISO date YYYY-MM-DD
}

export interface ManifestSpecimen {
  sample_name: string;
  case_type: "germline" | "somatic";
  tissue: string | null;
  sequencing_date: string | null;
}

export interface ManifestTask {
  pipeline_key: string | null;
  pipeline_version: string | null;
  run_id: string | null;
  vcf_filename: string | null;
}

export interface ParsedManifest {
  patient: ManifestPatient;
  specimen: ManifestSpecimen;
  task: ManifestTask;
}

const NHS_LAB_SYSTEM = "https://fhir.example-lab.org/Id/lab-number";
const NHS_NUMBER_SYSTEM = "https://fhir.nhs.uk/Id/nhs-number";
const CASE_TYPE_EXT =
  "https://example.org/fhir/StructureDefinition/case-type";

/** Validate NHS number using Luhn modulo-11 checksum */
export function validateNhsNumber(nhs: string): boolean {
  const digits = nhs.replace(/\s/g, "");
  if (!/^\d{10}$/.test(digits)) return false;
  const weights = [10, 9, 8, 7, 6, 5, 4, 3, 2];
  let sum = 0;
  for (let i = 0; i < 9; i++) {
    sum += parseInt(digits[i], 10) * weights[i];
  }
  const remainder = sum % 11;
  const checkDigit = 11 - remainder;
  if (checkDigit === 11) return parseInt(digits[9], 10) === 0;
  if (checkDigit === 10) return false; // invalid
  return parseInt(digits[9], 10) === checkDigit;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FhirResource = Record<string, any>;
type FhirBundle = {
  resourceType: "Bundle";
  type: "collection";
  entry: Array<{ resource: FhirResource }>;
};

function findResource(bundle: FhirBundle, type: string): FhirResource | null {
  return (
    bundle.entry.find((e) => e.resource?.resourceType === type)?.resource ??
    null
  );
}

export function parseManifest(raw: unknown): ParsedManifest {
  const bundle = raw as FhirBundle;
  if (bundle?.resourceType !== "Bundle" || bundle?.type !== "collection") {
    throw new Error("Manifest must be a FHIR R4 Bundle (type: collection)");
  }

  const patient = findResource(bundle, "Patient");
  const specimen = findResource(bundle, "Specimen");
  const task = findResource(bundle, "Task");

  if (!patient) throw new Error("Manifest missing Patient resource");
  if (!specimen) throw new Error("Manifest missing Specimen resource");
  if (!task) throw new Error("Manifest missing Task resource");

  // Patient identifiers
  const identifiers: Array<{ system?: string; value?: string; use?: string }> =
    patient.identifier ?? [];

  const labId = identifiers.find((id) => id.system === NHS_LAB_SYSTEM);
  const nhsId = identifiers.find((id) => id.system === NHS_NUMBER_SYSTEM);

  // Fall back: if no system-qualified identifier, use first identifier as lab number
  const lab_number =
    labId?.value ?? identifiers.find((id) => !id.system)?.value ?? null;
  if (!lab_number) {
    throw new Error("Patient manifest missing lab number identifier");
  }

  const nhs_number = nhsId?.value ?? null;
  if (nhs_number && !validateNhsNumber(nhs_number)) {
    throw new Error(
      `Invalid NHS number: ${nhs_number} (failed Luhn modulo-11 checksum)`
    );
  }

  const nameEntry = patient.name?.[0];
  const givenNames: string[] = nameEntry?.given ?? [];
  const name = nameEntry
    ? `${givenNames.join(" ")} ${nameEntry.family ?? ""}`.trim() || null
    : null;

  // Specimen
  const caseTypeExt = (specimen.extension ?? []).find(
    (e: { url: string }) => e.url === CASE_TYPE_EXT
  );
  const caseTypeRaw: string = caseTypeExt?.valueCode ?? "germline";
  const case_type: "germline" | "somatic" =
    caseTypeRaw === "somatic" ? "somatic" : "germline";

  const sampleIdentifier = specimen.identifier?.[0];
  const sample_name = sampleIdentifier?.value ?? "unknown";

  const tissueDisplay =
    specimen.type?.coding?.[0]?.display ?? specimen.type?.text ?? null;
  const sequencing_date =
    specimen.collection?.collectedDateTime?.split("T")[0] ?? null;

  // Task
  const pipelineKey: string | null = task.code?.text ?? null;
  const pipelineVersionInput = (task.input ?? []).find(
    (i: { type: { text?: string }; valueString?: string }) =>
      i.type?.text === "pipeline_version"
  );
  const pipeline_version: string | null =
    pipelineVersionInput?.valueString ?? null;
  const runId = task.identifier?.[0]?.value ?? null;
  const vcfOutput = (task.output ?? []).find(
    (o: { type: { text?: string }; valueString?: string }) =>
      o.type?.text === "vcf"
  );
  const vcf_filename: string | null = vcfOutput?.valueString ?? null;

  return {
    patient: {
      lab_number,
      nhs_number,
      name,
      dob: patient.birthDate ?? null,
    },
    specimen: {
      sample_name,
      case_type,
      tissue: tissueDisplay,
      sequencing_date,
    },
    task: {
      pipeline_key: pipelineKey,
      pipeline_version,
      run_id: runId,
      vcf_filename,
    },
  };
}

/** Build a FHIR R4 Bundle manifest from form field values */
export function buildManifest(
  patient: ManifestPatient,
  specimen: ManifestSpecimen,
  task: ManifestTask
): FhirBundle {
  return {
    resourceType: "Bundle",
    type: "collection",
    entry: [
      {
        resource: {
          resourceType: "Patient",
          identifier: [
            {
              system: NHS_LAB_SYSTEM,
              value: patient.lab_number,
            },
            ...(patient.nhs_number
              ? [
                  {
                    system: NHS_NUMBER_SYSTEM,
                    value: patient.nhs_number,
                    use: "official",
                  },
                ]
              : []),
          ],
          name: patient.name
            ? (() => {
                const parts = patient.name.split(" ");
                const family = parts.pop() ?? "";
                const given = parts;
                return [{ family, given }];
              })()
            : undefined,
          birthDate: patient.dob ?? undefined,
        },
      },
      {
        resource: {
          resourceType: "Specimen",
          identifier: [{ value: specimen.sample_name }],
          collection: specimen.sequencing_date
            ? { collectedDateTime: specimen.sequencing_date }
            : undefined,
          extension: [
            {
              url: CASE_TYPE_EXT,
              valueCode: specimen.case_type,
            },
          ],
        },
      },
      {
        resource: {
          resourceType: "Task",
          status: "completed",
          identifier: task.run_id ? [{ value: task.run_id }] : [],
          code: task.pipeline_key ? { text: task.pipeline_key } : undefined,
          input: task.pipeline_version
            ? [
                {
                  type: { text: "pipeline_version" },
                  valueString: task.pipeline_version,
                },
              ]
            : [],
          output: task.vcf_filename
            ? [{ type: { text: "vcf" }, valueString: task.vcf_filename }]
            : [],
        },
      },
    ],
  };
}
