import type { DisclaimerResponse } from "@/api/types";

/**
 * Persistent notices about what this tool can and cannot tell you.
 *
 * These are deliberately unmissable. Benchmark comparison is informational:
 * being outside a range is a reason to ask the hospital a question, not proof
 * of an error.
 */
export function DisclaimerFooter({ disclaimer }: { disclaimer: DisclaimerResponse | null }) {
  return (
    <footer className="border-t border-ink-200 bg-ink-50">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <h2 className="text-sm font-semibold text-ink-900">Before you rely on this</h2>
        <div className="mt-3 grid gap-4 text-sm leading-relaxed text-ink-600 sm:grid-cols-2">
          <div>
            <p className="font-medium text-ink-800">What this is</p>
            <p className="mt-1">
              {disclaimer?.main ??
                "MedBill Lens organises the charges on your bill and compares each one against published benchmark ranges so you can see where to ask questions."}
            </p>
          </div>
          <div>
            <p className="font-medium text-ink-800">What this is not</p>
            <p className="mt-1">
              {disclaimer?.tool_notice ??
                "It is not a medical, legal or financial opinion, and it cannot tell you whether a charge is correct. Only the hospital can confirm what was actually provided."}
            </p>
          </div>
          <div>
            <p className="font-medium text-ink-800">About the benchmarks</p>
            <p className="mt-1">
              {disclaimer?.dataset_notice ??
                "Benchmark ranges come from the records listed on each analysis and may not reflect your exact hospital, city or treatment."}
            </p>
          </div>
          <div>
            <p className="font-medium text-ink-800">Your documents</p>
            <p className="mt-1">
              {disclaimer?.privacy_notice ??
                "Uploaded documents are processed to build your analysis and are not shared with third parties."}
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
