"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Dialog, Field, StarRating, Textarea, useToast } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useSession, useSubmitFeedback } from "@/hooks";

const MIN_LENGTH = 10;
const MAX_LENGTH = 2000;

export function FeedbackDialog({
  publicId,
  campaignTitle,
  open,
  onClose,
}: {
  publicId: string;
  campaignTitle: string;
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const { data: user } = useSession();
  const { notify } = useToast();
  const submit = useSubmitFeedback(publicId);

  const [rating, setRating] = useState(0);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const valid = rating > 0 && text.trim().length >= MIN_LENGTH;

  const handleSubmit = async () => {
    setError(null);
    if (!user) {
      router.push(`/login?next=/campaign/${publicId}`);
      return;
    }
    try {
      await submit.mutateAsync({ text: text.trim(), rating });
      notify({
        title: "Feedback submitted",
        description: "Sentiment and themes are being analysed.",
        tone: "positive",
      });
      setRating(0);
      setText("");
      onClose();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Could not submit your feedback.",
      );
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Share your feedback"
      description={campaignTitle}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={submit.isPending} disabled={!valid}>
            Submit feedback
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert tone="critical">{error}</Alert>}

        {!user && (
          <Alert tone="info">You will be asked to sign in before your feedback is posted.</Alert>
        )}

        <div className="space-y-1.5">
          <p className="label-text">Your rating</p>
          <StarRating value={rating} onChange={setRating} size={28} />
        </div>

        <Field
          label="What do you think?"
          htmlFor="feedback-text"
          required
          hint={`${text.trim().length}/${MAX_LENGTH} characters · minimum ${MIN_LENGTH}`}
        >
          <Textarea
            rows={5}
            maxLength={MAX_LENGTH}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="What convinced you, and what still concerns you? Specific feedback helps the creator most."
          />
        </Field>

        <p className="text-xs leading-relaxed text-ink-faint">
          Your comment is classified for sentiment and theme so the creator can see what the
          community collectively thinks. Your identity is never sent to the AI model.
        </p>
      </div>
    </Dialog>
  );
}
