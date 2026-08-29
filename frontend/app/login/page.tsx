"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Button, Card, CardContent, Field, Input } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useLogin } from "@/hooks";

function dashboardFor(role: string): string {
  if (role === "ADMIN") return "/admin/dashboard";
  if (role === "CREATOR") return "/creator/dashboard";
  return "/contributor/dashboard";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const login = useLogin();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const next = params.get("next");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const result = await login.mutateAsync({ email: email.trim(), password });
      router.push(next || dashboardFor(result.user.role));
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Sign in failed. Please try again.",
      );
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error && (
        <Alert tone="critical" title="Could not sign in">
          {error}
        </Alert>
      )}

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

      <Field label="Password" htmlFor="password" required>
        <Input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••"
        />
      </Field>

      <Button type="submit" className="w-full" loading={login.isPending}>
        Sign in
      </Button>
    </form>
  );
}

export default function LoginPage() {
  const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

  return (
    <div className="container-page flex min-h-[calc(100vh-8rem)] items-center justify-center py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
          <p className="mt-1.5 text-sm text-ink-muted">
            Sign in to fund campaigns, vote, or manage your own.
          </p>
        </div>

        <Card>
          <CardContent className="p-6">
            <Suspense fallback={<div className="skeleton h-64 w-full" />}>
              <LoginForm />
            </Suspense>

            <p className="mt-5 text-center text-sm text-ink-muted">
              New to CrowdWise?{" "}
              <Link href="/register" className="font-medium text-brand-700 hover:underline">
                Create an account
              </Link>
            </p>
          </CardContent>
        </Card>

        {demoMode && (
          <Card className="mt-4 border-caution/30 bg-caution-soft/40">
            <CardContent className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-caution-strong">
                Demo accounts
              </p>
              <p className="mt-1 text-xs text-ink-muted">
                Local development only. Password for all three:{" "}
                <code className="rounded bg-surface px-1 py-0.5 font-mono">Demo@12345</code>
              </p>
              <ul className="mt-2 space-y-1 text-xs text-ink-soft">
                <li>
                  <span className="font-medium">Admin</span> — admin@example.com
                </li>
                <li>
                  <span className="font-medium">Creator</span> — creator@example.com
                </li>
                <li>
                  <span className="font-medium">Contributor</span> — contributor@example.com
                </li>
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
