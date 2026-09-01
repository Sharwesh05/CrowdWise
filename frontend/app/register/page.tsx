"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { HeartHandshake, Rocket } from "lucide-react";

import { Alert, Button, Card, CardContent, Field, Input } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useRegister } from "@/hooks";

const ROLES = [
  {
    value: "CONTRIBUTOR",
    icon: HeartHandshake,
    title: "I want to support campaigns",
    body: "Discover campaigns, contribute, leave feedback and vote on outcomes.",
  },
  {
    value: "CREATOR",
    icon: Rocket,
    title: "I want to run a campaign",
    body: "Get verified, submit a proposal for review, and raise from the community.",
  },
];

function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const register = useRegister();

  const [role, setRole] = useState(params.get("role") === "CREATOR" ? "CREATOR" : "CONTRIBUTOR");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const passwordIssue =
    password.length > 0 && password.length < 8
      ? "At least 8 characters."
      : password.length > 0 && !/\d/.test(password)
        ? "Include at least one number."
        : password.length > 0 && !/[a-zA-Z]/.test(password)
          ? "Include at least one letter."
          : undefined;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await register.mutateAsync({
        name: name.trim(),
        email: email.trim(),
        password,
        role,
        phone: phone.trim() || undefined,
      });
      router.push(role === "CREATOR" ? "/creator/kyc" : "/campaigns");
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Could not create your account.",
      );
    }
  };

  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      {error && (
        <Alert tone="critical" title="Could not register">
          {error}
        </Alert>
      )}

      <fieldset>
        <legend className="label-text mb-2">I am joining to…</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          {ROLES.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={role === option.value}
              onClick={() => setRole(option.value)}
              className={cn(
                "rounded-lg border p-4 text-left transition-all",
                role === option.value
                  ? "border-brand-600 bg-brand-50 shadow-sm"
                  : "border-surface-border hover:border-ink-faint",
              )}
            >
              <option.icon
                className={cn(
                  "h-5 w-5",
                  role === option.value ? "text-brand-700" : "text-ink-faint",
                )}
                aria-hidden
              />
              <span className="mt-2 block text-sm font-medium text-ink">{option.title}</span>
              <span className="mt-1 block text-xs leading-relaxed text-ink-muted">
                {option.body}
              </span>
            </button>
          ))}
        </div>
      </fieldset>

      <Field label="Full name" htmlFor="name" required>
        <Input
          autoComplete="name"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Asha Menon"
        />
      </Field>

      <Field label="Email" htmlFor="email" required>
        <Input
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
        />
      </Field>

      <Field label="Phone" htmlFor="phone" hint="Optional.">
        <Input
          type="tel"
          autoComplete="tel"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          placeholder="+91 98765 43210"
        />
      </Field>

      <Field
        label="Password"
        htmlFor="password"
        required
        error={passwordIssue}
        hint="At least 8 characters, with a letter and a number."
      >
        <Input
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>

      <Button
        type="submit"
        className="w-full"
        loading={register.isPending}
        disabled={Boolean(passwordIssue)}
      >
        Create account
      </Button>

      {role === "CREATOR" && (
        <p className="text-xs leading-relaxed text-ink-muted">
          Next you will complete identity verification and pay a small application fee before
          your campaign can be reviewed.
        </p>
      )}
    </form>
  );
}

export default function RegisterPage() {
  return (
    <div className="container-page flex min-h-[calc(100vh-8rem)] items-center justify-center py-12">
      <div className="w-full max-w-lg">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Join CrowdWise</h1>
          <p className="mt-1.5 text-sm text-ink-muted">
            Smarter Crowdfunding. Stronger Communities.
          </p>
        </div>

        <Card>
          <CardContent className="p-6">
            <Suspense fallback={<div className="skeleton h-96 w-full" />}>
              <RegisterForm />
            </Suspense>

            <p className="mt-5 text-center text-sm text-ink-muted">
              Already have an account?{" "}
              <Link href="/login" className="font-medium text-brand-700 hover:underline">
                Sign in
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
