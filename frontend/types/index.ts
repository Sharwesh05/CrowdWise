/** Shared API types. Mirrors the backend's Pydantic response schemas. */

export type UserRole = "CREATOR" | "CONTRIBUTOR" | "ADMIN";

export type KYCStatus =
  | "NOT_STARTED"
  | "SUBMITTED"
  | "PROCESSING"
  | "VERIFIED"
  | "REJECTED";

export type CampaignStatus =
  | "DRAFT"
  | "KYC_PENDING"
  | "FEE_PENDING"
  | "ANALYSIS_PENDING"
  | "UNDER_REVIEW"
  | "APPROVED"
  | "LIVE"
  | "COMPLETED"
  | "TARGET_MET"
  | "TARGET_MISSED"
  | "GOVERNANCE"
  | "REFUND_PENDING"
  | "CONTINUED"
  | "CLOSED"
  | "REJECTED";

export type ContributionStatus =
  | "PAYMENT_VERIFIED"
  | "BLOCKCHAIN_PENDING"
  | "BLOCKCHAIN_RECORDED"
  | "BLOCKCHAIN_FAILED"
  | "REFUND_PENDING"
  | "REFUNDED";

export type Sentiment = "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "PENDING" | "FAILED";
export type VoteChoice = "REFUND" | "CONTINUE";

export interface SessionUser {
  id: number;
  name: string;
  email: string;
  phone: string | null;
  role: UserRole;
  wallet_address: string | null;
  is_active: boolean;
  created_at: string;
  kyc_status: KYCStatus;
  is_kyc_verified: boolean;
}

export interface AuthResponse {
  user: SessionUser;
  csrf_token: string;
  message: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreatorSummary {
  id: number;
  name: string;
  is_verified: boolean;
}

export interface CampaignSummary {
  id: number;
  public_id: string;
  title: string;
  slug: string;
  short_description: string;
  category: string;
  cover_image_url: string | null;
  target_amount: string;
  raised_amount: string;
  funding_percentage: number;
  minimum_contribution: string;
  contributor_count: number;
  deadline: string;
  days_remaining: number;
  status: CampaignStatus;
  creator: CreatorSummary;
  average_rating: number | null;
  health_score: number | null;
  health_label: string | null;
  is_demo: boolean;
}

export interface AIAnalysis {
  id: number;
  campaign_id: number;
  type: string;
  model: string;
  provider: string;
  status: string;
  feasibility_score: number | null;
  problem_clarity_score: number | null;
  impact_score: number | null;
  risk_score: number | null;
  risk_level: string | null;
  summary: string | null;
  strengths: string[];
  concerns: string[];
  recommendations: string[];
  questions_for_creator: string[];
  missing_information: string[];
  created_at: string;
  disclaimer: string;
}

export interface CommunityInsight {
  id: number;
  campaign_id: number;
  positive_percentage: number;
  neutral_percentage: number;
  negative_percentage: number;
  average_rating: number | null;
  feedback_count: number;
  top_concerns: string[];
  positive_themes: string[];
  aspect_distribution: Record<string, number>;
  community_summary: string | null;
  recommendations: string[];
  questions_from_community: string[];
  risk_change: string | null;
  model: string;
  provider: string;
  status: string;
  created_at: string;
  disclaimer: string;
}

export interface SentimentSummary {
  feedback_count: number;
  analyzed_count: number;
  average_rating: number;
  positive_percentage: number;
  neutral_percentage: number;
  negative_percentage: number;
  aspect_distribution: { aspect: string; percentage: number }[];
  rating_distribution: Record<string, number>;
}

export interface CampaignHealth {
  score: number;
  label: string;
  financial_score: number;
  community_score: number;
  ai_score: number;
  signals: Record<string, unknown>;
  note: string;
}

export interface BlockchainSummary {
  recorded: number;
  pending: number;
  network: string | null;
  contract_address: string | null;
  latest_tx_hash: string | null;
  explorer_url: string | null;
  simulated: boolean;
}

export interface BlockchainRecord {
  id: number;
  record_type: string;
  tx_hash: string;
  network: string;
  contract_address: string | null;
  status: string;
  block_number: number | null;
  gas_used: number | null;
  created_at: string;
  explorer_url: string | null;
  simulated: boolean;
}

export interface OutcomeRules {
  outcome_type: string;
  voting_weight_mode: string;
  options: VoteChoice[];
  eligibility: string;
  locked_at: string | null;
  selected_outcome: string | null;
  note: string;
}

export interface PublicCampaign extends CampaignSummary {
  description: string;
  problem_statement: string;
  proposed_solution: string;
  expected_impact: string | null;
  published_at: string | null;
  governance_status: string;
  governance_closes_at: string | null;
  qr_url: string;
  outcome_rules: OutcomeRules | null;
  analysis: AIAnalysis | null;
  sentiment: SentimentSummary | null;
  update_count: number;
  insights: CommunityInsight | null;
  health: CampaignHealth | null;
  blockchain: BlockchainSummary | null;
}

export interface CampaignEvent {
  id: number;
  event_type: string;
  actor_id: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface CampaignApplication {
  id: number;
  campaign_id: number;
  application_fee: string;
  status: string;
  razorpay_order_id: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
}

export interface CreatorCampaign extends PublicCampaign {
  approval_status: string;
  review_notes: string | null;
  application: CampaignApplication | null;
  qr_token: string | null;
  events: CampaignEvent[];
  allowed_transitions: string[];
  /** Whether the proposal can still be corrected. Decided by the backend. */
  editable: boolean;
}

/**
 * Who may open a supporting document.
 *
 * Both tiers are read by the AI analyst — the tier decides which *humans* may
 * open the file, not whether the model may.
 */
export type DocumentVisibility = "SHARED" | "AI_ONLY";

export interface CampaignDocument {
  id: number;
  file_name: string;
  mime_type: string;
  size: number;
  created_at: string;
  visibility: DocumentVisibility;
  /** Whether the AI could actually read this file. */
  is_machine_readable: boolean;
  /** Why it could not be read, or a note about truncation. */
  extraction_note: string | null;
  /** Authenticated download route — never a raw storage key. */
  url: string | null;
}

export interface SharedDocuments {
  total: number;
  ai_only_count: number;
  requires_sign_in: boolean;
  documents: CampaignDocument[];
}

export interface OrderResponse {
  payment_id: number;
  order_id: string;
  amount: string;
  amount_paise: number;
  currency: string;
  key_id: string;
  provider: string;
  payment_type: string;
  campaign_public_id: string | null;
  demo_mode: boolean;
  notice: string | null;
}

export interface VerificationProgress {
  payment_received: boolean;
  payment_verified: boolean;
  webhook_verified: boolean;
  contribution_recorded: boolean;
  blockchain_status: string;
  blockchain_tx: string | null;
  contribution_id: number | null;
  message: string;
}

export interface PaymentRecord {
  id: number;
  payment_type: string;
  razorpay_order_id: string;
  razorpay_payment_id: string | null;
  amount: string;
  currency: string;
  status: string;
  webhook_verified: boolean;
  provider: string;
  created_at: string;
  verified_at: string | null;
}

export interface Contribution {
  id: number;
  campaign_id: number;
  campaign_public_id: string | null;
  campaign_title: string | null;
  amount: string;
  status: ContributionStatus;
  blockchain_tx: string | null;
  blockchain_attempts: number;
  created_at: string;
  payment: PaymentRecord | null;
  blockchain_record: BlockchainRecord | null;
}

export interface ProfileChainRecord extends BlockchainRecord {
  campaign_public_id: string | null;
  campaign_title: string | null;
}

export interface Profile {
  user: {
    id: number;
    name: string;
    email: string;
    phone: string | null;
    role: UserRole;
    wallet_address: string | null;
    is_active: boolean;
    created_at: string | null;
    kyc_status: string | null;
    kyc_verified_at: string | null;
  };
  stats: {
    total_contributed: string;
    contributions: number;
    campaigns_supported: number;
    votes_cast: number;
    anchored_on_chain: number;
    awaiting_anchor: number;
    chain_records: number;
    first_contribution_at: string | null;
    last_contribution_at: string | null;
  };
  contributions: Contribution[];
  chain_records: ProfileChainRecord[];
  votes: Vote[];
}

export interface CampaignUpdate {
  id: number;
  campaign_id: number;
  title: string;
  body: string;
  is_pinned: boolean;
  author_name: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface PublicContribution {
  id: number;
  amount: string;
  contributor_name: string;
  status: string;
  blockchain_tx: string | null;
  created_at: string;
}

export interface Feedback {
  id: number;
  campaign_id: number;
  text: string;
  rating: number;
  sentiment: Sentiment;
  sentiment_score: number | null;
  aspect: string | null;
  aspects: string[];
  aspect_label: string | null;
  author_name: string | null;
  created_at: string;
}

export interface GovernanceResult {
  votes: number;
  weight: number;
  percentage: number;
}

export interface Governance {
  campaign_public_id: string;
  campaign_title: string;
  campaign_status: CampaignStatus;
  status: string;
  is_open: boolean;
  closes_at: string | null;
  total_eligible_voters: number;
  votes_cast: number;
  participation_percentage: number;
  results: Record<string, GovernanceResult>;
  leading_choice: string | null;
  selected_outcome: string | null;
  weight_mode: string;
  options: VoteChoice[];
  target_amount: string;
  raised_amount: string;
  shortfall: string;
  viewer: {
    is_eligible: boolean;
    has_voted: boolean;
    vote: { choice: string; weight: number; created_at: string; blockchain_tx: string | null } | null;
    reason: string | null;
  } | null;
  blockchain_records: BlockchainRecord[];
  note: string;
}

export interface Vote {
  id: number;
  campaign_id: number;
  choice: VoteChoice;
  weight: string;
  blockchain_tx: string | null;
  blockchain_status: string | null;
  created_at: string;
  campaign_title: string | null;
  campaign_public_id: string | null;
}

export interface KYCStatusResponse {
  status: KYCStatus;
  provider: string | null;
  reference: string | null;
  submitted_at: string | null;
  verified_at: string | null;
  demo_mode: boolean;
  checks: Record<string, string> | null;
  notice: string;
}

export interface QRResponse {
  public_id: string;
  campaign_url: string;
  qr_token: string | null;
  qr_image_data_uri: string;
  download_url: string;
}

export interface AdminDashboard {
  total_campaigns: number;
  pending_reviews: number;
  active_campaigns: number;
  completed_campaigns: number;
  rejected_campaigns: number;
  governance_campaigns: number;
  total_contributions_amount: string;
  total_contributions_count: number;
  total_contributors: number;
  total_creators: number;
  kyc_summary: Record<string, number>;
  failed_payments: number;
  unverified_payments: number;
  blockchain_pending: number;
  blockchain_failed: number;
  demo_mode: boolean;
}

export interface AdminReview {
  campaign: CampaignSummary;
  description: string;
  problem_statement: string;
  proposed_solution: string;
  expected_impact: string | null;
  creator: {
    id: number;
    name: string;
    email: string;
    phone: string | null;
    kyc_status: KYCStatus;
    kyc_verified_at: string | null;
    kyc_reference: string | null;
    campaigns_created: number;
  };
  application: CampaignApplication | null;
  application_fee_paid: boolean;
  application_fee_webhook_verified: boolean;
  analysis: AIAnalysis | null;
  sentiment: SentimentSummary | null;
  risk_indicators: string[];
  recommended_questions: string[];
  documents: { id: number; file_name: string; mime_type: string; size: number; created_at: string; url: string | null }[];
  review_notes: string | null;
  allowed_actions: string[];
}

export interface AuditLog {
  id: number;
  actor_id: number | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface CreatorDashboard {
  cards: {
    active_campaigns: number;
    total_campaigns: number;
    total_raised: string;
    contributors: number;
    average_rating: number | null;
    positive_sentiment: number;
    average_health: number | null;
    ai_risk_level: string | null;
  };
  campaigns: (CampaignSummary & {
    positive_percentage: number;
    feedback_count: number;
    approval_status: string;
    governance_status: string;
  })[];
}

export interface ContributorDashboard {
  cards: {
    total_contributed: string;
    campaigns_supported: number;
    contributions: number;
    blockchain_recorded: number;
    open_votes: number;
  };
  recent_contributions: Contribution[];
  active_votes: {
    public_id: string;
    title: string;
    closes_at: string | null;
    has_voted: boolean;
    raised_amount: string;
    target_amount: string;
  }[];
  past_votes: Vote[];
}

export interface CampaignAnalytics {
  campaign: CampaignSummary;
  funding_series: { date: string; amount: number; cumulative: number }[];
  contribution_count: number;
  sentiment: SentimentSummary;
  health: CampaignHealth;
  blockchain: BlockchainSummary;
}

export interface PlatformStats {
  live_campaigns: number;
  total_raised: string;
  contributors: number;
  verified_creators: number;
  blockchain_records: number;
}
