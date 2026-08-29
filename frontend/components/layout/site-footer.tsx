import Link from "next/link";

const COLUMNS = [
  {
    title: "Platform",
    links: [
      { href: "/campaigns", label: "Explore campaigns" },
      { href: "/how-it-works", label: "How it works" },
      { href: "/scan", label: "Scan a QR" },
      { href: "/register", label: "Start a campaign" },
    ],
  },
  {
    title: "Company",
    links: [
      { href: "/about", label: "About CrowdWise" },
      { href: "/how-it-works#governance", label: "Governance model" },
      { href: "/how-it-works#trust", label: "Trust and verification" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="no-print border-t border-surface-border bg-surface">
      <div className="container-page py-12">
        <div className="grid gap-10 md:grid-cols-4">
          <div className="md:col-span-2">
            <div className="flex items-center gap-2.5">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink text-sm font-bold text-white">
                CW
              </span>
              <span className="text-base font-semibold tracking-tight text-ink">CrowdWise</span>
            </div>
            <p className="mt-3 max-w-sm text-sm text-ink-muted">
              Smarter Crowdfunding. Stronger Communities. Verified creators, AI-assisted
              evaluation, verified payments, and contributors who decide what happens next.
            </p>
          </div>

          {COLUMNS.map((column) => (
            <div key={column.title}>
              <h4 className="text-sm font-semibold text-ink">{column.title}</h4>
              <ul className="mt-3 space-y-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="text-sm text-ink-muted transition-colors hover:text-ink">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 space-y-3 border-t border-surface-border pt-6">
          <p className="text-xs leading-relaxed text-ink-faint">
            AI analysis on CrowdWise is decision support and is not a guarantee of campaign
            success or legitimacy. Payments are processed by Razorpay; the blockchain records
            selected events for verifiability and never holds funds. Identity verification data
            is stored off-chain and is never published.
          </p>
          <p className="text-xs text-ink-faint">
            © {new Date().getFullYear()} CrowdWise. Built as a hackathon MVP.
          </p>
        </div>
      </div>
    </footer>
  );
}
