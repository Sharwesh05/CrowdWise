"use client";

import { useState } from "react";
import { FlaskConical } from "lucide-react";

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
  Select,
  useToast,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useDemoControl } from "@/hooks";

/**
 * DEMO CONTROL — admin only, and only when DEMO_MODE is on.
 *
 * These compress time (a deadline, a settlement) so the lifecycle can be shown
 * in a few minutes. They never fabricate a payment and never bypass signature
 * verification — the backend refuses all of them outside demo mode.
 */
const ACTIONS = [
  { value: "run_analysis", label: "Trigger AI analysis", needs: "campaign" },
  { value: "simulate_deadline", label: "Simulate deadline reached", needs: "campaign" },
  { value: "mark_target_missed", label: "Mark target missed", needs: "campaign" },
  { value: "open_governance", label: "Open governance round", needs: "campaign" },
  { value: "close_governance", label: "Close governance and apply outcome", needs: "campaign" },
  { value: "retry_blockchain", label: "Retry blockchain sync", needs: "campaign" },
  { value: "refresh_insights", label: "Refresh community insights", needs: "campaign" },
  { value: "process_refunds", label: "Process refunds", needs: "campaign" },
  { value: "complete_kyc", label: "Complete KYC for a user", needs: "email" },
  { value: "analyze_pending_feedback", label: "Classify pending feedback", needs: "none" },
] as const;

export function DemoControls() {
  const control = useDemoControl();
  const { notify } = useToast();

  const [action, setAction] = useState<string>(ACTIONS[0].value);
  const [campaign, setCampaign] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const selected = ACTIONS.find((item) => item.value === action)!;

  const run = async () => {
    setError(null);
    setResult(null);
    try {
      const response = await control.mutateAsync({
        action,
        campaign_public_id: selected.needs === "campaign" ? campaign.trim() : undefined,
        user_email: selected.needs === "email" ? email.trim() : undefined,
      });
      setResult(response.detail);
      notify({ title: response.message, tone: "positive" });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The demo action failed.");
    }
  };

  const canRun =
    selected.needs === "none" ||
    (selected.needs === "campaign" && campaign.trim().length > 0) ||
    (selected.needs === "email" && email.trim().length > 0);

  return (
    <Card className="border-caution/40 bg-caution-soft/20">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-caution-strong" aria-hidden />
            Demo controls
          </CardTitle>
          <Badge tone="caution">DEMO CONTROL</Badge>
        </div>
        <p className="text-xs text-ink-muted">
          Admin-only shortcuts for the live demo. Disabled entirely when DEMO_MODE is off.
        </p>
      </CardHeader>

      <CardContent className="space-y-3">
        {error && <Alert tone="critical">{error}</Alert>}

        <Field label="Action" htmlFor="demo-action">
          <Select value={action} onChange={(event) => setAction(event.target.value)}>
            {ACTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </Select>
        </Field>

        {selected.needs === "campaign" && (
          <Field label="Campaign ID" htmlFor="demo-campaign" hint="For example CMP-101">
            <Input
              value={campaign}
              onChange={(event) => setCampaign(event.target.value.toUpperCase())}
              placeholder="CMP-101"
            />
          </Field>
        )}

        {selected.needs === "email" && (
          <Field label="User email" htmlFor="demo-email">
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="creator@example.com"
            />
          </Field>
        )}

        <Button
          className="w-full"
          variant="secondary"
          loading={control.isPending}
          disabled={!canRun}
          onClick={run}
        >
          Run action
        </Button>

        {result && (
          <pre className="max-h-40 overflow-auto rounded-lg bg-surface p-3 text-2xs text-ink-soft">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}
