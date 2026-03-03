"use client";

const BADGE_MAP: Record<string, string> = {
  Pathogenic: "badge badge-pathogenic",
  Likely_Pathogenic: "badge badge-likely-pathogenic",
  VUS: "badge badge-vus",
  Likely_Benign: "badge badge-likely-benign",
  Benign: "badge badge-benign",
  Oncogenic: "badge badge-oncogenic",
  Likely_Oncogenic: "badge badge-likely-oncogenic",
};

const LABEL_MAP: Record<string, string> = {
  Pathogenic: "Pathogenic",
  Likely_Pathogenic: "Likely Pathogenic",
  VUS: "VUS",
  Likely_Benign: "Likely Benign",
  Benign: "Benign",
  Oncogenic: "Oncogenic",
  Likely_Oncogenic: "Likely Oncogenic",
};

export default function ClassificationBadge({
  classification,
}: {
  classification: string | null;
}) {
  if (!classification) return <span className="text-gray-400 text-xs">—</span>;
  return (
    <span className={BADGE_MAP[classification] ?? "badge bg-gray-100 text-gray-600"}>
      {LABEL_MAP[classification] ?? classification}
    </span>
  );
}
