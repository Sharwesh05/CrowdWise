"use client";

import Link from "next/link";
import { Bot, FileText, Lock } from "lucide-react";

import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
} from "@/components/ui";
import { API_URL } from "@/lib/api";
import { usePublicDocuments } from "@/hooks";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Supporting documents on the public campaign page.
 *
 * The counts are shown to everyone and the files only to a signed-in reader.
 * Documents held back for the reviewer and the AI are counted rather than
 * hidden: a reader is entitled to know that the analysis they are reading was
 * informed by material they cannot check themselves.
 */
export function SharedDocumentsPanel({ publicId }: { publicId: string }) {
  const { data, isLoading } = usePublicDocuments(publicId);

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;

  const nothingAttached = data.total === 0 && data.ai_only_count === 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Supporting documents</CardTitle>
        <CardDescription>
          Evidence the creator attached to this campaign. The AI analysis read all of it,
          including anything held back from public view.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {nothingAttached ? (
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="No documents attached"
            description="This creator has not attached any supporting evidence."
          />
        ) : (
          <>
            {data.requires_sign_in ? (
              <div className="rounded-lg border border-dashed border-surface-border p-4 text-sm text-ink-muted">
                <Lock className="mb-1.5 h-4 w-4 text-ink-faint" aria-hidden />
                <p>
                  {data.total} document{data.total === 1 ? " is" : "s are"} shared with signed-in
                  supporters.{" "}
                  <Link href="/login" className="font-medium text-brand-700 hover:underline">
                    Sign in
                  </Link>{" "}
                  to open {data.total === 1 ? "it" : "them"}.
                </p>
              </div>
            ) : data.documents.length > 0 ? (
              <ul className="divide-y divide-surface-border">
                {data.documents.map((document) => (
                  <li key={document.id} className="flex items-center gap-3 py-3">
                    <FileText className="h-5 w-5 shrink-0 text-ink-faint" aria-hidden />
                    <div className="min-w-0 flex-1">
                      <a
                        href={document.url ? `${API_URL}${document.url}` : undefined}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate text-sm font-medium text-ink hover:underline"
                      >
                        {document.file_name}
                      </a>
                      <p className="mt-0.5 text-xs text-ink-faint">
                        {formatSize(document.size)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}

            {data.ai_only_count > 0 && (
              <p className="flex items-start gap-2 rounded-lg bg-surface-subtle p-3 text-xs text-ink-muted">
                <Bot className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" aria-hidden />
                <span>
                  <Badge tone="neutral" className="mr-1.5">
                    {data.ai_only_count} private
                  </Badge>
                  {data.ai_only_count === 1 ? "document was" : "documents were"} given to the AI
                  analyst and the reviewing admin, but not published. You are seeing an analysis
                  informed by material that is not shown here.
                </span>
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
