"use client";

/**
 * CrowdWise UI primitives.
 *
 * A small, deliberately plain component set in the shadcn/ui idiom: composable,
 * unstyled-by-default variants, accessible by construction. Everything that can
 * be a native element is one, so keyboard and screen-reader behaviour comes free.
 */

import * as React from "react";
import { AlertCircle, Check, ChevronDown, Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------
type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger" | "link";
type ButtonSize = "sm" | "md" | "lg" | "icon";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 shadow-sm",
  secondary: "bg-ink text-white hover:bg-ink-soft active:bg-ink",
  outline: "border border-surface-border bg-surface text-ink hover:bg-surface-muted",
  ghost: "text-ink-soft hover:bg-surface-muted hover:text-ink",
  danger: "bg-critical text-white hover:bg-critical-strong",
  link: "text-brand-700 underline-offset-4 hover:underline p-0 h-auto",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
  icon: "h-10 w-10",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leadingIcon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, leadingIcon, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      // `aria-busy` tells assistive tech the control is working, not broken.
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
        "disabled:pointer-events-none disabled:opacity-50",
        BUTTON_VARIANTS[variant],
        variant !== "link" && BUTTON_SIZES[size],
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : leadingIcon}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("card", className)} {...props} />;
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 p-5 pb-3", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-base font-semibold text-ink", className)} {...props} />;
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-ink-muted", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5 pt-0", className)} {...props} />;
}

export function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-center gap-3 border-t border-surface-border p-5", className)} {...props} />;
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------
type BadgeTone = "neutral" | "info" | "positive" | "caution" | "critical" | "brand";

const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-muted text-ink-muted",
  info: "bg-accent-50 text-accent-700",
  positive: "bg-positive-soft text-positive-strong",
  caution: "bg-caution-soft text-caution-strong",
  critical: "bg-critical-soft text-critical-strong",
  brand: "bg-brand-50 text-brand-700",
};

export function Badge({
  tone = "neutral",
  className,
  dot,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone; dot?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        BADGE_TONES[tone],
        className,
      )}
      {...props}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />}
      {props.children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Form controls
// ---------------------------------------------------------------------------
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-11 w-full rounded-lg border border-surface-border bg-surface px-3 text-base text-ink",
        "sm:h-10 sm:text-sm",
        "placeholder:text-ink-faint",
        "disabled:cursor-not-allowed disabled:bg-surface-muted",
        "aria-[invalid=true]:border-critical",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full rounded-lg border border-surface-border bg-surface p-3 text-base text-ink sm:text-sm",
      "placeholder:text-ink-faint",
      "aria-[invalid=true]:border-critical",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <div className="relative">
    <select
      ref={ref}
      className={cn(
        "h-11 w-full appearance-none rounded-lg border border-surface-border bg-surface px-3 pr-9 text-base text-ink",
        "sm:h-10 sm:text-sm",
        className,
      )}
      {...props}
    >
      {children}
    </select>
    <ChevronDown
      className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint"
      aria-hidden
    />
  </div>
));
Select.displayName = "Select";

export function Label({
  className,
  required,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement> & { required?: boolean }) {
  return (
    <label className={cn("label-text", className)} {...props}>
      {props.children}
      {required && (
        <span className="ml-0.5 text-critical" aria-hidden>
          *
        </span>
      )}
    </label>
  );
}

export function Field({
  label,
  htmlFor,
  error,
  hint,
  required,
  children,
  className,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const errorId = `${htmlFor}-error`;
  const hintId = `${htmlFor}-hint`;
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={htmlFor} required={required}>
        {label}
      </Label>
      {/* aria-describedby wires the hint and error to the control itself. */}
      {React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement, {
            id: htmlFor,
            "aria-invalid": error ? true : undefined,
            "aria-describedby": cn(hint && hintId, error && errorId) || undefined,
          })
        : children}
      {hint && !error && (
        <p id={hintId} className="hint-text">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="flex items-center gap-1 text-xs text-critical">
          <AlertCircle className="h-3 w-3" aria-hidden />
          {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Progress
// ---------------------------------------------------------------------------
export function Progress({
  value,
  className,
  barClassName,
  label,
}: {
  value: number;
  className?: string;
  barClassName?: string;
  label?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-surface-muted", className)}
    >
      <div
        className={cn("h-full rounded-full bg-brand-500 transition-[width] duration-500", barClassName)}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton / states
// ---------------------------------------------------------------------------
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-4 w-full", className)} aria-hidden />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-xl border border-dashed border-surface-border bg-surface px-6 py-12 text-center", className)}>
      {icon && <div className="mb-3 text-ink-faint">{icon}</div>}
      <p className="text-sm font-medium text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-ink-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn("rounded-xl border border-critical/20 bg-critical-soft/40 p-5 text-center", className)}
    >
      <AlertCircle className="mx-auto mb-2 h-5 w-5 text-critical" aria-hidden />
      <p className="text-sm font-medium text-ink">{title}</p>
      {message && <p className="mt-1 text-sm text-ink-muted">{message}</p>}
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: "info" | "positive" | "caution" | "critical";
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const tones = {
    info: "border-accent-300/50 bg-accent-50 text-accent-700",
    positive: "border-positive/25 bg-positive-soft text-positive-strong",
    caution: "border-caution/25 bg-caution-soft text-caution-strong",
    critical: "border-critical/25 bg-critical-soft text-critical-strong",
  } as const;
  return (
    <div className={cn("rounded-lg border p-3 text-sm", tones[tone], className)}>
      {title && <p className="font-medium">{title}</p>}
      {children && <div className={cn(title && "mt-1", "text-ink-soft")}>{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dialog — native <dialog> so focus trapping and Esc come from the platform
// ---------------------------------------------------------------------------
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  const ref = React.useRef<HTMLDialogElement>(null);

  React.useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  React.useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const handleCancel = (event: Event) => {
      event.preventDefault();
      onClose();
    };
    element.addEventListener("cancel", handleCancel);
    return () => element.removeEventListener("cancel", handleCancel);
  }, [onClose]);

  const widths = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl" };

  return (
    <dialog
      ref={ref}
      aria-labelledby="dialog-title"
      className={cn(
        "w-[calc(100vw-2rem)] rounded-xl border border-surface-border bg-surface p-0 shadow-popover",
        // A tall dialog on a phone must scroll inside itself rather than run off
        // the bottom of the viewport. `dvh` keeps it correct while mobile
        // browser chrome slides in and out.
        "max-h-[calc(100dvh-2rem)] overflow-hidden",
        "backdrop:bg-ink/40 backdrop:backdrop-blur-sm",
        widths[size],
      )}
      onClick={(event) => {
        // Click on the backdrop (outside the panel) closes the dialog.
        if (event.target === ref.current) onClose();
      }}
    >
      {/* Header and footer stay put; only the body scrolls. */}
      <div className="flex max-h-[calc(100dvh-2rem)] flex-col">
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-surface-border p-5">
          <div className="min-w-0">
            <h2 id="dialog-title" className="text-base font-semibold text-ink">
              {title}
            </h2>
            {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="-m-1 shrink-0 rounded-md p-2 text-ink-faint transition-colors hover:bg-surface-muted hover:text-ink"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto overscroll-contain p-5">{children}</div>
        {footer && (
          // Stacked on a phone (primary action on top, thumb-reachable), inline
          // from sm up.
          <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-surface-border p-5 sm:flex-row sm:justify-end sm:gap-3">
            {footer}
          </div>
        )}
      </div>
    </dialog>
  );
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cn("no-scrollbar flex gap-1 overflow-x-auto border-b border-surface-border", className)}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          type="button"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            active === tab.id
              ? "border-brand-600 text-ink"
              : "border-transparent text-ink-muted hover:text-ink",
          )}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="ml-1.5 text-xs text-ink-faint">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat tile
// ---------------------------------------------------------------------------
export function Stat({
  label,
  value,
  sublabel,
  icon,
  tone,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sublabel?: React.ReactNode;
  icon?: React.ReactNode;
  tone?: string;
  className?: string;
}) {
  return (
    <div className={cn("card p-4", className)}>
      <div className="flex items-start justify-between gap-2">
        <p className="stat-label">{label}</p>
        {icon && <span className="text-ink-faint">{icon}</span>}
      </div>
      <p className={cn("stat-value mt-2", tone)}>{value}</p>
      {sublabel && <p className="mt-1 text-xs text-ink-muted">{sublabel}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rating
// ---------------------------------------------------------------------------
export function StarRating({
  value,
  onChange,
  size = 20,
  readOnly = false,
  className,
}: {
  value: number;
  onChange?: (value: number) => void;
  size?: number;
  readOnly?: boolean;
  className?: string;
}) {
  const stars = [1, 2, 3, 4, 5];
  if (readOnly) {
    return (
      <span className={cn("inline-flex items-center gap-0.5", className)} aria-label={`${value} out of 5`}>
        {stars.map((star) => (
          <Star key={star} filled={star <= Math.round(value)} size={size} />
        ))}
      </span>
    );
  }
  return (
    <div role="radiogroup" aria-label="Rating" className={cn("inline-flex items-center gap-1", className)}>
      {stars.map((star) => (
        <button
          key={star}
          type="button"
          role="radio"
          aria-checked={value === star}
          aria-label={`${star} star${star > 1 ? "s" : ""}`}
          onClick={() => onChange?.(star)}
          className="rounded p-0.5 transition-transform hover:scale-110"
        >
          <Star filled={star <= value} size={size} />
        </button>
      ))}
    </div>
  );
}

function Star({ filled, size }: { filled: boolean; size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "#F59E0B" : "none"}
      stroke={filled ? "#F59E0B" : "#CBD5E1"}
      strokeWidth={1.5}
      aria-hidden
    >
      <path d="M12 2.5l2.9 5.9 6.5.9-4.7 4.6 1.1 6.5L12 17.4l-5.8 3 1.1-6.5L2.6 9.3l6.5-.9L12 2.5z" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Copy-to-clipboard
// ---------------------------------------------------------------------------
export function CopyButton({
  value,
  label = "Copy",
  className,
  size = "sm",
}: {
  value: string;
  label?: string;
  className?: string;
  size?: ButtonSize;
}) {
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // Clipboard can be blocked; fall back to a selectable prompt.
      window.prompt("Copy this:", value);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <Button variant="outline" size={size} onClick={copy} className={className}>
      {copied ? <Check className="h-3.5 w-3.5 text-positive" aria-hidden /> : null}
      {copied ? "Copied" : label}
    </Button>
  );
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
interface ToastMessage {
  id: number;
  title: string;
  description?: string;
  tone: "info" | "positive" | "critical";
}

/** `tone` is optional; it defaults to "info".  */
type ToastInput = Omit<ToastMessage, "id" | "tone"> & { tone?: ToastMessage["tone"] };

const ToastContext = React.createContext<{
  notify: (message: ToastInput) => void;
}>({ notify: () => undefined });

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = React.useState<ToastMessage[]>([]);

  const notify = React.useCallback((message: ToastInput) => {
    const id = Date.now() + Math.random();
    setMessages((current) => [...current, { tone: "info", ...message, id }]);
    setTimeout(() => setMessages((current) => current.filter((m) => m.id !== id)), 5000);
  }, []);

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      {/* aria-live so screen readers announce results without stealing focus. */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col gap-2 sm:left-auto sm:right-4 sm:w-full sm:max-w-sm"
      >
        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              "pointer-events-auto animate-fade-in rounded-lg border bg-surface p-3 shadow-popover",
              message.tone === "positive" && "border-positive/30",
              message.tone === "critical" && "border-critical/30",
              message.tone === "info" && "border-surface-border",
            )}
          >
            <p className="text-sm font-medium text-ink">{message.title}</p>
            {message.description && <p className="mt-0.5 text-sm text-ink-muted">{message.description}</p>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return React.useContext(ToastContext);
}
