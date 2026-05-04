---
name: GMS concordance feature
description: gms_concordance column, GmsConcordance component, migration 004, and local seed data
type: project
---

## What it is

`gms_concordance` is an `INTEGER[]` column on the `variants` table representing how other GMS laboratories have classified the same variant:
- `[oncogenic, benign, unknown]` — three integers summing to 5 (one per GMS lab)

## Migration

`migrations/004_gms_concordance.sql` — adds the column to `variants`. Applied to local dev DB.
Not yet applied to production (prototype branch only).

## Component

`components/GmsConcordance.tsx` — SVG row of 5 rounded squares:
- 🟢 Green `#22c55e` — oncogenic
- 🟡 Yellow `#facc15` — benign
- ⬜ Grey `#d1d5db` — not yet classified (stroke: `#9ca3af`)

Rendered in `VariantTable.tsx` as a column before ClinVar. Column is non-sortable.

## Prototype seed data rules

- All variants seeded with `{0,0,5}` (all unclassified) by default.
- One variant per specimen gets a real concordance value — selected by: `gnomad_af < 0.01`, pathogenic consequence (missense, frameshift, stop_gained, splice_donor, splice_acceptor), ClinVar not Benign/Likely_benign.
- Real concordance values use `{3,1,1}`, `{4,0,1}`, `{4,1,0}`, or `{5,0,0}` — randomly assigned.

## Local test data

- 10 patients loaded: 5 × SYN-2026-* and 5 × SYNTH-T-001..005 (some with 2 specimens)
- 5 × SYNTH-T-091..095 (single specimen each, pulled from AWS)
- Total: ~340 variants across 17 specimens

## Status

Prototype branch only (`prototype`). Not merged to main.
