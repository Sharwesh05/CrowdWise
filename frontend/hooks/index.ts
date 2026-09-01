"use client";

/**
 * TanStack Query hooks — the only place the app talks to the API.
 *
 * Polling is used deliberately and sparingly: payment verification and chain
 * anchoring are genuinely asynchronous server-side processes, so the UI polls
 * those and nothing else.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";
import type {
  AdminDashboard,
  AIAnalysis,
  AdminReview,
  AuditLog,
  AuthResponse,
  BlockchainRecord,
  CampaignAnalytics,
  CampaignDocument,
  CampaignSummary,
  CampaignUpdate,
  CommunityInsight,
  Contribution,
  ContributorDashboard,
  CreatorCampaign,
  CreatorDashboard,
  DocumentVisibility,
  Feedback,
  Governance,
  KYCStatusResponse,
  OrderResponse,
  Page,
  PlatformStats,
  Profile,
  PublicCampaign,
  PublicContribution,
  QRResponse,
  SentimentSummary,
  SessionUser,
  SharedDocuments,
  VerificationProgress,
  Vote,
  VoteChoice,
} from "@/types";

export const keys = {
  me: ["me"] as const,
  kyc: ["kyc"] as const,
  publicCampaigns: (params: string) => ["public-campaigns", params] as const,
  publicCampaign: (id: string) => ["public-campaign", id] as const,
  campaignFeedback: (id: string, page: number) => ["feedback", id, page] as const,
  campaignContributions: (id: string) => ["campaign-contributions", id] as const,
  campaignBlockchain: (id: string) => ["campaign-blockchain", id] as const,
  insights: (id: string) => ["insights", id] as const,
  governance: (id: string) => ["governance", id] as const,
  myCampaigns: ["my-campaigns"] as const,
  campaign: (id: number) => ["campaign", id] as const,
  qr: (id: number) => ["qr", id] as const,
  creatorDashboard: ["creator-dashboard"] as const,
  analytics: (id: string) => ["analytics", id] as const,
  contributorDashboard: ["contributor-dashboard"] as const,
  myContributions: ["my-contributions"] as const,
  myVotes: ["my-votes"] as const,
  campaignUpdates: (id: string) => ["campaign-updates", id] as const,
  campaignDocuments: (id: number) => ["campaign-documents", id] as const,
  publicDocuments: (id: string) => ["public-documents", id] as const,
  profile: ["profile"] as const,
  adminDashboard: ["admin-dashboard"] as const,
  adminPending: ["admin-pending"] as const,
  adminCampaigns: (status: string) => ["admin-campaigns", status] as const,
  adminReview: (id: string) => ["admin-review", id] as const,
  auditLogs: ["audit-logs"] as const,
  chainStatus: ["chain-status"] as const,
  stats: ["platform-stats"] as const,
};

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------
export function useSession() {
  return useQuery<SessionUser | null>({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await api.get<SessionUser>("/api/auth/me");
      } catch (error) {
        // Not signed in is a state, not a failure — don't surface it as an error.
        if (error instanceof ApiError && error.isUnauthenticated) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { email: string; password: string }) =>
      api.post<AuthResponse>("/api/auth/login", payload),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.me, data.user);
      queryClient.invalidateQueries();
    },
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      name: string;
      email: string;
      password: string;
      role: string;
      phone?: string;
    }) => api.post<AuthResponse>("/api/auth/register", payload),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.me, data.user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ message: string }>("/api/auth/logout"),
    onSuccess: () => {
      queryClient.setQueryData(keys.me, null);
      queryClient.clear();
    },
  });
}

// ---------------------------------------------------------------------------
// KYC
// ---------------------------------------------------------------------------
export function useKycStatus(enabled = true) {
  return useQuery<KYCStatusResponse>({
    queryKey: keys.kyc,
    queryFn: () => api.get<KYCStatusResponse>("/api/kyc/status"),
    enabled,
    // While the demo provider settles, poll so the UI shows the real progression.
    refetchInterval: (query) =>
      ["SUBMITTED", "PROCESSING"].includes(query.state.data?.status ?? "") ? 1500 : false,
  });
}

export function useSubmitKyc() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post<KYCStatusResponse>("/api/kyc/submit", payload),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.kyc, data);
      queryClient.invalidateQueries({ queryKey: keys.me });
    },
  });
}

export function useCompleteKyc() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<KYCStatusResponse>("/api/kyc/complete"),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.kyc, data);
      queryClient.invalidateQueries({ queryKey: keys.me });
    },
  });
}

// ---------------------------------------------------------------------------
// Public discovery
// ---------------------------------------------------------------------------
export interface CampaignFilters {
  search?: string;
  category?: string;
  status?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

export function buildQuery(filters: Record<string, unknown>): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function usePublicCampaigns(filters: CampaignFilters) {
  const query = buildQuery(filters as Record<string, unknown>);
  return useQuery<Page<CampaignSummary>>({
    queryKey: keys.publicCampaigns(query),
    queryFn: () => api.get<Page<CampaignSummary>>(`/api/public/campaigns${query}`),
    placeholderData: (previous) => previous,
  });
}

export function usePublicCampaign(publicId: string, options?: Partial<UseQueryOptions<PublicCampaign>>) {
  return useQuery<PublicCampaign>({
    queryKey: keys.publicCampaign(publicId),
    queryFn: () => api.get<PublicCampaign>(`/api/public/campaigns/${publicId}`),
    enabled: Boolean(publicId),
    ...options,
  });
}

export function usePlatformStats() {
  return useQuery<PlatformStats>({
    queryKey: keys.stats,
    queryFn: () => api.get<PlatformStats>("/api/public/stats"),
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Feedback and community
// ---------------------------------------------------------------------------
export function useCampaignFeedback(publicId: string, page = 0, limit = 5) {
  return useQuery<Page<Feedback>>({
    queryKey: keys.campaignFeedback(publicId, page),
    queryFn: () =>
      api.get<Page<Feedback>>(
        `/api/public/campaigns/${publicId}/feedback${buildQuery({ limit, offset: page * limit })}`,
      ),
    enabled: Boolean(publicId),
    placeholderData: (previous) => previous,
  });
}

export function useSubmitFeedback(publicId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { text: string; rating: number }) =>
      api.post<Feedback>(`/api/campaigns/${publicId}/feedback`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feedback", publicId] });
      queryClient.invalidateQueries({ queryKey: keys.publicCampaign(publicId) });
    },
  });
}

export function useCommunityInsights(publicId: string) {
  return useQuery<CommunityInsight | null>({
    queryKey: keys.insights(publicId),
    queryFn: async () => {
      try {
        return await api.get<CommunityInsight>(`/api/campaigns/${publicId}/community-insights`);
      } catch (error) {
        // "No insights yet" is an empty state, not an error.
        if (error instanceof ApiError && error.isNotFound) return null;
        throw error;
      }
    },
    enabled: Boolean(publicId),
  });
}

export function useRefreshInsights(publicId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<CommunityInsight>(`/api/campaigns/${publicId}/community-insights/refresh`),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.insights(publicId), data);
      queryClient.invalidateQueries({ queryKey: keys.publicCampaign(publicId) });
    },
  });
}

export function useRefreshAnalysis(publicId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<AIAnalysis>(`/api/campaigns/${publicId}/analysis/refresh`),
    onSuccess: () => {
      // The analysis is embedded in the campaign payloads rather than cached on
      // its own, so refetch whichever view is mounted.
      queryClient.invalidateQueries({ queryKey: keys.publicCampaign(publicId) });
      queryClient.invalidateQueries({ queryKey: keys.myCampaigns });
      queryClient.invalidateQueries({ queryKey: keys.adminReview(publicId) });
    },
  });
}

export function useRefreshSentiment(publicId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<SentimentSummary>(`/api/campaigns/${publicId}/sentiment/refresh`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.publicCampaign(publicId) });
      queryClient.invalidateQueries({ queryKey: keys.insights(publicId) });
      queryClient.invalidateQueries({ queryKey: keys.myCampaigns });
      queryClient.invalidateQueries({ queryKey: keys.adminReview(publicId) });
    },
  });
}

/**
 * `enabled` is false before a campaign is published: the updates endpoint is the
 * public one, which does not answer for a campaign that is not public yet. Asking
 * anyway would turn "not applicable" into a red error on the creator's own page.
 */
export function useCampaignUpdates(publicId: string, enabled = true) {
  return useQuery<Page<CampaignUpdate>>({
    queryKey: keys.campaignUpdates(publicId),
    queryFn: () => api.get<Page<CampaignUpdate>>(`/api/campaigns/${publicId}/updates?limit=50`),
    enabled: enabled && Boolean(publicId),
  });
}

function useUpdateMutation<TArgs>(
  publicId: string,
  request: (args: TArgs) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.campaignUpdates(publicId) });
      // update_count lives on the campaign payload, so the tab badge is stale
      // until the campaign is refetched too.
      queryClient.invalidateQueries({ queryKey: keys.publicCampaign(publicId) });
    },
  });
}

export function usePostUpdate(publicId: string) {
  return useUpdateMutation(publicId, (payload: { title: string; body: string }) =>
    api.post<CampaignUpdate>(`/api/campaigns/${publicId}/updates`, payload),
  );
}

export function useEditUpdate(publicId: string) {
  return useUpdateMutation(
    publicId,
    ({ id, ...payload }: { id: number; title?: string; body?: string; is_pinned?: boolean }) =>
      api.patch<CampaignUpdate>(`/api/campaigns/${publicId}/updates/${id}`, payload),
  );
}

export function useDeleteUpdate(publicId: string) {
  return useUpdateMutation(publicId, (id: number) =>
    api.delete<{ message: string }>(`/api/campaigns/${publicId}/updates/${id}`),
  );
}

export function useCampaignContributions(publicId: string) {
  return useQuery<Page<PublicContribution>>({
    queryKey: keys.campaignContributions(publicId),
    queryFn: () =>
      api.get<Page<PublicContribution>>(`/api/public/campaigns/${publicId}/contributions?limit=10`),
    enabled: Boolean(publicId),
  });
}

export function useCampaignBlockchain(publicId: string) {
  return useQuery<BlockchainRecord[]>({
    queryKey: keys.campaignBlockchain(publicId),
    queryFn: () => api.get<BlockchainRecord[]>(`/api/campaigns/${publicId}/blockchain`),
    enabled: Boolean(publicId),
  });
}

// ---------------------------------------------------------------------------
// Payments
// ---------------------------------------------------------------------------
export function useCreateContribution(publicId: string) {
  return useMutation({
    mutationFn: (payload: { amount: string; is_anonymous?: boolean }) =>
      api.post<OrderResponse>(`/api/campaigns/${publicId}/contribute`, payload),
  });
}

export function useVerifyPayment() {
  return useMutation({
    mutationFn: (payload: {
      razorpay_order_id: string;
      razorpay_payment_id: string;
      razorpay_signature: string;
    }) => api.post<VerificationProgress>("/api/payments/verify", payload),
  });
}

export function useSimulatePayment() {
  return useMutation({
    mutationFn: (paymentId: number) =>
      api.post<VerificationProgress>(`/api/payments/${paymentId}/simulate`),
  });
}

/**
 * Polls the real server-side progression:
 *   received → verified → contribution recorded → anchored.
 * Stops as soon as the chain record is final either way.
 */
export function usePaymentProgress(paymentId: number | null, enabled: boolean) {
  return useQuery<VerificationProgress>({
    queryKey: ["payment-progress", paymentId],
    queryFn: () => api.get<VerificationProgress>(`/api/payments/${paymentId}/progress`),
    enabled: enabled && Boolean(paymentId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1500;
      const settled =
        data.blockchain_status === "BLOCKCHAIN_RECORDED" ||
        data.blockchain_status === "BLOCKCHAIN_FAILED";
      return settled ? false : 1500;
    },
  });
}

export function useMyContributions() {
  return useQuery<Page<Contribution>>({
    queryKey: keys.myContributions,
    queryFn: () => api.get<Page<Contribution>>("/api/contributions/my?limit=50"),
  });
}

export function useRetryBlockchain() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contributionId: number) =>
      api.post<{ recorded: boolean; status: string; tx_hash: string | null }>(
        `/api/blockchain/contributions/${contributionId}/retry`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.myContributions });
      queryClient.invalidateQueries({ queryKey: keys.contributorDashboard });
    },
  });
}

// ---------------------------------------------------------------------------
// Creator
// ---------------------------------------------------------------------------
export function useMyCampaigns() {
  return useQuery<CreatorCampaign[]>({
    queryKey: keys.myCampaigns,
    queryFn: () => api.get<CreatorCampaign[]>("/api/campaigns/my"),
  });
}

export function useCampaign(campaignId: number) {
  return useQuery<CreatorCampaign>({
    queryKey: keys.campaign(campaignId),
    queryFn: () => api.get<CreatorCampaign>(`/api/campaigns/${campaignId}`),
    enabled: Number.isFinite(campaignId) && campaignId > 0,
  });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post<CreatorCampaign>("/api/campaigns", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.myCampaigns }),
  });
}

/** Correct a proposal that has not yet been acted on by a reviewer. */
export function useUpdateCampaign(campaignId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.patch<CreatorCampaign>(`/api/campaigns/${campaignId}`, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.campaign(campaignId), data);
      queryClient.invalidateQueries({ queryKey: keys.myCampaigns });
      queryClient.invalidateQueries({ queryKey: keys.publicCampaign(data.public_id) });
    },
  });
}

export function useSubmitCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (campaignId: number) =>
      api.post<CreatorCampaign>(`/api/campaigns/${campaignId}/submit`),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.campaign(data.id), data);
      queryClient.invalidateQueries({ queryKey: keys.myCampaigns });
    },
  });
}

export function useApplicationFeeOrder() {
  return useMutation({
    mutationFn: (campaignId: number) =>
      api.post<OrderResponse>(`/api/campaigns/${campaignId}/application-fee/order`),
  });
}

export function useRunAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (campaignId: number) =>
      api.post<CreatorCampaign>(`/api/campaigns/${campaignId}/analyze`),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.campaign(data.id), data);
      queryClient.invalidateQueries({ queryKey: keys.myCampaigns });
    },
  });
}

export function useCampaignQr(campaignId: number, enabled: boolean) {
  return useQuery<QRResponse>({
    queryKey: keys.qr(campaignId),
    queryFn: () => api.get<QRResponse>(`/api/campaigns/${campaignId}/qr`),
    enabled: enabled && campaignId > 0,
  });
}

// ---------------------------------------------------------------------------
// Supporting documents
// ---------------------------------------------------------------------------

/** Every document on a campaign the caller owns (or administers), both tiers. */
export function useCampaignDocuments(campaignId: number) {
  return useQuery<CampaignDocument[]>({
    queryKey: keys.campaignDocuments(campaignId),
    queryFn: () => api.get<CampaignDocument[]>(`/api/campaigns/${campaignId}/documents`),
    enabled: Number.isFinite(campaignId) && campaignId > 0,
  });
}

export function useUploadDocument(campaignId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, visibility }: { file: File; visibility: DocumentVisibility }) => {
      const body = new FormData();
      body.append("file", file);
      body.append("visibility", visibility);
      return api.post<CampaignDocument>(`/api/campaigns/${campaignId}/documents`, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.campaignDocuments(campaignId) });
      queryClient.invalidateQueries({ queryKey: keys.campaign(campaignId) });
    },
  });
}

export function useDeleteDocument(campaignId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: number) =>
      api.delete<{ message: string }>(`/api/campaigns/${campaignId}/documents/${documentId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.campaignDocuments(campaignId) });
    },
  });
}

export function useUploadCoverImage(campaignId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return api.post<CreatorCampaign>(`/api/campaigns/${campaignId}/cover-image`, body);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(keys.campaign(campaignId), data);
      queryClient.invalidateQueries({ queryKey: keys.myCampaigns });
    },
  });
}

/** The SHARED documents a signed-in visitor may open on a public campaign. */
export function usePublicDocuments(publicId: string) {
  return useQuery<SharedDocuments>({
    queryKey: keys.publicDocuments(publicId),
    queryFn: () => api.get<SharedDocuments>(`/api/public/campaigns/${publicId}/documents`),
    enabled: Boolean(publicId),
  });
}

export function useCreatorDashboard() {
  return useQuery<CreatorDashboard>({
    queryKey: keys.creatorDashboard,
    queryFn: () => api.get<CreatorDashboard>("/api/creator/dashboard"),
  });
}

export function useCampaignAnalytics(publicId: string) {
  return useQuery<CampaignAnalytics>({
    queryKey: keys.analytics(publicId),
    queryFn: () => api.get<CampaignAnalytics>(`/api/creator/campaigns/${publicId}/analytics`),
    enabled: Boolean(publicId),
  });
}

// ---------------------------------------------------------------------------
// Contributor
// ---------------------------------------------------------------------------
export function useContributorDashboard() {
  return useQuery<ContributorDashboard>({
    queryKey: keys.contributorDashboard,
    queryFn: () => api.get<ContributorDashboard>("/api/contributor/dashboard"),
  });
}

export function useProfile() {
  return useQuery<Profile>({
    queryKey: keys.profile,
    queryFn: () => api.get<Profile>("/api/profile"),
  });
}

export function useMyVotes() {
  return useQuery<Page<Vote>>({
    queryKey: keys.myVotes,
    queryFn: () => api.get<Page<Vote>>("/api/votes/my?limit=50"),
  });
}

// ---------------------------------------------------------------------------
// Governance
// ---------------------------------------------------------------------------
export function useGovernance(publicId: string, enabled = true) {
  return useQuery<Governance>({
    queryKey: keys.governance(publicId),
    queryFn: () => api.get<Governance>(`/api/campaigns/${publicId}/governance`),
    enabled: enabled && Boolean(publicId),
  });
}

export function useCastVote(publicId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (choice: VoteChoice) =>
      api.post<Governance>(`/api/campaigns/${publicId}/vote`, { choice }),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.governance(publicId), data);
      queryClient.invalidateQueries({ queryKey: keys.contributorDashboard });
      queryClient.invalidateQueries({ queryKey: keys.myVotes });
    },
  });
}

export function useCloseGovernance(publicId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Governance>(`/api/campaigns/${publicId}/governance/close`),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.governance(publicId), data);
      queryClient.invalidateQueries({ queryKey: keys.publicCampaign(publicId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------
export function useAdminDashboard() {
  return useQuery<AdminDashboard>({
    queryKey: keys.adminDashboard,
    queryFn: () => api.get<AdminDashboard>("/api/admin/dashboard"),
  });
}

export function useAdminPending() {
  return useQuery<Page<CampaignSummary>>({
    queryKey: keys.adminPending,
    queryFn: () => api.get<Page<CampaignSummary>>("/api/admin/campaigns/pending?limit=50"),
  });
}

export function useAdminCampaigns(status: string) {
  return useQuery<Page<CampaignSummary>>({
    queryKey: keys.adminCampaigns(status),
    queryFn: () =>
      api.get<Page<CampaignSummary>>(`/api/admin/campaigns${buildQuery({ status, limit: 50 })}`),
  });
}

export function useAdminReview(publicId: string) {
  return useQuery<AdminReview>({
    queryKey: keys.adminReview(publicId),
    queryFn: () => api.get<AdminReview>(`/api/admin/campaigns/${publicId}`),
    enabled: Boolean(publicId),
  });
}

export function useAdminDecision(publicId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: keys.adminReview(publicId) });
    queryClient.invalidateQueries({ queryKey: keys.adminPending });
    queryClient.invalidateQueries({ queryKey: keys.adminDashboard });
  };

  const approve = useMutation({
    mutationFn: (notes?: string) =>
      api.post<CreatorCampaign>(`/api/admin/campaigns/${publicId}/approve`, { notes }),
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: (reason: string) =>
      api.post<CreatorCampaign>(`/api/admin/campaigns/${publicId}/reject`, { reason }),
    onSuccess: invalidate,
  });
  const requestChanges = useMutation({
    mutationFn: (notes: string) =>
      api.post<CreatorCampaign>(`/api/admin/campaigns/${publicId}/request-changes`, { notes }),
    onSuccess: invalidate,
  });

  return { approve, reject, requestChanges };
}

export function useAuditLogs() {
  return useQuery<Page<AuditLog>>({
    queryKey: keys.auditLogs,
    queryFn: () => api.get<Page<AuditLog>>("/api/admin/audit-logs?limit=100"),
  });
}

export function useChainStatus() {
  return useQuery<{
    provider: string;
    network: string;
    contract_address: string | null;
    chain_id: number;
    simulated: boolean;
    records_total: number;
    pending_records: number;
    note: string;
    explorer_url: string | null;
  }>({
    queryKey: keys.chainStatus,
    queryFn: () => api.get("/api/blockchain/status"),
  });
}

export function useDemoControl() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { action: string; campaign_public_id?: string; user_email?: string }) =>
      api.post<{ action: string; status: string; message: string; detail: Record<string, unknown> }>(
        "/api/admin/demo/control",
        payload,
      ),
    onSuccess: () => {
      // A demo control can change almost anything; refresh broadly.
      queryClient.invalidateQueries();
    },
  });
}
