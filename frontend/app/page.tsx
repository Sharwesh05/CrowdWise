import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  Blocks,
  Brain,
  MessagesSquare,
  QrCode,
  ShieldCheck,
  Vote,
} from "lucide-react";

import { Badge, Button } from "@/components/ui";
import { HomeStats } from "@/features/campaign/home-stats";
import { FeaturedCampaigns } from "@/features/campaign/featured-campaigns";

const PILLARS = [
  {
    icon: BadgeCheck,
    title: "Verified creators",
    body: "Every creator completes identity verification and pays a ₹500 application fee before a campaign can be reviewed. No anonymous asks.",
  },
  {
    icon: Brain,
    title: "AI campaign insights",
    body: "Each proposal is analysed for problem clarity, feasibility, impact and execution risk — then a human reviewer decides.",
  },
  {
    icon: MessagesSquare,
    title: "Community intelligence",
    body: "Contributor feedback is classified for sentiment and theme, then summarised so creators hear what the community actually thinks.",
  },
  {
    icon: ShieldCheck,
    title: "Verified payments",
    body: "Contributions count only after the payment is verified server-side. A browser saying \"success\" is never enough.",
  },
  {
    icon: Blocks,
    title: "Blockchain verification",
    body: "Contributions, votes and outcomes are anchored on-chain for tamper-evidence. No personal data ever goes on the chain.",
  },
  {
    icon: Vote,
    title: "Contributor governance",
    body: "If a campaign misses its target, the people who funded it vote on what happens next — refund or continue.",
  },
];

const STEPS = [
  {
    step: "01",
    title: "Creators get verified",
    body: "Identity verification, a ₹500 application fee, and a written proposal — problem, solution, budget and impact.",
  },
  {
    step: "02",
    title: "AI analyses, a human approves",
    body: "Feasibility, clarity, impact and risk are scored and surfaced to a reviewer. Approval is always a person's decision.",
  },
  {
    step: "03",
    title: "The campaign gets a QR",
    body: "Every approved campaign gets a unique QR that works on a poster, a slide, a stall or a social post.",
  },
  {
    step: "04",
    title: "Contributors fund and speak",
    body: "Payments are verified server-side, anchored on chain, and contributors rate and comment on what they backed.",
  },
  {
    step: "05",
    title: "The community decides the ending",
    body: "Target met, or target missed and put to a contributor vote under rules fixed before funding opened.",
  },
];

export default function HomePage() {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-surface-border bg-surface">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage:
              "linear-gradient(#0F172A 1px, transparent 1px), linear-gradient(90deg, #0F172A 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
          aria-hidden
        />
        <div className="container-page relative py-16 md:py-24">
          <div className="max-w-3xl">
            <Badge tone="brand" dot className="mb-5">
              AI-powered community crowdfunding
            </Badge>
            <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight text-ink sm:text-5xl lg:text-6xl">
              Smarter Crowdfunding.
              <br />
              <span className="text-brand-700">Stronger Communities.</span>
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-muted">
              Discover, evaluate, fund, and participate in campaigns through an AI-powered
              community crowdfunding platform. Creators are verified and evaluated, payments are
              verified server-side, and contributors decide what happens when a target is missed.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/campaigns">
                <Button size="lg">
                  Explore campaigns
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Button>
              </Link>
              <Link href="/register?role=CREATOR">
                <Button size="lg" variant="outline">
                  Start a campaign
                </Button>
              </Link>
              <Link href="/scan">
                <Button size="lg" variant="ghost" leadingIcon={<QrCode className="h-4 w-4" />}>
                  Scan a QR
                </Button>
              </Link>
            </div>
          </div>

          <HomeStats />
        </div>
      </section>

      {/* Featured campaigns */}
      <section className="border-b border-surface-border py-16">
        <div className="container-page">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Campaigns raising now</h2>
              <p className="mt-1.5 text-sm text-ink-muted">
                Every campaign here passed identity verification, AI analysis and human review.
              </p>
            </div>
            <Link href="/campaigns" className="text-sm font-medium text-brand-700 hover:underline">
              View all campaigns →
            </Link>
          </div>
          <FeaturedCampaigns />
        </div>
      </section>

      {/* How it works */}
      <section className="border-b border-surface-border bg-surface py-16">
        <div className="container-page">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-semibold tracking-tight">How CrowdWise works</h2>
            <p className="mt-2 text-ink-muted">
              Crowdfunding is not a payment. It is a lifecycle with gates, evidence and a say for
              the people who paid.
            </p>
          </div>

          <ol className="mt-10 grid gap-6 md:grid-cols-5">
            {STEPS.map((item) => (
              <li key={item.step} className="relative">
                <span className="text-2xl font-bold tracking-tight text-brand-200">{item.step}</span>
                <h3 className="mt-2 text-sm font-semibold text-ink">{item.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{item.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Pillars */}
      <section className="py-16">
        <div className="container-page">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-semibold tracking-tight">
              What makes a CrowdWise campaign different
            </h2>
            <p className="mt-2 text-ink-muted">
              Six guarantees, each backed by something the platform actually enforces.
            </p>
          </div>

          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {PILLARS.map((pillar) => (
              <div key={pillar.title} className="card p-5">
                <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand-50 text-brand-700">
                  <pillar.icon className="h-5 w-5" aria-hidden />
                </span>
                <h3 className="mt-4 text-sm font-semibold text-ink">{pillar.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{pillar.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-surface-border bg-ink py-16 text-white">
        <div className="container-page">
          <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
            <div className="max-w-xl">
              <h2 className="text-2xl font-semibold tracking-tight text-white">
                Have something your community needs?
              </h2>
              <p className="mt-2 text-white/70">
                Get verified, submit your proposal, and let the community evaluate it — with AI
                analysis and a human reviewer standing between an idea and a public campaign.
              </p>
            </div>
            <div className="flex gap-3">
              <Link href="/register?role=CREATOR">
                <Button size="lg" className="bg-white text-ink hover:bg-white/90">
                  Start a campaign
                </Button>
              </Link>
              <Link href="/how-it-works">
                <Button
                  size="lg"
                  variant="outline"
                  className="border-white/20 bg-transparent text-white hover:bg-white/10"
                >
                  Read the model
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
