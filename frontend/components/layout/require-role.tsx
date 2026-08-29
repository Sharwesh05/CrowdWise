"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Lock } from "lucide-react";

import { Button, EmptyState, Skeleton } from "@/components/ui";
import { useSession } from "@/hooks";
import type { UserRole } from "@/types";

/**
 * Client-side role gate.
 *
 * This is a UX convenience only — every protected endpoint enforces the same
 * rule server-side, so bypassing this component gains nothing.
 */
export function RequireRole({
  roles,
  children,
}: {
  roles: UserRole[];
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { data: user, isLoading } = useSession();

  useEffect(() => {
    if (!isLoading && !user) {
      const next = typeof window !== "undefined" ? window.location.pathname : "/";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [isLoading, user, router]);

  if (isLoading) {
    return (
      <div className="container-page space-y-4 py-10">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!user) return null;

  if (!roles.includes(user.role)) {
    return (
      <div className="container-page py-16">
        <EmptyState
          icon={<Lock className="h-6 w-6" />}
          title="You do not have access to this page"
          description={`This area is for ${roles.join(" and ").toLowerCase()} accounts. You are signed in as ${user.role.toLowerCase()}.`}
          action={
            <Link href="/campaigns">
              <Button size="sm" variant="outline">
                Browse campaigns
              </Button>
            </Link>
          }
        />
      </div>
    );
  }

  return <>{children}</>;
}
