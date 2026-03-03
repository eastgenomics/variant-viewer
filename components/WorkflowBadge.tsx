"use client";

const BADGE_CLASSES: Record<string, string> = {
  pending: "badge badge-pending",
  reviewing: "badge badge-reviewing",
  reported: "badge badge-reported",
  archived: "badge badge-archived",
};

const LABELS: Record<string, string> = {
  pending: "Pending",
  reviewing: "Reviewing",
  reported: "Reported",
  archived: "Archived",
};

export default function WorkflowBadge({ status }: { status: string }) {
  return (
    <span className={BADGE_CLASSES[status] ?? "badge bg-gray-100 text-gray-600"}>
      {LABELS[status] ?? status}
    </span>
  );
}
