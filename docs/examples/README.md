# Example manifest files

These are examples of FHIR R4 Bundle manifests for testing direct S3 uploads.

## Naming convention

The manifest **must** have the same name as the VCF with `.manifest.json` replacing the VCF extension:

| VCF filename | Manifest filename |
|---|---|
| `sample.vcf.gz` | `sample.manifest.json` |
| `sample.vcf` | `sample.manifest.json` |

## S3 key structure

Both files must be uploaded to the **same S3 prefix**:

```text
uploads/<lab-number>/sample.vcf.gz
uploads/<lab-number>/sample.manifest.json
```

Lambda is triggered by the VCF upload (`ObjectCreated` event) and then fetches the manifest from the same prefix. Upload the manifest **before** the VCF so it is present when Lambda runs.

## Examples

| File | Pairs with | Case type | Pipeline | Notes |
|---|---|---|---|---|
| `germline-example.manifest.json` | `germline-example.vcf.gz` | Germline | `dragen_germline` | Peripheral blood |
| `somatic-example.manifest.json` | `somatic-example.vcf.gz` | Somatic | `mutect2` | FFPE tumour biopsy |
| `somatic-wgs-example.manifest.json` | `somatic-wgs-example.vcf.gz` | Somatic | `strelka2` | Fresh frozen tumour WGS |
| `germline-panel-example.manifest.json` | `germline-panel-example.vcf.gz` | Germline | `dragen_germline` | Saliva, targeted panel (`BRCA1_BRCA2_v3`) |
| `somatic-cfdna-example.manifest.json` | `somatic-cfdna-example.vcf.gz` | Somatic | `mutect2` | Liquid biopsy cfDNA, tumour-only mode |
| `germline-trio-proband-example.manifest.json` | `germline-trio-proband-example.vcf.gz` | Germline | `dragen_germline` | Trio analysis, proband sample |
| `somatic-reanalysis-example.manifest.json` | `somatic-reanalysis-example.vcf.gz` | Somatic | `mutect2` | Re-analysis of LAB-2024-00456 with updated PoN |

NHS test numbers used (all valid Modulus 11): `9000000009`, `9000000017`, `9000000025`, `9000000033`, `9000000041`.
