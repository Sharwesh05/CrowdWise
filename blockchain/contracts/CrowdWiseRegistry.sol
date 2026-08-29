// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title CrowdWiseRegistry
 * @notice Tamper-evident record of the CrowdWise campaign lifecycle.
 *
 * WHAT THIS CONTRACT IS
 * ---------------------
 * An append-only audit log for the events that matter: a campaign was
 * registered, a verified contribution happened, a governance round opened, a
 * vote was cast, an outcome was selected.
 *
 * WHAT THIS CONTRACT IS NOT
 * -------------------------
 * It is NOT a bank and NOT an escrow. It never holds, transfers, or refunds
 * Indian rupees. There is deliberately no payable function and no withdrawal
 * path anywhere in this file. Fiat movement is handled entirely by regulated
 * payment infrastructure (Razorpay), and the backend records the payment result
 * here only as evidence that it happened.
 *
 * The `amount` fields below are denominated in paise and exist purely as part of
 * the audit record. Writing an amount here moves no value.
 *
 * PRIVACY
 * -------
 * No personal data reaches this contract. The backend passes only:
 *   - campaignRef:    salted hash of the campaign's public id
 *   - paymentRefHash: salted one-way hash of the gateway payment id
 *   - voterRef:       salted, campaign-scoped, opaque voter reference
 * Names, emails, phone numbers, KYC data and raw payment identifiers stay in
 * PostgreSQL and never appear on chain.
 *
 * TRUST MODEL
 * -----------
 * A single recorder (the CrowdWise backend) writes records, because the facts
 * being recorded — that Razorpay verified a payment — are only knowable
 * off-chain. The value delivered is tamper-evidence and public verifiability of
 * the platform's own history, not trustless settlement. The recorder can be
 * rotated by the owner, and every write emits an event.
 */
contract CrowdWiseRegistry {
    // ---------------------------------------------------------------------
    // Types
    // ---------------------------------------------------------------------
    enum VoteChoice {
        NONE,
        REFUND,
        CONTINUE
    }

    struct Campaign {
        bytes32 ref;
        uint256 targetAmount; // paise, audit record only
        uint256 totalRecorded; // paise, sum of recorded contributions
        uint64 registeredAt;
        uint64 votingClosesAt;
        uint32 contributionCount;
        uint32 voteCount;
        bool exists;
        bool votingOpen;
        bool votingClosed;
        VoteChoice outcome;
    }

    struct Contribution {
        bytes32 paymentRefHash;
        uint256 amount; // paise, audit record only
        address contributor; // zero address when the contributor has no wallet
        uint64 recordedAt;
    }

    struct Vote {
        VoteChoice choice;
        uint256 weight;
        uint64 castAt;
        bool exists;
    }

    // ---------------------------------------------------------------------
    // Storage
    // ---------------------------------------------------------------------
    address public owner;
    address public recorder;

    mapping(bytes32 => Campaign) private campaigns;
    mapping(bytes32 => Contribution[]) private contributions;
    /// @dev campaignRef => paymentRefHash => recorded. Makes a replayed
    ///      contribution write a no-op rather than a duplicate record.
    mapping(bytes32 => mapping(bytes32 => bool)) private contributionSeen;
    /// @dev campaignRef => voterRef => vote. One vote per voter per campaign,
    ///      enforced by the contract itself and not only by the backend.
    mapping(bytes32 => mapping(bytes32 => Vote)) private votes;
    mapping(bytes32 => bytes32[]) private voterList;

    // ---------------------------------------------------------------------
    // Events
    // ---------------------------------------------------------------------
    event CampaignRegistered(bytes32 indexed campaignRef, uint256 targetAmount, uint64 at);
    event ContributionRecorded(
        bytes32 indexed campaignRef,
        bytes32 indexed paymentRefHash,
        uint256 amount,
        address contributor,
        uint256 index,
        uint64 at
    );
    event VotingOpened(bytes32 indexed campaignRef, uint64 closesAt);
    event VoteRecorded(
        bytes32 indexed campaignRef,
        bytes32 indexed voterRef,
        VoteChoice choice,
        uint256 weight,
        uint64 at
    );
    event VotingClosed(bytes32 indexed campaignRef, uint32 voteCount, uint64 at);
    event OutcomeRecorded(bytes32 indexed campaignRef, VoteChoice outcome, uint64 at);
    event RecorderChanged(address indexed previousRecorder, address indexed newRecorder);

    // ---------------------------------------------------------------------
    // Errors
    // ---------------------------------------------------------------------
    error NotOwner();
    error NotRecorder();
    error CampaignExists();
    error CampaignUnknown();
    error VotingNotOpen();
    error VotingAlreadyOpen();
    error VotingHasClosed();
    error AlreadyVoted();
    error InvalidChoice();
    error InvalidReference();
    error ZeroAddress();

    // ---------------------------------------------------------------------
    // Access control
    // ---------------------------------------------------------------------
    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyRecorder() {
        if (msg.sender != recorder && msg.sender != owner) revert NotRecorder();
        _;
    }

    constructor(address initialRecorder) {
        owner = msg.sender;
        recorder = initialRecorder == address(0) ? msg.sender : initialRecorder;
    }

    function setRecorder(address newRecorder) external onlyOwner {
        if (newRecorder == address(0)) revert ZeroAddress();
        emit RecorderChanged(recorder, newRecorder);
        recorder = newRecorder;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        owner = newOwner;
    }

    // ---------------------------------------------------------------------
    // Campaign lifecycle
    // ---------------------------------------------------------------------
    function registerCampaign(bytes32 campaignRef, uint256 targetAmount) external onlyRecorder {
        if (campaignRef == bytes32(0)) revert InvalidReference();
        if (campaigns[campaignRef].exists) revert CampaignExists();

        campaigns[campaignRef] = Campaign({
            ref: campaignRef,
            targetAmount: targetAmount,
            totalRecorded: 0,
            registeredAt: uint64(block.timestamp),
            votingClosesAt: 0,
            contributionCount: 0,
            voteCount: 0,
            exists: true,
            votingOpen: false,
            votingClosed: false,
            outcome: VoteChoice.NONE
        });

        emit CampaignRegistered(campaignRef, targetAmount, uint64(block.timestamp));
    }

    /**
     * @notice Record a contribution whose payment was already verified off-chain.
     * @dev Idempotent by paymentRefHash: a redelivered webhook that reaches this
     *      function twice records once and returns the existing index.
     */
    function recordContribution(
        bytes32 campaignRef,
        bytes32 paymentRefHash,
        uint256 amount,
        address contributor
    ) external onlyRecorder returns (uint256 index) {
        Campaign storage campaign = campaigns[campaignRef];
        if (!campaign.exists) revert CampaignUnknown();
        if (paymentRefHash == bytes32(0)) revert InvalidReference();

        if (contributionSeen[campaignRef][paymentRefHash]) {
            return contributions[campaignRef].length;
        }
        contributionSeen[campaignRef][paymentRefHash] = true;

        contributions[campaignRef].push(
            Contribution({
                paymentRefHash: paymentRefHash,
                amount: amount,
                contributor: contributor,
                recordedAt: uint64(block.timestamp)
            })
        );
        index = contributions[campaignRef].length - 1;

        campaign.totalRecorded += amount;
        campaign.contributionCount += 1;

        emit ContributionRecorded(
            campaignRef, paymentRefHash, amount, contributor, index, uint64(block.timestamp)
        );
    }

    // ---------------------------------------------------------------------
    // Governance
    // ---------------------------------------------------------------------
    function openVoting(bytes32 campaignRef, uint64 closesAt) external onlyRecorder {
        Campaign storage campaign = campaigns[campaignRef];
        if (!campaign.exists) revert CampaignUnknown();
        if (campaign.votingOpen) revert VotingAlreadyOpen();
        if (campaign.votingClosed) revert VotingHasClosed();

        campaign.votingOpen = true;
        campaign.votingClosesAt = closesAt;
        emit VotingOpened(campaignRef, closesAt);
    }

    /**
     * @notice Record one vote by one eligible voter.
     * @dev Eligibility is established off-chain (a verified contribution);
     *      uniqueness is enforced here, so the chain cannot be made to hold two
     *      votes from the same voter reference even if the backend tried.
     */
    function recordVote(
        bytes32 campaignRef,
        bytes32 voterRef,
        uint8 choice,
        uint256 weight
    ) external onlyRecorder {
        Campaign storage campaign = campaigns[campaignRef];
        if (!campaign.exists) revert CampaignUnknown();
        if (!campaign.votingOpen) revert VotingNotOpen();
        if (campaign.votingClosed) revert VotingHasClosed();
        if (campaign.votingClosesAt != 0 && block.timestamp > campaign.votingClosesAt) {
            revert VotingHasClosed();
        }
        if (voterRef == bytes32(0)) revert InvalidReference();
        if (choice != uint8(VoteChoice.REFUND) && choice != uint8(VoteChoice.CONTINUE)) {
            revert InvalidChoice();
        }
        if (votes[campaignRef][voterRef].exists) revert AlreadyVoted();

        votes[campaignRef][voterRef] = Vote({
            choice: VoteChoice(choice),
            weight: weight,
            castAt: uint64(block.timestamp),
            exists: true
        });
        voterList[campaignRef].push(voterRef);
        campaign.voteCount += 1;

        emit VoteRecorded(campaignRef, voterRef, VoteChoice(choice), weight, uint64(block.timestamp));
    }

    function closeVoting(bytes32 campaignRef) external onlyRecorder {
        Campaign storage campaign = campaigns[campaignRef];
        if (!campaign.exists) revert CampaignUnknown();
        if (!campaign.votingOpen) revert VotingNotOpen();

        campaign.votingOpen = false;
        campaign.votingClosed = true;
        emit VotingClosed(campaignRef, campaign.voteCount, uint64(block.timestamp));
    }

    /**
     * @notice Record the selected outcome.
     * @dev Recording REFUND does not move any money — it is the decision that is
     *      being anchored. The refund itself is executed by payment infrastructure.
     */
    function recordOutcome(bytes32 campaignRef, uint8 outcome) external onlyRecorder {
        Campaign storage campaign = campaigns[campaignRef];
        if (!campaign.exists) revert CampaignUnknown();
        if (outcome != uint8(VoteChoice.REFUND) && outcome != uint8(VoteChoice.CONTINUE)) {
            revert InvalidChoice();
        }

        campaign.outcome = VoteChoice(outcome);
        emit OutcomeRecorded(campaignRef, VoteChoice(outcome), uint64(block.timestamp));
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------
    function getCampaign(bytes32 campaignRef)
        external
        view
        returns (
            uint256 targetAmount,
            uint256 totalRecorded,
            uint32 contributionCount,
            uint32 voteCount,
            uint64 registeredAt,
            bool votingOpen,
            bool votingClosed,
            VoteChoice outcome
        )
    {
        Campaign storage campaign = campaigns[campaignRef];
        if (!campaign.exists) revert CampaignUnknown();
        return (
            campaign.targetAmount,
            campaign.totalRecorded,
            campaign.contributionCount,
            campaign.voteCount,
            campaign.registeredAt,
            campaign.votingOpen,
            campaign.votingClosed,
            campaign.outcome
        );
    }

    function getContribution(bytes32 campaignRef, uint256 index)
        external
        view
        returns (bytes32 paymentRefHash, uint256 amount, address contributor, uint64 recordedAt)
    {
        Contribution storage entry = contributions[campaignRef][index];
        return (entry.paymentRefHash, entry.amount, entry.contributor, entry.recordedAt);
    }

    function getContributionCount(bytes32 campaignRef) external view returns (uint256) {
        return contributions[campaignRef].length;
    }

    function getVote(bytes32 campaignRef, bytes32 voterRef)
        external
        view
        returns (VoteChoice choice, uint256 weight, uint64 castAt, bool exists)
    {
        Vote storage vote = votes[campaignRef][voterRef];
        return (vote.choice, vote.weight, vote.castAt, vote.exists);
    }

    function getVoterCount(bytes32 campaignRef) external view returns (uint256) {
        return voterList[campaignRef].length;
    }

    /// @notice Tally the recorded votes. Read-only: it decides nothing by itself.
    function tally(bytes32 campaignRef)
        external
        view
        returns (uint256 refundVotes, uint256 continueVotes, uint256 refundWeight, uint256 continueWeight)
    {
        bytes32[] storage voters = voterList[campaignRef];
        for (uint256 i = 0; i < voters.length; i++) {
            Vote storage vote = votes[campaignRef][voters[i]];
            if (vote.choice == VoteChoice.REFUND) {
                refundVotes += 1;
                refundWeight += vote.weight;
            } else if (vote.choice == VoteChoice.CONTINUE) {
                continueVotes += 1;
                continueWeight += vote.weight;
            }
        }
    }

    function isContributionRecorded(bytes32 campaignRef, bytes32 paymentRefHash)
        external
        view
        returns (bool)
    {
        return contributionSeen[campaignRef][paymentRefHash];
    }
}
