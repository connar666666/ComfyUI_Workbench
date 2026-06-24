type Status = "queued" | "running" | "succeeded" | "failed" | "canceled";

const STATUS_LABELS: Record<Status, string> = {
  queued: "排队中",
  running: "运行中",
  succeeded: "成功",
  failed: "失败",
  canceled: "已取消",
};

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABELS[status]}</span>;
}
