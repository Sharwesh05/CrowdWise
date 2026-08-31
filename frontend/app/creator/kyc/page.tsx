"use client";

import Link from "next/link";
import { useState } from "react";
import { BadgeCheck, Loader2, ShieldAlert } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Field,
  Input,
  Textarea,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCompleteKyc, useKycStatus, useSubmitKyc } from "@/hooks";

const STEPS = ["SUBMITTED", "PROCESSING", "VERIFIED"] as const;

export default function KycPage() {
  return (
    <RequireRole roles={["CREATOR", "ADMIN"]}>
      <KycContent />
    </RequireRole>
  );
}

function KycContent() {
  const { data: status } = useKycStatus();
  const submit = useSubmitKyc();
  const complete = useCompleteKyc();
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    full_name: "",
    date_of_birth: "",
    pan_number: "",
    address: "",
    bank_account_number: "",
    bank_ifsc: "",
  });

  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const verified = status?.status === "VERIFIED";
  const inFlight = status?.status === "SUBMITTED" || status?.status === "PROCESSING";

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await submit.mutateAsync({ ...form, confirm_demo_data: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not submit verification.");
    }
  };

  return (
    <div className="container-page py-10">
      <div className="mx-auto max-w-2xl">
        <header className="mb-6">
          <Badge tone="caution" className="mb-3">
            DEMO KYC MODE
          </Badge>
          <h1 className="text-2xl font-semibold tracking-tight">Identity verification</h1>
          <p className="mt-2 text-ink-muted">
            Creators must be verified before a campaign can be reviewed. This is the gate that
            makes &ldquo;verified creator&rdquo; mean something.
          </p>
        </header>

        <Alert tone="caution" title="This is a simulated verification" className="mb-6">
          Submit test values only. Do not enter a real PAN, a real bank account, or any real
          identity document. Nothing here is sent to a real verification provider, written to the
          blockchain, or shown publicly.
        </Alert>

        {/* Progress */}
        <Card className="mb-6">
          <CardContent className="p-5">
            <ol className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              {STEPS.map((step, index) => {
                const reachedIndex = status ? STEPS.indexOf(status.status as typeof STEPS[number]) : -1;
                const done = reachedIndex >= index && reachedIndex !== -1;
                const active = status?.status === step;
                return (
                  <li key={step} className="flex flex-1 items-center gap-2">
                    <span
                      className={cn(
                        "grid h-8 w-8 shrink-0 place-items-center rounded-full border text-xs font-semibold",
                        done
                          ? "border-brand-600 bg-brand-600 text-white"
                          : "border-surface-border text-ink-faint",
                      )}
                    >
                      {active && step !== "VERIFIED" ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                      ) : done ? (
                        <BadgeCheck className="h-4 w-4" aria-hidden />
                      ) : (
                        index + 1
                      )}
                    </span>
                    <span
                      className={cn(
                        "text-xs font-medium",
                        done ? "text-ink" : "text-ink-faint",
                      )}
                    >
                      {step.charAt(0) + step.slice(1).toLowerCase()}
                    </span>
                    {index < STEPS.length - 1 && (
                      <span className="mx-2 hidden h-px flex-1 bg-surface-border sm:block" />
                    )}
                  </li>
                );
              })}
            </ol>
          </CardContent>
        </Card>

        {verified ? (
          <Card className="border-positive/30">
            <CardContent className="space-y-4 p-6 text-center">
              <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-positive-soft">
                <BadgeCheck className="h-6 w-6 text-positive-strong" aria-hidden />
              </span>
              <div>
                <h2 className="text-lg font-semibold text-ink">Identity verified</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  Verified {formatDateTime(status?.verified_at)} · reference{" "}
                  <span className="font-mono text-xs">{status?.reference}</span>
                </p>
              </div>

              {status?.checks && (
                <ul className="mx-auto max-w-sm space-y-1.5 text-left">
                  {Object.entries(status.checks).map(([check, result]) => (
                    <li key={check} className="flex items-center justify-between text-sm">
                      <span className="text-ink-muted">
                        {check.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                      </span>
                      <Badge tone={result === "PASS" ? "positive" : "neutral"}>{result}</Badge>
                    </li>
                  ))}
                </ul>
              )}

              <Link href="/creator/campaigns/new">
                <Button>Create your campaign</Button>
              </Link>
            </CardContent>
          </Card>
        ) : inFlight ? (
          <Card>
            <CardContent className="space-y-4 p-6 text-center">
              <Loader2 className="mx-auto h-6 w-6 animate-spin text-accent-500" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-ink">Verification in progress</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  Reference <span className="font-mono text-xs">{status?.reference}</span>
                </p>
              </div>
              <Button variant="outline" loading={complete.isPending} onClick={() => complete.mutate()}>
                Check status now
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-caution" aria-hidden />
                Submit demo verification
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                {error && <Alert tone="critical">{error}</Alert>}

                <Field label="Full name" htmlFor="full_name" required>
                  <Input
                    value={form.full_name}
                    onChange={(event) => set("full_name")(event.target.value)}
                    placeholder="Asha Menon"
                    required
                  />
                </Field>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Date of birth" htmlFor="date_of_birth" required>
                    <Input
                      type="date"
                      value={form.date_of_birth}
                      onChange={(event) => set("date_of_birth")(event.target.value)}
                      required
                    />
                  </Field>

                  <Field
                    label="PAN (demo)"
                    htmlFor="pan_number"
                    required
                    hint="Test format only, e.g. ABCDE1234F"
                  >
                    <Input
                      value={form.pan_number}
                      onChange={(event) => set("pan_number")(event.target.value.toUpperCase())}
                      placeholder="ABCDE1234F"
                      maxLength={10}
                      required
                    />
                  </Field>
                </div>

                <Field label="Address" htmlFor="address" required>
                  <Textarea
                    rows={3}
                    value={form.address}
                    onChange={(event) => set("address")(event.target.value)}
                    placeholder="12 Demo Street, Test Nagar, Bengaluru 560001"
                    required
                  />
                </Field>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field
                    label="Bank account (demo)"
                    htmlFor="bank_account_number"
                    required
                    hint="Test digits only"
                  >
                    <Input
                      value={form.bank_account_number}
                      onChange={(event) => set("bank_account_number")(event.target.value)}
                      placeholder="000123456789"
                      required
                    />
                  </Field>

                  <Field label="IFSC (demo)" htmlFor="bank_ifsc" required hint="11 characters">
                    <Input
                      value={form.bank_ifsc}
                      onChange={(event) => set("bank_ifsc")(event.target.value.toUpperCase())}
                      placeholder="DEMO0001234"
                      maxLength={11}
                      required
                    />
                  </Field>
                </div>

                <Field
                  label="Identity document (demo)"
                  htmlFor="document"
                  hint="Optional in demo mode. Do not upload a real document."
                >
                  <Input id="document" type="file" accept="image/*,.pdf" disabled />
                </Field>

                <Button type="submit" className="w-full" loading={submit.isPending}>
                  Submit for verification
                </Button>
              </form>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
