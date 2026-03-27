type Props = {
  status: string;
};

const colorMap: Record<string, string> = {
  queued: "badge badge-queued",
  running: "badge badge-running",
  succeeded: "badge badge-succeeded",
  failed: "badge badge-failed",
  pending_review: "badge badge-pending",
  approved: "badge badge-approved",
  rejected: "badge badge-rejected",
};

export function StatusBadge({ status }: Props) {
  return <span className={colorMap[status] ?? "badge"}>{status}</span>;
}

