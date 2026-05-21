export default function WorkflowBadge({ status }: { status: string }) {
  const classes: Record<string, string> = {
    pending:   "badge badge-pending",
    reviewing: "badge badge-reviewing",
    reported:  "badge badge-reported",
    archived:  "badge badge-archived",
  };
  const labels: Record<string, string> = {
    pending:   "Pending",
    reviewing: "Reviewing",
    reported:  "Reported",
    archived:  "Archived",
  };
  return (
    <span className={classes[status] ?? "badge bg-gray-100 text-gray-600"}>
      {labels[status] ?? status}
    </span>
  );
}
