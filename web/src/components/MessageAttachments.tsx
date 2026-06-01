import type { MessageAttachment } from "../types";

interface Props {
  attachments: MessageAttachment[];
  variant?: "user" | "assistant";
}

export function MessageAttachments({
  attachments,
  variant = "assistant",
}: Props) {
  if (!attachments.length) return null;
  const linkClass =
    variant === "user"
      ? "text-slate-800 underline decoration-slate-600/50"
      : "text-honey-800 underline";

  return (
    <div className="mt-2 flex flex-col gap-2">
      {attachments.map((a) => {
        const href = a.url.startsWith("/api/") ? a.url : `/api${a.url}`;
        if (a.mime_type.startsWith("image/")) {
          return (
            <a
              key={a.id}
              href={href}
              target="_blank"
              rel="noreferrer"
              className="block overflow-hidden rounded-lg border border-black/10"
            >
              <img
                src={href}
                alt={a.filename}
                className="max-h-64 max-w-full object-contain"
              />
            </a>
          );
        }
        return (
          <a
            key={a.id}
            href={href}
            target="_blank"
            rel="noreferrer"
            className={`text-xs ${linkClass}`}
          >
            📎 {a.filename} ({formatSize(a.size)})
          </a>
        );
      })}
    </div>
  );
}

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
