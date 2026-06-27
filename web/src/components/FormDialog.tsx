import { useEffect, useId } from "react";
import type { MouseEvent, ReactNode } from "react";
import { X } from "lucide-react";

type FormDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
};

export function FormDialog({ open, title, description, onClose, children }: FormDialogProps) {
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  const handleBackdropClick = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="form-dialog-backdrop" onClick={handleBackdropClick}>
      <div
        className="form-dialog glass-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
      >
        <div className="form-dialog-header">
          <div>
            <h2 id={titleId} className="form-dialog-title">{title}</h2>
            {description ? <p id={descriptionId} className="form-dialog-description">{description}</p> : null}
          </div>
          <button type="button" className="form-dialog-close" onClick={onClose} aria-label="关闭弹窗">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
