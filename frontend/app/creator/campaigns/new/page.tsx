"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Info } from "lucide-react";

import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Field,
  Input,
  Select,
  Textarea,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { ApiError } from "@/lib/api";
import { CATEGORY_LABELS } from "@/lib/utils";
import { useCreateCampaign, useKycStatus } from "@/hooks";
import Link from "next/link";

const MIN = {
  title: 6,
  short_description: 20,
  description: 100,
  problem_statement: 40,
  proposed_solution: 40,
};

function defaultDeadline(): string {
  const date = new Date();
  date.setDate(date.getDate() + 45);
  return date.toISOString().slice(0, 10);
}

export default function NewCampaignPage() {
  return (
    <RequireRole roles={["CREATOR", "ADMIN"]}>
      <NewCampaignForm />
    </RequireRole>
  );
}

function NewCampaignForm() {
  const router = useRouter();
  const create = useCreateCampaign();
  const { data: kyc } = useKycStatus();
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    title: "",
    short_description: "",
    description: "",
    problem_statement: "",
    proposed_solution: "",
    expected_impact: "",
    category: "OTHER",
    target_amount: "1000000",
    minimum_contribution: "500",
    deadline: defaultDeadline(),
    outcome_type: "CONTRIBUTOR_VOTE",
    voting_weight_mode: "ONE_PERSON_ONE_VOTE",
  });

  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const tooShort = (key: keyof typeof MIN) =>
    form[key].length > 0 && form[key].length < MIN[key]
      ? `At least ${MIN[key]} characters (currently ${form[key].length}).`
      : undefined;

  const valid =
    Object.keys(MIN).every((key) => form[key as keyof typeof MIN].length >= MIN[key as keyof typeof MIN]) &&
    Number(form.target_amount) > 0 &&
    Number(form.minimum_contribution) > 0 &&
    Number(form.minimum_contribution) <= Number(form.target_amount);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const created = await create.mutateAsync({
        ...form,
        expected_impact: form.expected_impact || null,
        target_amount: Number(form.target_amount).toFixed(2),
        minimum_contribution: Number(form.minimum_contribution).toFixed(2),
        // Sent as an ISO instant; the backend rejects a deadline in the past.
        deadline: new Date(`${form.deadline}T23:59:59`).toISOString(),
      });
      router.push(`/creator/campaigns/${created.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the campaign.");
    }
  };

  return (
    <div className="container-page py-10">
      <div className="mx-auto max-w-3xl">
        <Link
          href="/creator/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to dashboard
        </Link>

        <header className="mt-4 mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">Create a campaign</h1>
          <p className="mt-2 text-ink-muted">
            Write the proposal a reviewer and the community will judge. Specifics — numbers,
            partners, timelines — score better than adjectives.
          </p>
        </header>

        {kyc && kyc.status !== "VERIFIED" && (
          <Alert tone="caution" title="Identity verification is not complete" className="mb-6">
            You can draft a campaign now, but it cannot be submitted for review until
            verification is done.{" "}
            <Link href="/creator/kyc" className="font-medium underline">
              Verify now
            </Link>
          </Alert>
        )}

        <form onSubmit={submit} className="space-y-6" noValidate>
          {error && <Alert tone="critical">{error}</Alert>}

          <Card>
            <CardHeader>
              <CardTitle>The basics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Campaign title" htmlFor="title" required error={tooShort("title")}>
                <Input
                  value={form.title}
                  onChange={(event) => set("title")(event.target.value)}
                  placeholder="Solar Water Purifier for Rural Schools"
                  required
                />
              </Field>

              <Field
                label="One-line summary"
                htmlFor="short_description"
                required
                error={tooShort("short_description")}
                hint="Shown on campaign cards and in search results."
              >
                <Input
                  value={form.short_description}
                  onChange={(event) => set("short_description")(event.target.value)}
                  placeholder="Solar-powered water purifiers for 40 rural schools across two districts."
                  required
                />
              </Field>

              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Category" htmlFor="category" required>
                  <Select
                    value={form.category}
                    onChange={(event) => set("category")(event.target.value)}
                  >
                    {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </Select>
                </Field>

                <Field label="Target amount (₹)" htmlFor="target_amount" required>
                  <Input
                    type="number"
                    min={1}
                    value={form.target_amount}
                    onChange={(event) => set("target_amount")(event.target.value)}
                    required
                  />
                </Field>

                <Field label="Minimum contribution (₹)" htmlFor="minimum_contribution" required>
                  <Input
                    type="number"
                    min={1}
                    value={form.minimum_contribution}
                    onChange={(event) => set("minimum_contribution")(event.target.value)}
                    required
                  />
                </Field>
              </div>

              <Field
                label="Funding deadline"
                htmlFor="deadline"
                required
                hint="Must be in the future. Short windows are flagged as a risk by the analysis."
              >
                <Input
                  type="date"
                  value={form.deadline}
                  onChange={(event) => set("deadline")(event.target.value)}
                  required
                />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>The proposal</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field
                label="Problem statement"
                htmlFor="problem_statement"
                required
                error={tooShort("problem_statement")}
                hint="What is wrong today, for whom, and how do you know?"
              >
                <Textarea
                  rows={4}
                  value={form.problem_statement}
                  onChange={(event) => set("problem_statement")(event.target.value)}
                  required
                />
              </Field>

              <Field
                label="Proposed solution"
                htmlFor="proposed_solution"
                required
                error={tooShort("proposed_solution")}
                hint="What you will build or do, who delivers it, and over what timeline."
              >
                <Textarea
                  rows={4}
                  value={form.proposed_solution}
                  onChange={(event) => set("proposed_solution")(event.target.value)}
                  required
                />
              </Field>

              <Field
                label="Expected impact"
                htmlFor="expected_impact"
                hint="Quantify it if you can — who benefits and by how much."
              >
                <Textarea
                  rows={2}
                  value={form.expected_impact}
                  onChange={(event) => set("expected_impact")(event.target.value)}
                />
              </Field>

              <Field
                label="Full description"
                htmlFor="description"
                required
                error={tooShort("description")}
                hint="Include a budget breakdown, milestones and team background. This is what the AI analysis and the reviewer read most closely."
              >
                <Textarea
                  rows={10}
                  value={form.description}
                  onChange={(event) => set("description")(event.target.value)}
                  required
                />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>If the target is missed</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert tone="info">
                <span className="flex gap-2">
                  <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  These rules are locked when the campaign is published and cannot be changed
                  afterwards. Contributors fund knowing exactly how the campaign can end.
                </span>
              </Alert>

              <Field label="Outcome rule" htmlFor="outcome_type" required>
                <Select
                  value={form.outcome_type}
                  onChange={(event) => set("outcome_type")(event.target.value)}
                >
                  <option value="CONTRIBUTOR_VOTE">
                    Contributors vote — refund or continue
                  </option>
                  <option value="AUTOMATIC_REFUND">Automatic refund to all contributors</option>
                  <option value="KEEP_WHAT_YOU_RAISE">Keep what was raised</option>
                </Select>
              </Field>

              {form.outcome_type === "CONTRIBUTOR_VOTE" && (
                <Field
                  label="Voting weight"
                  htmlFor="voting_weight_mode"
                  hint="One vote per contributor is the default and the fairest for small backers."
                >
                  <Select
                    value={form.voting_weight_mode}
                    onChange={(event) => set("voting_weight_mode")(event.target.value)}
                  >
                    <option value="ONE_PERSON_ONE_VOTE">One contributor, one vote</option>
                    <option value="CONTRIBUTION_WEIGHTED">Weighted by contribution amount</option>
                  </Select>
                </Field>
              )}
            </CardContent>
          </Card>

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Link href="/creator/dashboard" className="w-full sm:w-auto">
              <Button type="button" variant="ghost" className="w-full sm:w-auto">
                Cancel
              </Button>
            </Link>
            <Button
              type="submit"
              loading={create.isPending}
              disabled={!valid}
              className="w-full sm:w-auto"
            >
              Create draft campaign
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
