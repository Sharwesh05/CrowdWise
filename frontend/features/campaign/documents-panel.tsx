"use client";

import { useRef, useState } from "react";
import {
  Bot,
  Eye,
  FileText,
  ImageIcon,
  Trash2,
  Upload,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Field,
  Select,
  Skeleton,
  useToast,
} from "@/components/ui";
import { API_URL, ApiError, mediaUrl } from "@/lib/api";
import {
  useCampaignDocuments,
  useDeleteDocument,
  useUploadCoverImage,
  useUploadDocument,
} from "@/hooks";
import type { CampaignDocument, DocumentVisibility } from "@/types";

const ACCEPT = ".pdf,.txt,.jpg,.jpeg,.png,.webp";
const IMAGE_ACCEPT = ".jpg,.jpeg,.png,.webp";

const VISIBILITY_META: Record<
  DocumentVisibility,
  { label: string; description: string; tone: "info" | "neutral" }
> = {
  SHARED: {
    label: "Signed-in supporters",
    description:
      "Anyone signed in can open this once the campaign is live. The AI reads it too.",
    tone: "info",
  },
  AI_ONLY: {
    label: "Private — AI only",
    description:
      "Never shown to supporters. Only you, the reviewing admin and the AI can open it.",
    tone: "neutral",
  },
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * The creator's view of everything attached to a campaign.
 *
 * Two things this panel is careful to be honest about: which documents a
 * supporter will actually be able to open, and whether the AI could read a file
 * at all. A creator who uploads a scanned budget should learn immediately that
 * the model saw nothing in it, not discover it from a weak analysis later.
 */
export function DocumentsPanel({
  campaignId,
  coverImageUrl,
}: {
  campaignId: number;
  coverImageUrl?: string | null;
}) {
  return (
    <div className="space-y-6">
      <CoverImageCard campaignId={campaignId} coverImageUrl={coverImageUrl} />
      <SupportingDocumentsCard campaignId={campaignId} />
    </div>
  );
}

function CoverImageCard({
  campaignId,
  coverImageUrl,
}: {
  campaignId: number;
  coverImageUrl?: string | null;
}) {
  const upload = useUploadCoverImage(campaignId);
  const { notify } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      await upload.mutateAsync(file);
      notify({ tone: "positive", title: "Cover image updated." });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not upload the image.");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cover image</CardTitle>
        <CardDescription>
          The single image at the top of your campaign page. JPEG, PNG or WebP. It is public,
          so use something you are happy for anyone to see.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <Alert tone="critical">{error}</Alert>}

        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div className="grid h-32 w-full shrink-0 place-items-center overflow-hidden rounded-lg border border-surface-border bg-surface-subtle sm:w-56">
            {coverImageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={mediaUrl(coverImageUrl)}
                alt="Campaign cover"
                className="h-full w-full object-cover"
              />
            ) : (
              <span className="flex flex-col items-center gap-1 text-ink-faint">
                <ImageIcon className="h-6 w-6" aria-hidden />
                <span className="text-xs">No cover image</span>
              </span>
            )}
          </div>

          <div className="space-y-2">
            <input
              ref={inputRef}
              type="file"
              accept={IMAGE_ACCEPT}
              className="sr-only"
              onChange={(event) => pick(event.target.files?.[0])}
            />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              loading={upload.isPending}
              onClick={() => inputRef.current?.click()}
            >
              <Upload className="mr-1.5 h-4 w-4" aria-hidden />
              {coverImageUrl ? "Replace image" : "Upload image"}
            </Button>
            <p className="text-xs text-ink-faint">
              A wide image works best — roughly 3:1. The AI does not read images.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function SupportingDocumentsCard({ campaignId }: { campaignId: number }) {
  const { data: documents, isLoading } = useCampaignDocuments(campaignId);
  const upload = useUploadDocument(campaignId);
  const remove = useDeleteDocument(campaignId);
  const { notify } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [visibility, setVisibility] = useState<DocumentVisibility>("AI_ONLY");
  const [error, setError] = useState<string | null>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      const created = await upload.mutateAsync({ file, visibility });
      // A file the model cannot read is reported as an upload that succeeded
      // and an ingest that did not — never as a plain success.
      notify({
        tone: created.is_machine_readable ? "positive" : "info",
        title: `${created.file_name} uploaded.`,
        description: created.is_machine_readable
          ? "The AI can read this file."
          : created.extraction_note ?? "The AI cannot read this file.",
      });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not upload the document.");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const drop = async (documentId: number, name: string) => {
    try {
      await remove.mutateAsync(documentId);
      notify({ tone: "positive", title: `${name} removed.` });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not remove the document.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Supporting documents</CardTitle>
        <CardDescription>
          Budgets, quotes, plans, letters — the evidence behind your claims. The AI reads the
          text of every document you attach, whichever visibility you choose; the choice
          decides who <em>else</em> can open it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {error && <Alert tone="critical">{error}</Alert>}

        <div className="rounded-lg border border-dashed border-surface-border p-4">
          <Field
            label="Who can open this file?"
            htmlFor="doc-visibility"
            hint={VISIBILITY_META[visibility].description}
          >
            <Select
              id="doc-visibility"
              value={visibility}
              onChange={(event) => setVisibility(event.target.value as DocumentVisibility)}
            >
              <option value="AI_ONLY">Private — only you, the reviewer and the AI</option>
              <option value="SHARED">Signed-in supporters can open it</option>
            </Select>
          </Field>

          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            onChange={(event) => pick(event.target.files?.[0])}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="mt-3"
            loading={upload.isPending}
            onClick={() => inputRef.current?.click()}
          >
            <Upload className="mr-1.5 h-4 w-4" aria-hidden />
            Add document
          </Button>
          <p className="mt-2 text-xs text-ink-faint">
            PDF and plain text are read by the AI. Images are stored and shown, but not read.
          </p>
        </div>

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 2 }).map((_, index) => (
              <Skeleton key={index} className="h-16 w-full" />
            ))}
          </div>
        ) : !documents || documents.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="No documents attached"
            description="A campaign with evidence behind its numbers reviews better than one without."
          />
        ) : (
          <ul className="divide-y divide-surface-border">
            {documents.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                onRemove={() => drop(document.id, document.file_name)}
                removing={remove.isPending}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function DocumentRow({
  document,
  onRemove,
  removing,
}: {
  document: CampaignDocument;
  onRemove: () => void;
  removing: boolean;
}) {
  const meta = VISIBILITY_META[document.visibility];
  return (
    <li className="flex flex-wrap items-start gap-3 py-3">
      <span className="mt-0.5 text-ink-faint">
        {document.mime_type.startsWith("image/") ? (
          <ImageIcon className="h-5 w-5" aria-hidden />
        ) : (
          <FileText className="h-5 w-5" aria-hidden />
        )}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <a
            href={document.url ? `${API_URL}${document.url}` : undefined}
            target="_blank"
            rel="noreferrer"
            className="truncate text-sm font-medium text-ink hover:underline"
          >
            {document.file_name}
          </a>
          <Badge tone={meta.tone === "info" ? "info" : "neutral"}>
            {document.visibility === "SHARED" ? (
              <Eye className="mr-1 h-3 w-3" aria-hidden />
            ) : (
              <Bot className="mr-1 h-3 w-3" aria-hidden />
            )}
            {meta.label}
          </Badge>
        </div>

        <p className="mt-0.5 text-xs text-ink-faint">{formatSize(document.size)}</p>

        <p
          className={`mt-1 flex items-start gap-1.5 text-xs ${
            document.is_machine_readable ? "text-ink-muted" : "text-caution-strong"
          }`}
        >
          {document.is_machine_readable ? (
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          ) : (
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          )}
          <span>
            {document.is_machine_readable
              ? "The AI can read this file."
              : "The AI cannot read this file."}
            {document.extraction_note ? ` ${document.extraction_note}` : ""}
          </span>
        </p>
      </div>

      <Button
        type="button"
        variant="ghost"
        size="sm"
        loading={removing}
        onClick={onRemove}
        aria-label={`Remove ${document.file_name}`}
      >
        <Trash2 className="h-4 w-4" aria-hidden />
      </Button>
    </li>
  );
}
