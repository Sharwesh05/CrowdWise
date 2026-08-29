import type { Metadata } from "next";
import Link from "next/link";
import { Blocks, Brain, CreditCard, QrCode, ShieldCheck, Vote } from "lucide-react";

import { Alert, Badge, Button, Card, CardContent } from "@/components/ui";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "The CrowdWise lifecycle: verification, AI analysis, human review, QR discovery, verified payments, community intelligence and contributor governance.",
};

const STAGES = [
  {
    id: "verification",
    number: "01",
    icon: ShieldCheck,
    title: "Creator verification",
    body: "A creator registers and completes identity verification. Until that is done, nothing else in the lifecycle can proceed — this is what makes the verified badge on a campaign mean something.",
    detail: [
      "Identity verification is required before submission.",
      "Verification data is stored off-chain and never published.",
      "In demo mode the provider is simulated and accepts test values only.",
    ],
  },
  {
    id: "application",
    number: "02",
    icon: CreditCard,
    title: "Process application fee",
    body: "A small application fee filters out low-effort submissions and funds the review process. The application only advances after the payment is verified on the server.",
    detail: [
      "The backend creates a Razorpay order; the browser completes it.",
      "A client callback is treated as an unverified claim.",
      "Only a valid HMAC signature — or a signed webhook — moves the application forward.",
    ],
  },
  {
    id: "analysis",
    number: "03",
    icon: Brain,
    title: "AI analysis, human decision",
    body: "The proposal is scored for problem clarity, feasibility, potential impact and execution risk. Strengths, concerns, recommendations and the questions a reviewer should ask are extracted. Then a person decides.",
    detail: [
      "Model output is validated against a strict schema before it is stored.",
      "If the model is unavailable, a deterministic fallback runs and is marked as degraded.",
      "AI never approves a campaign. Approval is always an admin action.",
    ],
  },
  {
    id: "qr",
    number: "04",
    icon: QrCode,
    title: "Publication and a unique QR",
    body: "On approval the campaign goes live and receives a unique QR code that resolves to its public page — on a poster, an event stall, a slide, a package or a social post.",
    detail: [
      "The QR encodes a link. It never holds money and carries no personal data.",
      "Physical and online discovery lead to exactly the same campaign page.",
      "The page is built mobile-first, because most scans come from a phone.",
    ],
  },
  {
    id: "funding",
    number: "05",
    icon: ShieldCheck,
    title: "Verified contributions",
    body: "Contributors fund through Razorpay. The amount raised moves only inside the transaction that verifies the payment — never because a browser said it worked.",
    detail: [
      "The signed Razorpay webhook is the source of truth for money.",
      "Duplicate webhook deliveries cannot create a second contribution.",
      "The contribution is then anchored on chain as a separate, retryable step.",
    ],
  },
  {
    id: "trust",
    number: "06",
    icon: Blocks,
    title: "Blockchain verification",
    body: "Contributions, votes and outcomes are anchored in a small Solidity registry so the platform's own history is tamper-evident and publicly checkable.",
    detail: [
      "On chain: campaign reference hash, amount, timestamp, payment reference hash, vote record.",
      "Never on chain: names, emails, phone numbers, KYC data, or raw payment identifiers.",
      "A chain outage never invalidates a verified payment — the anchor simply retries.",
    ],
  },
  {
    id: "community",
    number: "07",
    icon: Brain,
    title: "Community intelligence",
    body: "Contributor feedback is classified for sentiment and theme, aggregated, and then summarised once for the whole community — so creators hear the signal rather than a wall of comments.",
    detail: [
      "Each comment is classified when it is written, never on page load.",
      "Only anonymised aggregates and a small sample reach the language model.",
      "Themes such as funding target, execution plan, team and scalability are tracked separately.",
    ],
  },
  {
    id: "governance",
    number: "08",
    icon: Vote,
    title: "Contributor governance",
    body: "A missed target is not automatically a refund and not automatically a continuation. It is a decision — and the people who funded the campaign make it, under rules fixed before funding opened.",
    detail: [
      "Eligibility: at least one verified contribution to that campaign.",
      "One vote per contributor per round, enforced by a database constraint and by the contract.",
      "Refunds are executed by payment infrastructure. The chain records the decision, not the money.",
    ],
  },
];

export default function HowItWorksPage() {
  return (
    <div className="container-page py-12">
      <header className="max-w-3xl">
        <Badge tone="brand" className="mb-4">
          The CrowdWise lifecycle
        </Badge>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          How CrowdWise works
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-ink-muted">
          Most platforms model crowdfunding as campaign → payment → money raised. CrowdWise
          models it as a governed lifecycle, with a gate at every point where trust is usually
          just assumed.
        </p>
      </header>

      <div className="mt-12 space-y-6">
        {STAGES.map((stage) => (
          <Card key={stage.id} id={stage.id} className="scroll-mt-24">
            <CardContent className="grid gap-6 p-6 md:grid-cols-[auto,1fr]">
              <div className="flex items-start gap-4">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700">
                  <stage.icon className="h-5 w-5" aria-hidden />
                </span>
                <span className="text-2xl font-bold tracking-tight text-brand-200 md:hidden">
                  {stage.number}
                </span>
              </div>

              <div>
                <div className="flex items-baseline gap-3">
                  <span className="hidden text-sm font-bold tracking-tight text-brand-300 md:inline">
                    {stage.number}
                  </span>
                  <h2 className="text-lg font-semibold text-ink">{stage.title}</h2>
                </div>
                <p className="mt-2 leading-relaxed text-ink-muted">{stage.body}</p>
                <ul className="mt-4 space-y-1.5">
                  {stage.detail.map((item, index) => (
                    <li key={index} className="flex gap-2 text-sm text-ink-soft">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <section className="mt-12 max-w-3xl">
        <h2 className="text-xl font-semibold tracking-tight">Where the money actually is</h2>
        <p className="mt-3 leading-relaxed text-ink-muted">
          It is worth being precise, because crowdfunding plus blockchain invites a lot of
          hand-waving. Rupees move through Razorpay and regulated settlement infrastructure —
          full stop. The QR is a link. The blockchain is an audit surface holding hashes,
          amounts and timestamps. CrowdWise&apos;s database is the record of the application.
          Nothing in this product pretends a smart contract is a bank account.
        </p>

        <Alert tone="info" className="mt-5" title="What this means in practice">
          If the blockchain is unreachable, your contribution is still verified and still
          counted — only its anchor is pending, and the interface says so rather than hiding it.
          If a refund is decided, it is processed by the payment provider, not by a Solidity
          function claiming to move rupees.
        </Alert>
      </section>

      <section className="mt-12 flex flex-wrap gap-3">
        <Link href="/campaigns">
          <Button size="lg">Explore campaigns</Button>
        </Link>
        <Link href="/register?role=CREATOR">
          <Button size="lg" variant="outline">
            Start a campaign
          </Button>
        </Link>
      </section>
    </div>
  );
}
