import type { Metadata } from "next";
import Link from "next/link";

import { Button, Card, CardContent } from "@/components/ui";

export const metadata: Metadata = {
  title: "About",
  description:
    "CrowdWise treats crowdfunding as a community participation and governance system, not merely a payment system.",
};

const PRINCIPLES = [
  {
    title: "The payment system is the source of truth for money",
    body: "A browser saying a payment succeeded proves nothing. Contributions are counted only after a server-side signature check, and the signed webhook is authoritative even if the browser closed.",
  },
  {
    title: "The blockchain is an audit surface, not a bank",
    body: "There is no payable function in the contract and no path to withdraw funds. It records that something happened — a verified contribution, a vote, an outcome — so the platform's history can be checked by anyone.",
  },
  {
    title: "Personal data never goes on chain",
    body: "Names, emails, phone numbers, identity documents, bank details and raw payment identifiers stay in the database. Only salted hashes, amounts and timestamps are anchored.",
  },
  {
    title: "AI is decision support, never the decider",
    body: "Analysis is scored, validated and shown to a human reviewer with the questions worth asking. If the model is unavailable, a deterministic fallback runs and is labelled as such. A person approves every campaign.",
  },
  {
    title: "The ending is decided in advance, and by contributors",
    body: "What happens if a target is missed is fixed before funding opens and locked at publication. When it is put to a vote, only people who actually funded the campaign can vote, once each.",
  },
  {
    title: "Failures are shown, not hidden",
    body: "A pending blockchain anchor, a payment awaiting webhook confirmation, an AI analysis that fell back to a heuristic — each is surfaced honestly rather than smoothed into a green tick.",
  },
];

export default function AboutPage() {
  return (
    <div className="container-page py-12">
      <header className="max-w-3xl">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">About CrowdWise</h1>
        <p className="mt-4 text-lg leading-relaxed text-ink-muted">
          CrowdWise is an AI-powered community crowdfunding and governance platform. Its premise
          is that crowdfunding should be a community participation and governance system, not
          merely a payment system.
        </p>
      </header>

      <section className="mt-10 max-w-3xl space-y-4 text-ink-soft">
        <p className="leading-relaxed">
          A typical crowdfunding platform asks you to trust three things at once: that the person
          asking is real, that the plan is plausible, and that something sensible will happen if
          the campaign falls short. Usually all three are assumed rather than established.
        </p>
        <p className="leading-relaxed">
          CrowdWise turns each of those assumptions into a step with evidence behind it. Creators
          are verified and pay to apply. Proposals are analysed and then judged by a person.
          Payments are verified on the server before a single rupee is counted. Community
          feedback is measured rather than curated. And when a campaign misses its target, the
          people who funded it decide what happens next — under rules that were fixed before
          they contributed.
        </p>
      </section>

      <section className="mt-12">
        <h2 className="text-xl font-semibold tracking-tight">The principles it is built on</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {PRINCIPLES.map((principle) => (
            <Card key={principle.title}>
              <CardContent className="p-5">
                <h3 className="text-sm font-semibold text-ink">{principle.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-muted">{principle.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-12 max-w-3xl">
        <h2 className="text-xl font-semibold tracking-tight">What CrowdWise deliberately is not</h2>
        <p className="mt-3 leading-relaxed text-ink-muted">
          There is no token, no NFT, no speculative tokenomics and no custom wallet. Rupees are
          never held on chain, and no smart contract function claims to transfer them. The
          governance model is a single, understandable vote rather than a DAO framework. Each of
          those omissions is a choice: they would have added surface area without making the
          lifecycle any more complete.
        </p>
      </section>

      <section className="mt-12 flex flex-wrap gap-3">
        <Link href="/how-it-works">
          <Button size="lg">Read how it works</Button>
        </Link>
        <Link href="/campaigns">
          <Button size="lg" variant="outline">
            Explore campaigns
          </Button>
        </Link>
      </section>
    </div>
  );
}
