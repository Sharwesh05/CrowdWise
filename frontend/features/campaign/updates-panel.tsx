"use client";

import { useState } from "react";
import { Megaphone, Pin, PinOff, Trash2 } from "lucide-react";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Skeleton,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  useCampaignUpdates,
  useDeleteUpdate,
  useEditUpdate,
  usePostUpdate,
} from "@/hooks";
import { formatDateTime } from "@/lib/format";
import type { CampaignUpdate } from "@/types";

const TITLE_MIN = 4;
const BODY_MIN = 20;

export function UpdatesPanel({
  publicId,
  canPost = false,
  published = true,
}: {
  publicId: string;
  /** True for the campaign's own creator and for admins. */
  canPost?: boolean;
  /** False before the campaign goes live, when there is nothing to fetch yet. */
  published?: boolean;
}) {
  // Updates cannot be read or written before publication, so an unpublished
  // campaign does not ask: the creator gets an explanation of when this opens,
  // not a failed request dressed up as an error.
  const { data, isLoading, isError, refetch } = useCampaignUpdates(publicId, published);

  if (!published) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Megaphone className="h-4 w-4 text-accent-600" aria-hidden />
            Updates
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={<Megaphone className="h-6 w-6" />}
            title="Updates open when your campaign goes live"
            description="Once a reviewer approves the campaign you can post progress here, and your backers will see it on the campaign page."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {canPost && <ComposeUpdate publicId={publicId} />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Megaphone className="h-4 w-4 text-accent-600" aria-hidden />
            Updates
          </CardTitle>
          <CardDescription>
            What the creator is doing to reach people and deliver the project. Posted by the
            campaign, not by contributors — leave your own thoughts under Community.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isError ? (
            <ErrorState title="Could not load updates" onRetry={() => refetch()} />
          ) : isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 2 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : !data || data.items.length === 0 ? (
            <EmptyState
              icon={<Megaphone className="h-6 w-6" />}
              title="No updates yet"
              description={
                canPost
                  ? "Post your first update. Campaigns that report progress keep their backers."
                  : "The creator has not posted an update yet."
              }
            />
          ) : (
            <ol className="space-y-4">
              {data.items.map((update) => (
                <UpdateItem
                  key={update.id}
                  publicId={publicId}
                  update={update}
                  canManage={canPost}
                />
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// --------------------------------------------------------------------------
function ComposeUpdate({ publicId }: { publicId: string }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const post = usePostUpdate(publicId);
  const { notify } = useToast();

  const valid = title.trim().length >= TITLE_MIN && body.trim().length >= BODY_MIN;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    try {
      await post.mutateAsync({ title: title.trim(), body: body.trim() });
      setTitle("");
      setBody("");
      notify({ title: "Update posted", tone: "positive" });
    } catch (caught) {
      notify({
        title: "Could not post the update",
        description: caught instanceof Error ? caught.message : undefined,
        tone: "critical",
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Post an update</CardTitle>
        <CardDescription>
          Outreach, milestones, setbacks. Contributors see this on the campaign page.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Title" htmlFor="update-title">
            <Input
              id="update-title"
              value={title}
              maxLength={140}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Week 3: first 12 units installed"
            />
          </Field>
          <Field
            label="Update"
            htmlFor="update-body"
            hint={`${body.trim().length}/5000 — at least ${BODY_MIN} characters`}
          >
            <Textarea
              id="update-body"
              rows={5}
              value={body}
              maxLength={5000}
              onChange={(event) => setBody(event.target.value)}
              placeholder="What happened, who you spoke to, what is next."
            />
          </Field>
          <div className="flex justify-end">
            <Button type="submit" disabled={!valid} loading={post.isPending}>
              Post update
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------
function UpdateItem({
  publicId,
  update,
  canManage,
}: {
  publicId: string;
  update: CampaignUpdate;
  canManage: boolean;
}) {
  const edit = useEditUpdate(publicId);
  const remove = useDeleteUpdate(publicId);
  const { notify } = useToast();
  const [confirming, setConfirming] = useState(false);

  const togglePin = async () => {
    await edit.mutateAsync({ id: update.id, is_pinned: !update.is_pinned });
    notify({ title: update.is_pinned ? "Unpinned" : "Pinned to the top", tone: "info" });
  };

  const confirmDelete = async () => {
    await remove.mutateAsync(update.id);
    setConfirming(false);
    notify({ title: "Update deleted", tone: "info" });
  };

  return (
    <li className="rounded-lg border border-surface-border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold text-ink">{update.title}</h4>
            {update.is_pinned && (
              <Badge tone="brand">
                <Pin className="mr-1 h-3 w-3" aria-hidden />
                pinned
              </Badge>
            )}
          </div>
          <p className="mt-1 text-xs text-ink-faint">
            {update.author_name ?? "The campaign"} · {formatDateTime(update.created_at)}
            {update.updated_at && " · edited"}
          </p>
        </div>

        {canManage && (
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={togglePin}
              loading={edit.isPending}
              aria-label={update.is_pinned ? "Unpin this update" : "Pin this update"}
            >
              {update.is_pinned ? (
                <PinOff className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Pin className="h-3.5 w-3.5" aria-hidden />
              )}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirming((open) => !open)}
              aria-label="Delete this update"
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden />
            </Button>
          </div>
        )}
      </div>

      {/* whitespace-pre-line keeps the creator's paragraph breaks without
          rendering their text as HTML. */}
      <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-soft">
        {update.body}
      </p>

      {confirming && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md bg-critical-soft px-3 py-2">
          <span className="text-xs text-critical-strong">Delete this update permanently?</span>
          <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={confirmDelete} loading={remove.isPending}>
            Delete
          </Button>
        </div>
      )}
    </li>
  );
}
