"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertCircle, Check, Loader2, ShieldCheck } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Dialog,
  Field,
  Input,
  useToast,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  useCreateContribution,
  usePaymentProgress,
  useSession,
  useSimulatePayment,
  useVerifyPayment,
} from "@/hooks";
import type { OrderResponse, PublicCampaign, VerificationProgress } from "@/types";

type Stage = "amount" | "checkout" | "progress";

const PRESETS = [500, 1000, 2500, 5000];

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

export function ContributeDialog({
  campaign,
  open,
  onClose,
}: {
  campaign: PublicCampaign;
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const { data: user } = useSession();
  const { notify } = useToast();

  const [stage, setStage] = useState<Stage>("amount");
  const [amount, setAmount] = useState(String(Number(campaign.minimum_contribution)));
  const [order, setOrder] = useState<OrderResponse | null>(null);
  const [progress, setProgress] = useState<VerificationProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Our Dialog is a native <dialog> opened with showModal(), which lives in the
  // browser's top layer. Razorpay's checkout is an ordinary div in document.body,
  // so it can never paint above us no matter its z-index — its UPI QR ends up
  // behind our panel. Stepping our dialog aside while their sheet is open is the
  // only fix; a z-index cannot cross the top layer boundary.
  const [checkoutSheetOpen, setCheckoutSheetOpen] = useState(false);

  const createOrder = useCreateContribution(campaign.public_id);
  const simulate = useSimulatePayment();
  const verify = useVerifyPayment();

  // Polls the server for the real progression once a payment is in flight.
  const polled = usePaymentProgress(order?.payment_id ?? null, stage === "progress");
  const live = polled.data ?? progress;

  const minimum = Number(campaign.minimum_contribution);
  const numericAmount = Number(amount);
  const amountValid = Number.isFinite(numericAmount) && numericAmount >= minimum;

  const reset = () => {
    setStage("amount");
    setCheckoutSheetOpen(false);
    setOrder(null);
    setProgress(null);
    setError(null);
  };

  const close = () => {
    onClose();
    // Let the closing animation finish before resetting the content.
    setTimeout(reset, 200);
  };

  const startCheckout = async () => {
    setError(null);
    if (!user) {
      router.push(`/login?next=/campaign/${campaign.public_id}`);
      return;
    }
    try {
      const created = await createOrder.mutateAsync({ amount: numericAmount.toFixed(2) });
      setOrder(created);
      setStage("checkout");
      if (created.provider === "razorpay") {
        openRazorpay(created);
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not start the payment.");
    }
  };

  const openRazorpay = (created: OrderResponse) => {
    if (typeof window === "undefined" || !window.Razorpay) {
      setError(
        "The Razorpay checkout script did not load. Check your connection and try again.",
      );
      return;
    }
    const checkout = new window.Razorpay({
      key: created.key_id,
      amount: created.amount_paise,
      currency: created.currency,
      name: "CrowdWise",
      description: campaign.title,
      order_id: created.order_id,
      prefill: { name: user?.name, email: user?.email },
      theme: { color: "#059669" },
      handler: async (response: Record<string, string>) => {
        setCheckoutSheetOpen(false);
        setStage("progress");
        try {
          // This is only a claim from the browser. The server verifies the
          // signature before anything is recorded.
          const result = await verify.mutateAsync({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          setProgress(result);
        } catch (caught) {
          setError(
            caught instanceof ApiError
              ? caught.message
              : "We could not verify this payment. If money left your account, it will be reconciled automatically.",
          );
        }
      },
      modal: {
        ondismiss: () => {
          setCheckoutSheetOpen(false);
          setStage("amount");
        },
      },
    });
    setCheckoutSheetOpen(true);
    checkout.open();
  };

  const runDemoPayment = async () => {
    if (!order) return;
    setStage("progress");
    setError(null);
    try {
      const result = await simulate.mutateAsync(order.payment_id);
      setProgress(result);
      notify({ title: "Payment verified", tone: "positive" });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The demo payment failed.");
    }
  };

  return (
    <Dialog
      open={open && !checkoutSheetOpen}
      onClose={close}
      title={stage === "progress" ? "Processing your contribution" : `Contribute to ${campaign.title}`}
      description={
        stage === "amount"
          ? `Minimum contribution ${formatCurrency(campaign.minimum_contribution)}`
          : undefined
      }
      footer={
        stage === "amount" ? (
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button onClick={startCheckout} loading={createOrder.isPending} disabled={!amountValid}>
              Continue to payment
            </Button>
          </>
        ) : stage === "checkout" && order?.provider === "demo" ? (
          <>
            <Button variant="ghost" onClick={() => setStage("amount")}>
              Back
            </Button>
            <Button onClick={runDemoPayment} loading={simulate.isPending}>
              Complete demo payment
            </Button>
          </>
        ) : (
          <Button variant={live?.contribution_recorded ? "primary" : "ghost"} onClick={close}>
            {live?.contribution_recorded ? "Done" : "Close"}
          </Button>
        )
      }
    >
      {error && (
        <Alert tone="critical" className="mb-4">
          {error}
        </Alert>
      )}

      {stage === "amount" && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {PRESETS.filter((preset) => preset >= minimum).map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => setAmount(String(preset))}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors",
                  Number(amount) === preset
                    ? "border-brand-600 bg-brand-50 text-brand-700"
                    : "border-surface-border text-ink-muted hover:border-ink-faint",
                )}
              >
                {formatCurrency(preset)}
              </button>
            ))}
          </div>

          <Field
            label="Amount (INR)"
            htmlFor="contribution-amount"
            required
            error={
              amount && !amountValid
                ? `Minimum contribution is ${formatCurrency(minimum)}.`
                : undefined
            }
            hint="Payments are processed by Razorpay in test mode."
          >
            <Input
              type="number"
              inputMode="decimal"
              min={minimum}
              step="1"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>

          <Alert tone="info">
            Your contribution is counted only after CrowdWise verifies the payment on the server.
            You will see each step as it happens.
          </Alert>
        </div>
      )}

      {stage === "checkout" && order && (
        <div className="space-y-4">
          <div className="rounded-lg border border-surface-border p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink-muted">Amount</span>
              <span className="font-semibold text-ink">{formatCurrency(order.amount)}</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-sm">
              <span className="text-ink-muted">Order</span>
              <span className="font-mono text-xs text-ink-soft">{order.order_id}</span>
            </div>
          </div>

          {order.provider === "demo" ? (
            <Alert tone="caution" title="Demo payment provider">
              No Razorpay keys are configured, so the checkout sheet is replaced by a local
              simulator. It produces a genuine signature and goes through the same
              server-side verification as a live payment.
            </Alert>
          ) : (
            <div className="flex items-center gap-2 text-sm text-ink-muted">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Opening Razorpay checkout…
            </div>
          )}
        </div>
      )}

      {stage === "progress" && <VerificationSteps progress={live} />}
    </Dialog>
  );
}

/**
 * The honest version of "Payment successful".
 *
 * Each step is a distinct server-side fact, and the blockchain step is allowed
 * to be pending or failed without implying the money did not arrive.
 */
export function VerificationSteps({ progress }: { progress: VerificationProgress | null | undefined }) {
  const anchored = progress?.blockchain_status === "BLOCKCHAIN_RECORDED";
  const anchorFailed = progress?.blockchain_status === "BLOCKCHAIN_FAILED";

  const steps = [
    { label: "Payment received", done: Boolean(progress?.payment_received) },
    { label: "Payment verified on the server", done: Boolean(progress?.payment_verified) },
    { label: "Contribution recorded", done: Boolean(progress?.contribution_recorded) },
    {
      label: anchorFailed ? "Blockchain record failed — will retry" : "Blockchain record confirmed",
      done: anchored,
      failed: anchorFailed,
    },
  ];

  return (
    <div className="space-y-4">
      <ol className="space-y-3">
        {steps.map((step, index) => {
          const active = !step.done && steps.slice(0, index).every((prior) => prior.done);
          return (
            <li key={step.label} className="flex items-start gap-3">
              <span
                className={cn(
                  "mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border",
                  step.done && "border-positive bg-positive text-white",
                  step.failed && "border-caution bg-caution-soft text-caution-strong",
                  !step.done && !step.failed && active && "border-accent-500 text-accent-500",
                  !step.done && !step.failed && !active && "border-surface-border text-ink-faint",
                )}
              >
                {step.done ? (
                  <Check className="h-3 w-3" aria-hidden />
                ) : step.failed ? (
                  <AlertCircle className="h-3 w-3" aria-hidden />
                ) : active ? (
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
                ) : null}
              </span>
              <span
                className={cn(
                  "text-sm",
                  step.done ? "text-ink" : step.failed ? "text-caution-strong" : "text-ink-muted",
                )}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>

      {progress?.webhook_verified && (
        <Badge tone="positive" dot>
          Confirmed by Razorpay webhook
        </Badge>
      )}

      {progress?.blockchain_tx && (
        <div className="rounded-lg bg-surface-muted p-3">
          <p className="text-xs font-medium text-ink">Blockchain transaction</p>
          <p className="mt-1 break-all font-mono text-xs text-ink-muted">{progress.blockchain_tx}</p>
        </div>
      )}

      {anchorFailed && (
        <Alert tone="caution" title="Your contribution is safe">
          The payment is verified and counted. Only the blockchain record is missing, and it will
          be retried automatically.
        </Alert>
      )}

      {progress?.contribution_recorded && !anchored && !anchorFailed && (
        <p className="flex items-center gap-2 text-xs text-ink-muted">
          <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
          Your payment is verified. The blockchain record is being written.
        </p>
      )}
    </div>
  );
}
