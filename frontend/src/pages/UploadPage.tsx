/**
 * Drag-and-drop / file-picker upload.
 *
 * File type and size are checked in the browser for fast feedback, but the
 * server re-sniffs content and is the only authority: a renamed `.txt` is
 * rejected regardless of what this component allows.
 */

import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, ImageIcon, ShieldCheck, Trash2, UploadCloud } from "lucide-react";

import { api } from "@/api/client";
import { Spinner } from "@/components/Feedback";
import { ErrorNotice, Notice } from "@/components/Notice";
import { useAppMeta } from "@/state/AppMeta";
import { useBillSession } from "@/state/BillSession";
import { formatFileSize } from "@/lib/format";

const ACCEPTED = ".pdf,.jpg,.jpeg,.png";

export default function UploadPage() {
  const navigate = useNavigate();
  const { health } = useAppMeta();
  const { remember } = useBillSession();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const maxBytes = (health?.max_upload_size_mb ?? 10) * 1024 * 1024;

  const accept = useCallback(
    (candidate: File | null) => {
      if (!candidate) return;
      setError(null);
      setLocalError(null);

      const extension = candidate.name.split(".").pop()?.toLowerCase() ?? "";
      if (!["pdf", "jpg", "jpeg", "png"].includes(extension)) {
        setLocalError(
          `We can only read PDF, JPG and PNG files. "${candidate.name}" is a .${extension} file.`,
        );
        return;
      }
      if (candidate.size > maxBytes) {
        setLocalError(
          `That file is ${formatFileSize(candidate.size)}. The limit is ${formatFileSize(maxBytes)}.`,
        );
        return;
      }
      if (candidate.size === 0) {
        setLocalError("That file is empty.");
        return;
      }
      setFile(candidate);
    },
    [maxBytes],
  );

  const submit = useCallback(async () => {
    if (!file) return;
    setPending(true);
    setError(null);
    setLocalError(null);
    try {
      const response = await api.uploadBill(file);
      remember(response.bill.id);
      // Upload returns an `uploaded` bill; extraction is a separate step so a
      // failure there can be retried without re-uploading the file.
      await api.extractBill(response.bill.id);
      navigate(`/bills/${response.bill.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setPending(false);
    }
  }, [file, navigate, remember]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
      <h1 className="text-3xl font-semibold tracking-tight text-ink-900">Upload your bill</h1>
      <p className="mt-2 text-ink-600">
        A scanned PDF or a clear photo of the itemised bill works best. We will show you
        everything we read before comparing anything.
      </p>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          accept(event.dataTransfer.files?.[0] ?? null);
        }}
        className={`mt-8 rounded-xl border-2 border-dashed p-8 text-center transition-all duration-200 ${
          dragging
            ? "scale-[1.01] border-brand-500 bg-brand-50 anim-ring"
            : "border-ink-300 bg-white"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="sr-only"
          onChange={(event) => {
            accept(event.target.files?.[0] ?? null);
            // Allow re-selecting the same file after a failure.
            event.target.value = "";
          }}
        />

        {file ? (
          <div className="anim-pop flex items-center justify-center gap-4">
            <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
              {file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf") ? (
                <FileText className="h-6 w-6" aria-hidden="true" />
              ) : (
                <ImageIcon className="h-6 w-6" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0 text-left">
              <p className="truncate text-sm font-semibold text-ink-900">{file.name}</p>
              <p className="tnum text-xs text-ink-500">{formatFileSize(file.size)}</p>
            </div>
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={() => setFile(null)}
              disabled={pending}
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              Remove
            </button>
          </div>
        ) : (
          <>
            <UploadCloud className="mx-auto h-10 w-10 text-ink-400" aria-hidden="true" />
            <p className="mt-3 text-sm font-medium text-ink-800">
              Drag your bill here, or choose a file
            </p>
            <button
              type="button"
              className="btn-secondary btn-sm mt-4"
              onClick={() => inputRef.current?.click()}
            >
              Choose file
            </button>
            <p className="mt-3 text-xs text-ink-500">
              PDF, JPG or PNG up to {formatFileSize(maxBytes)}
            </p>
          </>
        )}
      </div>

      {localError ? (
        <Notice tone="error" className="mt-4">
          {localError}
        </Notice>
      ) : null}

      {error ? <ErrorNotice error={error} className="mt-4" /> : null}

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          type="button"
          className="btn-primary"
          onClick={submit}
          disabled={!file || pending}
        >
          {pending ? <Spinner /> : null}
          {pending ? "Reading your bill" : "Read this bill"}
        </button>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => navigate("/review")}
          disabled={pending}
        >
          Enter charges manually instead
        </button>
      </div>

      {pending ? (
        <div className="anim-fade mt-4" role="status" aria-live="polite">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-200">
            <div className="h-full w-1/3 rounded-full bg-brand-600 progress-fill" />
          </div>
          <div className="mt-3">
            <Notice tone="info" title="Reading the charges">
              We are extracting the line items and totals. Scanned documents can take a moment.
            </Notice>
          </div>
        </div>
      ) : null}

      <div className="mt-10 rounded-xl bg-ink-100/70 p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink-900">
          <ShieldCheck className="h-4 w-4 text-ink-600" aria-hidden="true" />
          How your document is handled
        </h2>
        <ul className="stagger mt-3 space-y-2 text-sm leading-relaxed text-ink-600">
          <li>
            The file is used to build your bill, then deleted automatically after the configured
            retention window{health ? ` (${health.raw_file_retention_minutes} minutes)` : ""}. It is
            never served back over the web and is not shared with third parties.
          </li>
          <li>
            Nothing is compared until you have reviewed the extracted charges and confirmed them.
          </li>
          <li>
            Prefer not to upload anything? Manual entry produces exactly the same analysis.
          </li>
        </ul>
      </div>
    </div>
  );
}
