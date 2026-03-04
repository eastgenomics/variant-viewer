# Example manifest files

These are example FHIR R4 Bundle manifests for testing direct S3 uploads.

## Naming convention

The manifest **must** have the same name as the VCF with `.manifest.json` replacing the VCF extension:

| VCF filename | Manifest filename |
|---|---|
| `sample.vcf.gz` | `sample.manifest.json` |
| `sample.vcf` | `sample.manifest.json` |

## S3 key structure

Both files must be uploaded to the **same S3 prefix**:

```
uploads/<lab-number>/sample.vcf.gz
uploads/<lab-number>/sample.manifest.json
```

Lambda is triggered by the VCF upload (`ObjectCreated` event) and then fetches the manifest from the same prefix. Upload the manifest **before** the VCF so it is present when Lambda runs.

## Examples

| File | Pairs with | Case type | Pipeline |
|---|---|---|---|
| `germline-example.manifest.json` | `germline-example.vcf.gz` | Germline | `dragen_germline` |
| `somatic-example.manifest.json` | `somatic-example.vcf.gz` | Somatic | `mutect2` |

Both use NHS test number `9000000009` (valid Luhn mod-11 checksum).
