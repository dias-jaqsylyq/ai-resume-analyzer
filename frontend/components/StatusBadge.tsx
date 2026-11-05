import { STATUS_LABEL, type Status } from "@/lib/report.ts";

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge badge-${status.toLowerCase()}`}>{STATUS_LABEL[status] ?? status}</span>;
}
