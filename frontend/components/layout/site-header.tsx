"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { LayoutDashboard, LogOut, Menu, QrCode, ShieldCheck, X } from "lucide-react";

import { Badge, Button } from "@/components/ui";
import { useLogout, useSession } from "@/hooks";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

const PUBLIC_LINKS = [
  { href: "/campaigns", label: "Explore" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/about", label: "About" },
];

function dashboardHref(role: string | undefined): string {
  if (role === "ADMIN") return "/admin/dashboard";
  if (role === "CREATOR") return "/creator/dashboard";
  return "/contributor/dashboard";
}

export function SiteHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const { data: user, isLoading } = useSession();
  const logout = useLogout();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout.mutateAsync();
    setMenuOpen(false);
    router.push("/");
  };

  return (
    <header className="sticky top-0 z-40 border-b border-surface-border bg-surface/85 backdrop-blur">
      <div className="container-page flex h-16 items-center justify-between gap-4">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2.5" aria-label="CrowdWise home">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink text-sm font-bold text-white">
              CW
            </span>
            <span className="text-base font-semibold tracking-tight text-ink">CrowdWise</span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {PUBLIC_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  pathname.startsWith(link.href)
                    ? "bg-surface-muted text-ink"
                    : "text-ink-muted hover:text-ink",
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            href="/scan"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-ink-muted transition-colors hover:text-ink"
          >
            <QrCode className="h-4 w-4" aria-hidden />
            Scan
          </Link>

          {isLoading ? (
            <div className="h-9 w-32 skeleton" />
          ) : user ? (
            <div className="flex items-center gap-3">
              <Link href={dashboardHref(user.role)}>
                <Button variant="outline" size="sm" leadingIcon={<LayoutDashboard className="h-4 w-4" />}>
                  Dashboard
                </Button>
              </Link>
              <div className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-subtle px-2.5 py-1.5">
                <span className="grid h-6 w-6 place-items-center rounded-full bg-brand-100 text-2xs font-semibold text-brand-700">
                  {initials(user.name)}
                </span>
                <div className="leading-tight">
                  <p className="text-xs font-medium text-ink">{user.name}</p>
                  <p className="text-2xs text-ink-faint">{user.role.toLowerCase()}</p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleLogout}
                loading={logout.isPending}
                aria-label="Sign out"
              >
                <LogOut className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link href="/login">
                <Button variant="ghost" size="sm">
                  Sign in
                </Button>
              </Link>
              <Link href="/register">
                <Button size="sm">Get started</Button>
              </Link>
            </div>
          )}
        </div>

        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
        >
          {menuOpen ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
        </Button>
      </div>

      {menuOpen && (
        <div className="animate-fade-in border-t border-surface-border bg-surface md:hidden">
          <nav className="container-page flex flex-col gap-1 py-3" aria-label="Mobile">
            {PUBLIC_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm font-medium text-ink-soft hover:bg-surface-muted"
              >
                {link.label}
              </Link>
            ))}
            <Link
              href="/scan"
              onClick={() => setMenuOpen(false)}
              className="rounded-lg px-3 py-2.5 text-sm font-medium text-ink-soft hover:bg-surface-muted"
            >
              Scan a campaign QR
            </Link>
            <div className="mt-2 border-t border-surface-border pt-3">
              {user ? (
                <div className="space-y-2">
                  <Link href={dashboardHref(user.role)} onClick={() => setMenuOpen(false)}>
                    <Button variant="outline" className="w-full">
                      Dashboard
                    </Button>
                  </Link>
                  <Button variant="ghost" className="w-full" onClick={handleLogout}>
                    Sign out
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <Link href="/login" onClick={() => setMenuOpen(false)}>
                    <Button variant="outline" className="w-full">
                      Sign in
                    </Button>
                  </Link>
                  <Link href="/register" onClick={() => setMenuOpen(false)}>
                    <Button className="w-full">Get started</Button>
                  </Link>
                </div>
              )}
            </div>
          </nav>
        </div>
      )}

      {process.env.NEXT_PUBLIC_DEMO_MODE === "true" && (
        <div className="border-b border-caution/20 bg-caution-soft">
          <div className="container-page flex items-center gap-2 py-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-caution-strong" aria-hidden />
            <p className="text-xs text-caution-strong">
              <Badge tone="caution" className="mr-2">
                DEMO MODE
              </Badge>
              Simulated KYC, test payments and a local blockchain. No real money or identity data.
            </p>
          </div>
        </div>
      )}
    </header>
  );
}
