"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CameraOff, Image as ImageIcon, Link2, QrCode } from "lucide-react";

import { Alert, Button, Card, CardContent, Field, Input, Tabs } from "@/components/ui";
import { parseCampaignReference } from "@/lib/utils";

type Mode = "camera" | "upload" | "manual";

/**
 * QR entry point.
 *
 * Three ways in, because a demo must not depend on a working phone camera:
 * live camera, an uploaded QR image decoded in-browser, and plain URL entry.
 */
export default function ScanPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("camera");
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState("");

  const go = useCallback(
    (raw: string) => {
      const reference = parseCampaignReference(raw);
      if (!reference) {
        setError("That does not look like a CrowdWise campaign link or ID.");
        return;
      }
      router.push(`/campaign/${reference}`);
    },
    [router],
  );

  return (
    <div className="container-page py-10">
      <div className="mx-auto max-w-xl">
        <header className="mb-6 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-ink text-white">
            <QrCode className="h-6 w-6" aria-hidden />
          </span>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">Scan a campaign QR</h1>
          <p className="mt-2 text-sm text-ink-muted">
            Point your camera at a CrowdWise QR from a poster, a stall, a slide or a social post.
          </p>
        </header>

        <Card>
          <CardContent className="p-5">
            <Tabs
              tabs={[
                { id: "camera", label: "Camera" },
                { id: "upload", label: "Upload image" },
                { id: "manual", label: "Enter link" },
              ]}
              active={mode}
              onChange={(id) => {
                setMode(id as Mode);
                setError(null);
              }}
              className="mb-5"
            />

            {error && (
              <Alert tone="critical" className="mb-4">
                {error}
              </Alert>
            )}

            {mode === "camera" && <CameraScanner onResult={go} onError={setError} />}
            {mode === "upload" && <ImageScanner onResult={go} onError={setError} />}
            {mode === "manual" && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  go(manual);
                }}
                className="space-y-4"
              >
                <Field
                  label="Campaign link or ID"
                  htmlFor="manual-reference"
                  hint="For example: http://localhost:3000/campaign/CMP-101 or just CMP-101"
                >
                  <Input
                    value={manual}
                    onChange={(event) => setManual(event.target.value)}
                    placeholder="CMP-101"
                  />
                </Field>
                <Button type="submit" className="w-full" leadingIcon={<Link2 className="h-4 w-4" />}>
                  Open campaign
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <p className="mt-4 text-center text-xs text-ink-faint">
          The QR only carries a campaign link. It never holds money and never carries personal
          data.
        </p>
      </div>
    </div>
  );
}

function CameraScanner({
  onResult,
  onError,
}: {
  onResult: (value: string) => void;
  onError: (message: string | null) => void;
}) {
  const containerId = "crowdwise-qr-reader";
  const [scanning, setScanning] = useState(false);
  const scannerRef = useRef<{ stop: () => Promise<void>; clear: () => void } | null>(null);

  const stop = useCallback(async () => {
    const scanner = scannerRef.current;
    scannerRef.current = null;
    if (scanner) {
      try {
        await scanner.stop();
        scanner.clear();
      } catch {
        // The camera may already be released; nothing useful to do here.
      }
    }
    setScanning(false);
  }, []);

  useEffect(() => () => void stop(), [stop]);

  const start = async () => {
    onError(null);
    try {
      // Imported on demand so the scanner bundle never loads for users who
      // never open this tab.
      const { Html5Qrcode } = await import("html5-qrcode");
      const scanner = new Html5Qrcode(containerId);
      scannerRef.current = scanner as unknown as { stop: () => Promise<void>; clear: () => void };
      setScanning(true);
      await scanner.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 240, height: 240 } },
        (decoded: string) => {
          void stop();
          onResult(decoded);
        },
        () => {
          // Per-frame decode misses are normal; ignore them.
        },
      );
    } catch (caught) {
      setScanning(false);
      onError(
        caught instanceof Error && caught.name === "NotAllowedError"
          ? "Camera permission was denied. Use the upload or link tab instead."
          : "Could not start the camera. Use the upload or link tab instead.",
      );
    }
  };

  return (
    <div className="space-y-4">
      <div
        id={containerId}
        className="aspect-square w-full overflow-hidden rounded-lg border border-surface-border bg-surface-muted"
      >
        {!scanning && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-ink-faint">
            <CameraOff className="h-8 w-8" aria-hidden />
            <p className="text-sm">Camera is off</p>
          </div>
        )}
      </div>

      {scanning ? (
        <Button variant="outline" className="w-full" onClick={() => void stop()}>
          Stop camera
        </Button>
      ) : (
        <Button className="w-full" onClick={start} leadingIcon={<Camera className="h-4 w-4" />}>
          Start camera
        </Button>
      )}

      <p className="text-xs text-ink-muted">
        Your browser will ask for camera permission. Nothing is uploaded — decoding happens on
        your device.
      </p>
    </div>
  );
}

function ImageScanner({
  onResult,
  onError,
}: {
  onResult: (value: string) => void;
  onError: (message: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);

  const handleFile = async (file: File) => {
    onError(null);
    setBusy(true);
    try {
      const jsQR = (await import("jsqr")).default;
      const bitmap = await createImageBitmap(file);
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("canvas unavailable");
      context.drawImage(bitmap, 0, 0);
      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      const decoded = jsQR(imageData.data, imageData.width, imageData.height);
      if (!decoded?.data) {
        onError("No QR code was found in that image. Try a clearer photo.");
        return;
      }
      onResult(decoded.data);
    } catch {
      onError("Could not read that image.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-surface-border bg-surface-subtle p-10 text-center transition-colors hover:border-ink-faint">
        <ImageIcon className="h-8 w-8 text-ink-faint" aria-hidden />
        <span className="text-sm font-medium text-ink">
          {busy ? "Decoding…" : "Choose a QR image"}
        </span>
        <span className="text-xs text-ink-muted">PNG or JPEG, decoded in your browser</span>
        <input
          type="file"
          accept="image/*"
          className="sr-only"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
      </label>
      <p className="text-xs text-ink-muted">
        Useful on a laptop with no camera — screenshot the QR from a slide and drop it here.
      </p>
    </div>
  );
}
