import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CampaignCard } from "@/features/campaign/campaign-card";
import { VerificationSteps } from "@/features/campaign/contribute-dialog";
import { formatCompactCurrency, formatCurrency } from "@/lib/format";
import { parseCampaignReference } from "@/lib/utils";
import type { CampaignSummary, VerificationProgress } from "@/types";

const campaign: CampaignSummary = {
  id: 1,
  public_id: "CMP-101",
  title: "Solar Water Purifier for Rural Schools",
  slug: "solar-water-purifier",
  short_description: "Solar-powered purifiers for 40 rural schools.",
  category: "ENVIRONMENT",
  cover_image_url: null,
  target_amount: "1000000.00",
  raised_amount: "680000.00",
  funding_percentage: 68,
  minimum_contribution: "500.00",
  contributor_count: 342,
  deadline: new Date(Date.now() + 86_400_000 * 20).toISOString(),
  days_remaining: 20,
  status: "LIVE",
  creator: { id: 2, name: "Asha Menon", is_verified: true },
  average_rating: 4.2,
  health_score: 74,
  health_label: "Healthy",
  is_demo: false,
};

describe("CampaignCard", () => {
  it("shows funding, backers and the verified creator badge", () => {
    render(<CampaignCard campaign={campaign} />);

    expect(screen.getByText(campaign.title)).toBeInTheDocument();
    expect(screen.getByText("Asha Menon")).toBeInTheDocument();
    expect(screen.getByText(/verified creator/i)).toBeInTheDocument();
    expect(screen.getByText(/342 backers/i)).toBeInTheDocument();
    expect(screen.getByText(/20d left/i)).toBeInTheDocument();
    expect(screen.getByText(/health 74/i)).toBeInTheDocument();
  });

  it("exposes funding progress to assistive technology", () => {
    render(<CampaignCard campaign={campaign} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "68");
  });

  it("links to the public campaign page", () => {
    render(<CampaignCard campaign={campaign} />);
    const link = screen.getByRole("link", { name: /view campaign/i });
    expect(link).toHaveAttribute("href", "/campaign/CMP-101");
  });
});

describe("VerificationSteps", () => {
  const base: VerificationProgress = {
    payment_received: true,
    payment_verified: true,
    webhook_verified: false,
    contribution_recorded: true,
    blockchain_status: "BLOCKCHAIN_PENDING",
    blockchain_tx: null,
    contribution_id: 5,
    message: "",
  };

  it("shows each real server-side step rather than one success message", () => {
    render(<VerificationSteps progress={base} />);
    expect(screen.getByText(/payment received/i)).toBeInTheDocument();
    expect(screen.getByText(/payment verified on the server/i)).toBeInTheDocument();
    expect(screen.getByText(/contribution recorded/i)).toBeInTheDocument();
    expect(screen.getByText(/blockchain record confirmed/i)).toBeInTheDocument();
  });

  it("reassures the contributor when the chain anchor fails", () => {
    render(<VerificationSteps progress={{ ...base, blockchain_status: "BLOCKCHAIN_FAILED" }} />);
    expect(screen.getByText(/your contribution is safe/i)).toBeInTheDocument();
    expect(screen.getByText(/will be retried automatically/i)).toBeInTheDocument();
  });

  it("marks a webhook-confirmed payment", () => {
    render(<VerificationSteps progress={{ ...base, webhook_verified: true }} />);
    expect(screen.getByText(/confirmed by razorpay webhook/i)).toBeInTheDocument();
  });
});

describe("formatting and QR parsing", () => {
  it("formats rupees in Indian conventions", () => {
    expect(formatCurrency("1000000")).toContain("10,00,000");
    expect(formatCompactCurrency("1000000")).toBe("₹10 L");
    expect(formatCompactCurrency("15000000")).toBe("₹1.5 Cr");
  });

  it("extracts a campaign id from any QR payload shape", () => {
    expect(parseCampaignReference("http://localhost:3000/campaign/CMP-124")).toBe("CMP-124");
    expect(parseCampaignReference("CMP-124")).toBe("CMP-124");
    expect(parseCampaignReference("cmp-124")).toBe("CMP-124");
    expect(parseCampaignReference("  ")).toBeNull();
    expect(parseCampaignReference("not a qr @@")).toBeNull();
  });
});
