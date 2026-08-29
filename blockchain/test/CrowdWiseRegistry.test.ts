import { expect } from "chai";
import { ethers } from "hardhat";
import { CrowdWiseRegistry } from "../typechain-types";
import { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";

const ref = (value: string) => ethers.keccak256(ethers.toUtf8Bytes(value));

const CAMPAIGN = ref("campaign:CMP-124");
const PAYMENT_A = ref("payment:pay_test_aaa");
const PAYMENT_B = ref("payment:pay_test_bbb");
const VOTER_A = ref("voter:CMP-124:1");
const VOTER_B = ref("voter:CMP-124:2");

const REFUND = 1;
const CONTINUE = 2;
const TARGET = 100_000_000n; // ₹10,00,000 in paise — an audit value, not money

describe("CrowdWiseRegistry", () => {
  let registry: CrowdWiseRegistry;
  let owner: HardhatEthersSigner;
  let recorder: HardhatEthersSigner;
  let outsider: HardhatEthersSigner;

  beforeEach(async () => {
    [owner, recorder, outsider] = await ethers.getSigners();
    const factory = await ethers.getContractFactory("CrowdWiseRegistry");
    registry = (await factory.deploy(recorder.address)) as CrowdWiseRegistry;
    await registry.waitForDeployment();
  });

  describe("deployment", () => {
    it("sets the owner and the recorder", async () => {
      expect(await registry.owner()).to.equal(owner.address);
      expect(await registry.recorder()).to.equal(recorder.address);
    });

    it("holds no funds and exposes no payable entry point", async () => {
      // The contract records money; it never receives it.
      const abi = registry.interface.fragments.filter(
        (fragment: any) => fragment.type === "function",
      );
      const payable = abi.filter((fn: any) => fn.payable || fn.stateMutability === "payable");
      expect(payable.length).to.equal(0);
      expect(await ethers.provider.getBalance(await registry.getAddress())).to.equal(0n);
    });
  });

  describe("campaign registration", () => {
    it("registers a campaign and emits the event", async () => {
      await expect(registry.connect(recorder).registerCampaign(CAMPAIGN, TARGET))
        .to.emit(registry, "CampaignRegistered")
        .withArgs(CAMPAIGN, TARGET, (value: bigint) => value > 0n);

      const campaign = await registry.getCampaign(CAMPAIGN);
      expect(campaign.targetAmount).to.equal(TARGET);
      expect(campaign.contributionCount).to.equal(0);
    });

    it("rejects a duplicate registration", async () => {
      await registry.connect(recorder).registerCampaign(CAMPAIGN, TARGET);
      await expect(
        registry.connect(recorder).registerCampaign(CAMPAIGN, TARGET),
      ).to.be.revertedWithCustomError(registry, "CampaignExists");
    });

    it("rejects an empty reference", async () => {
      await expect(
        registry.connect(recorder).registerCampaign(ethers.ZeroHash, TARGET),
      ).to.be.revertedWithCustomError(registry, "InvalidReference");
    });

    it("rejects a write from an unauthorised account", async () => {
      await expect(
        registry.connect(outsider).registerCampaign(CAMPAIGN, TARGET),
      ).to.be.revertedWithCustomError(registry, "NotRecorder");
    });
  });

  describe("contribution recording", () => {
    beforeEach(async () => {
      await registry.connect(recorder).registerCampaign(CAMPAIGN, TARGET);
    });

    it("records a contribution and accumulates the total", async () => {
      await expect(
        registry.connect(recorder).recordContribution(CAMPAIGN, PAYMENT_A, 50_000n, outsider.address),
      ).to.emit(registry, "ContributionRecorded");

      const campaign = await registry.getCampaign(CAMPAIGN);
      expect(campaign.contributionCount).to.equal(1);
      expect(campaign.totalRecorded).to.equal(50_000n);

      const contribution = await registry.getContribution(CAMPAIGN, 0);
      expect(contribution.paymentRefHash).to.equal(PAYMENT_A);
      expect(contribution.amount).to.equal(50_000n);
    });

    it("is idempotent for a replayed payment reference", async () => {
      // A redelivered webhook must not become a second on-chain record.
      await registry.connect(recorder).recordContribution(CAMPAIGN, PAYMENT_A, 50_000n, outsider.address);
      await registry.connect(recorder).recordContribution(CAMPAIGN, PAYMENT_A, 50_000n, outsider.address);

      const campaign = await registry.getCampaign(CAMPAIGN);
      expect(campaign.contributionCount).to.equal(1);
      expect(campaign.totalRecorded).to.equal(50_000n);
      expect(await registry.getContributionCount(CAMPAIGN)).to.equal(1n);
    });

    it("accepts the zero address for a contributor without a wallet", async () => {
      await registry.connect(recorder).recordContribution(CAMPAIGN, PAYMENT_A, 50_000n, ethers.ZeroAddress);
      const contribution = await registry.getContribution(CAMPAIGN, 0);
      expect(contribution.contributor).to.equal(ethers.ZeroAddress);
    });

    it("rejects a contribution to an unknown campaign", async () => {
      await expect(
        registry.connect(recorder).recordContribution(ref("campaign:nope"), PAYMENT_A, 1n, outsider.address),
      ).to.be.revertedWithCustomError(registry, "CampaignUnknown");
    });
  });

  describe("governance", () => {
    beforeEach(async () => {
      await registry.connect(recorder).registerCampaign(CAMPAIGN, TARGET);
      await registry.connect(recorder).recordContribution(CAMPAIGN, PAYMENT_A, 50_000n, outsider.address);
      await registry.connect(recorder).recordContribution(CAMPAIGN, PAYMENT_B, 50_000n, outsider.address);
    });

    // Returns the transaction so callers can assert on emitted events.
    const openVoting = async (offsetSeconds = 3600) => {
      const now = (await ethers.provider.getBlock("latest"))!.timestamp;
      return registry.connect(recorder).openVoting(CAMPAIGN, now + offsetSeconds);
    };

    it("opens voting with a closing time", async () => {
      await expect(openVoting()).to.emit(registry, "VotingOpened");
      const campaign = await registry.getCampaign(CAMPAIGN);
      expect(campaign.votingOpen).to.equal(true);
    });

    it("rejects a vote before voting opens", async () => {
      await expect(
        registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, REFUND, 1n),
      ).to.be.revertedWithCustomError(registry, "VotingNotOpen");
    });

    it("records a vote", async () => {
      await openVoting();
      await expect(registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, REFUND, 1n))
        .to.emit(registry, "VoteRecorded")
        .withArgs(CAMPAIGN, VOTER_A, REFUND, 1n, (value: bigint) => value > 0n);

      const vote = await registry.getVote(CAMPAIGN, VOTER_A);
      expect(vote.exists).to.equal(true);
      expect(vote.choice).to.equal(REFUND);
    });

    it("prevents the same voter voting twice", async () => {
      await openVoting();
      await registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, REFUND, 1n);
      await expect(
        registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, CONTINUE, 1n),
      ).to.be.revertedWithCustomError(registry, "AlreadyVoted");

      const campaign = await registry.getCampaign(CAMPAIGN);
      expect(campaign.voteCount).to.equal(1);
    });

    it("rejects an out-of-range choice", async () => {
      await openVoting();
      await expect(
        registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, 7, 1n),
      ).to.be.revertedWithCustomError(registry, "InvalidChoice");
    });

    it("rejects a vote after the closing time", async () => {
      await openVoting(60);
      await ethers.provider.send("evm_increaseTime", [120]);
      await ethers.provider.send("evm_mine", []);
      await expect(
        registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, REFUND, 1n),
      ).to.be.revertedWithCustomError(registry, "VotingHasClosed");
    });

    it("rejects a vote after voting is closed", async () => {
      await openVoting();
      await registry.connect(recorder).closeVoting(CAMPAIGN);
      await expect(
        registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, REFUND, 1n),
      ).to.be.revertedWithCustomError(registry, "VotingNotOpen");
    });

    it("tallies votes and weights", async () => {
      await openVoting();
      await registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, REFUND, 500n);
      await registry.connect(recorder).recordVote(CAMPAIGN, VOTER_B, CONTINUE, 1500n);

      const result = await registry.tally(CAMPAIGN);
      expect(result.refundVotes).to.equal(1n);
      expect(result.continueVotes).to.equal(1n);
      expect(result.refundWeight).to.equal(500n);
      expect(result.continueWeight).to.equal(1500n);
    });

    it("closes voting and records the outcome", async () => {
      await openVoting();
      await registry.connect(recorder).recordVote(CAMPAIGN, VOTER_A, REFUND, 1n);
      await expect(registry.connect(recorder).closeVoting(CAMPAIGN)).to.emit(registry, "VotingClosed");
      await expect(registry.connect(recorder).recordOutcome(CAMPAIGN, REFUND))
        .to.emit(registry, "OutcomeRecorded")
        .withArgs(CAMPAIGN, REFUND, (value: bigint) => value > 0n);

      const campaign = await registry.getCampaign(CAMPAIGN);
      expect(campaign.votingClosed).to.equal(true);
      expect(campaign.outcome).to.equal(REFUND);
    });

    it("does not let an outsider record a vote", async () => {
      await openVoting();
      await expect(
        registry.connect(outsider).recordVote(CAMPAIGN, VOTER_A, REFUND, 1n),
      ).to.be.revertedWithCustomError(registry, "NotRecorder");
    });
  });

  describe("recorder rotation", () => {
    it("lets the owner rotate the recorder", async () => {
      await expect(registry.connect(owner).setRecorder(outsider.address)).to.emit(
        registry,
        "RecorderChanged",
      );
      expect(await registry.recorder()).to.equal(outsider.address);
      await registry.connect(outsider).registerCampaign(CAMPAIGN, TARGET);
    });

    it("does not let a non-owner rotate the recorder", async () => {
      await expect(
        registry.connect(outsider).setRecorder(outsider.address),
      ).to.be.revertedWithCustomError(registry, "NotOwner");
    });
  });
});
