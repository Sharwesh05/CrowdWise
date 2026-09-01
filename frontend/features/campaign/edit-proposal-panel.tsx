"use client";

import { useState } from "react";
import { Info, Save } from "lucide-react";

import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Field,
  Input,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { CATEGORY_LABELS } from "@/lib/utils";
import { useUpdateCampaign } from "@/hooks";
import type { CreatorCampaign } from "@/types";

/** Mirrors the server-side minimums so the button disables before a 422 does. */
const MIN = {
  title: 6,
  short_description: 20,
  description: 100,
  problem_statement: 40,
  proposed_solution: 40,
};

function toDateInput(iso: string): string {
  return iso ? iso.slice(0, 10) : "";
}

/**
 * Correcting a proposal that has not yet been decided on.
 *
 * The campaign is still the creator's while it waits in the review queue, so a
 * wrong figure or a missing detail can be fixed here rather than costing a
 * rejection. Every save is audited, and a reviewer looking at a proposal that
 * changed after its AI analysis is told so on their own screen — which is what
 * makes editing under review safe to allow rather than something to hide.
 */
export function EditProposalPanel({ campaign }: { campaign: CreatorCampaign }) {
  const update = useUpdateCampaign(campaign.id);
  const { notify } = useToast();
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    title: campaign.title,
    short_description: campaign.short_description,
    description: campaign.description,
    problem_statement: campaign.problem_statement,
    proposed_solution: campaign.proposed_solution,
    expected_impact: campaign.expected_impact ?? "",
    category: campaign.category,
    target_amount: String(campaign.target_amount),
    minimum_contribution: String(campaign.minimum_contribution),
    deadline: toDateInput(campaign.deadline),
  });

  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const tooShort = (key: keyof typeof MIN) =>
    form[key].length > 0 && form[key].length < MIN[key]
      ? `At least ${MIN[key]} characters (currently ${form[key].length}).`
      : undefined;

  const valid =
    Object.keys(MIN).every(
      (key) => form[key as keyof typeof MIN].length >= MIN[key as keyof typeof MIN],
    ) &&
    Number(form.target_amount) > 0 &&
    Number(form.minimum_contribution) > 0 &&
    Number(form.minimum_contribution) <= Number(form.target_amount);

  if (!campaign.editable) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Edit proposal</CardTitle>
        </CardHeader>
        <CardContent>
          <Alert tone="info">
            A campaign in {campaign.status.replace(/_/g, " ").toLowerCase()} can no longer be
            edited. Contributors funded this campaign against the text as it stands, so it is
            fixed from publication onwards.
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await update.mutateAsync({
        ...form,
        expected_impact: form.expected_impact || null,
        target_amount: Number(form.target_amount).toFixed(2),
        minimum_contribution: Number(form.minimum_contribution).toFixed(2),
        deadline: new Date(`${form.deadline}T23:59:59`).toISOString(),
      });
      notify({ tone: "positive", title: "Proposal updated." });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save your changes.");
    }
  };

  const underReview = campaign.status === "UNDER_REVIEW";

  return (
    <form onSubmit={submit} className="space-y-6" noValidate>
      {error && <Alert tone="critical">{error}</Alert>}

      {underReview && (
        <Alert tone="caution" title="This campaign is with a reviewer">
          <span className="flex gap-2">
            <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
              You can still correct it. The reviewer is shown that the proposal changed after
              the AI analysis ran, so re-run the analysis from the Lifecycle tab if your edits
              are substantial.
            </span>
          </span>
        </Alert>
      )}

      {campaign.review_notes && (
        <Alert tone="caution" title="Reviewer notes">
          {campaign.review_notes}
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>The basics</CardTitle>
          <CardDescription>
            Specifics — numbers, partners, timelines — score better than adjectives.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Campaign title" htmlFor="edit-title" required error={tooShort("title")}>
            <Input
              id="edit-title"
              value={form.title}
              onChange={(event) => set("title")(event.target.value)}
              required
            />
          </Field>

          <Field
            label="One-line summary"
            htmlFor="edit-short"
            required
            error={tooShort("short_description")}
          >
            <Input
              id="edit-short"
              value={form.short_description}
              onChange={(event) => set("short_description")(event.target.value)}
              required
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Category" htmlFor="edit-category" required>
              <Select
                id="edit-category"
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

            <Field label="Funding deadline" htmlFor="edit-deadline" required>
              <Input
                id="edit-deadline"
                type="date"
                value={form.deadline}
                onChange={(event) => set("deadline")(event.target.value)}
                required
              />
            </Field>

            <Field label="Target amount (₹)" htmlFor="edit-target" required>
              <Input
                id="edit-target"
                type="number"
                min="1"
                value={form.target_amount}
                onChange={(event) => set("target_amount")(event.target.value)}
                required
              />
            </Field>

            <Field label="Minimum contribution (₹)" htmlFor="edit-minimum" required>
              <Input
                id="edit-minimum"
                type="number"
                min="1"
                value={form.minimum_contribution}
                onChange={(event) => set("minimum_contribution")(event.target.value)}
                required
              />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>The proposal</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field
            label="Problem statement"
            htmlFor="edit-problem"
            required
            error={tooShort("problem_statement")}
          >
            <Textarea
              id="edit-problem"
              rows={4}
              value={form.problem_statement}
              onChange={(event) => set("problem_statement")(event.target.value)}
              required
            />
          </Field>

          <Field
            label="Proposed solution"
            htmlFor="edit-solution"
            required
            error={tooShort("proposed_solution")}
          >
            <Textarea
              id="edit-solution"
              rows={4}
              value={form.proposed_solution}
              onChange={(event) => set("proposed_solution")(event.target.value)}
              required
            />
          </Field>

          <Field label="Expected impact" htmlFor="edit-impact">
            <Textarea
              id="edit-impact"
              rows={3}
              value={form.expected_impact}
              onChange={(event) => set("expected_impact")(event.target.value)}
            />
          </Field>

          <Field
            label="Full description"
            htmlFor="edit-description"
            required
            error={tooShort("description")}
            hint="Include a budget breakdown, milestones and team background. This is what the AI analysis and the reviewer read most closely."
          >
            <Textarea
              id="edit-description"
              rows={10}
              value={form.description}
              onChange={(event) => set("description")(event.target.value)}
              required
            />
          </Field>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button type="submit" loading={update.isPending} disabled={!valid}>
          <Save className="mr-1.5 h-4 w-4" aria-hidden />
          Save changes
        </Button>
      </div>
    </form>
  );
}
