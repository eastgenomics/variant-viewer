---
name: Case identifier rework
description: UI identifier changes from first deployment feedback — MRN primary, Specimen rename, no NHS/name displayed, YOB only. Merged to main.
type: project
originSessionId: 4039298e-55e5-47b1-999d-6c05fb200903
---
PR #10 (`feat/rename-and-case-identifiers`) **merged to main.**

- **Primary identifier**: MRN (lab_number) replaces patient name throughout UI
- **Secondary identifier**: "Sample" renamed to "Specimen" in all UI text
- **NHS numbers**: removed from display (upload form, patient list, detail page)
- **Patient names**: removed from display (upload form, patient list, detail page)
- **DOB**: shows year of birth only (`lib/display-utils.ts` → `formatYearOfBirth`)
  - Implementation uses regex `/^(\d{4})(?:-|$)/` — avoids NaN and timezone issues with YYYY-MM-DD strings

Extracted presentational components: `PatientListTable`, `PatientHeader`, `SpecimenCard`.
Nav changed from "Patients" to "Cases".
Test suite: 28 tests / 7 suites (`npm test`).

**Why:** Clinical feedback — MRN is the standard clinical identifier, NHS numbers shouldn't be displayed in this context, and full DOB is unnecessary detail.
