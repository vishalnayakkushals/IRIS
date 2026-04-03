interface Props {
  status: string;
}

const CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  running:  { bg: "bg-orange-100", text: "text-orange-700", label: "In Progress" },
  queued:   { bg: "bg-pink-100",   text: "text-pink-700",   label: "Added To Queue" },
  done:     { bg: "bg-green-100",  text: "text-green-700",  label: "Done" },
  failed:   { bg: "bg-red-100",    text: "text-red-700",    label: "Failed" },
  idle:     { bg: "bg-gray-100",   text: "text-gray-600",   label: "Idle" },
};

export default function StatusBadge({ status }: Props) {
  const cfg = CONFIG[status] ?? CONFIG.idle;
  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${cfg.bg} ${cfg.text}`}
    >
      {cfg.label}
    </span>
  );
}
