import type { JobStatus, SearchResponse } from "@/lib/api";
import demoRun from "@/lib/demo-run.json";

/**
 * Demo mode.
 *
 * The real backend is FastAPI + Playwright running 30-90 second jobs against
 * live retailers. That cannot be hosted on serverless (no browser, request
 * duration caps, and an in-memory job store that does not survive across
 * invocations), and a public endpoint holding real API keys would let any
 * visitor spend them.
 *
 * So the deployed build replays one recorded run instead. The data below is a
 * genuine result captured from the real pipeline, not invented: the same rows,
 * prices, methods and trust labels the backend produced. What is simulated is
 * only the *timing* - the progress bar and the order stores complete in - so
 * the streaming behaviour is still visible.
 *
 * The UI states plainly that this is a recording. Nothing here should imply a
 * live scrape is happening.
 */

export const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

const RESULT = demoRun.result as unknown as SearchResponse;

/** Mirrors the real run's shape: stores land one at a time, not all at once. */
const TIMELINE: { at: number; percent: number; message: string; done: string[] }[] = [
  { at: 0, percent: 5, message: "Checking Newegg…", done: [] },
  {
    at: 2600,
    percent: 27,
    message: "Finished with Newegg — found a price.",
    done: ["Newegg"],
  },
  {
    at: 6200,
    percent: 62,
    message: "Finished with Walmart — found a price.",
    done: ["Newegg", "Walmart"],
  },
  {
    at: 10400,
    percent: 80,
    message: "Finished with Best Buy — no price found this time.",
    done: ["Newegg", "Walmart", "Best Buy"],
  },
  {
    at: 13200,
    percent: 95,
    message: "Putting your table together…",
    done: ["Newegg", "Walmart", "Best Buy", "Amazon"],
  },
  {
    at: 15000,
    percent: 100,
    message: "Done.",
    done: ["Newegg", "Walmart", "Best Buy", "Amazon"],
  },
];

const TOTAL_MS = TIMELINE[TIMELINE.length - 1].at;

/** Site order in the recorded run, so cards appear as their store finishes. */
const SITE_BY_LABEL: Record<string, string> = {
  Newegg: "Newegg.com",
  Walmart: "Walmart.com",
  "Best Buy": "BestBuy.com",
  Amazon: "Amazon.com",
};

const started = new Map<string, number>();

export function startDemoJob(): string {
  const id = `demo-${Date.now().toString(36)}`;
  started.set(id, Date.now());
  return id;
}

export function getDemoJob(jobId: string): JobStatus {
  const t0 = started.get(jobId) ?? Date.now();
  const elapsed = Date.now() - t0;

  let frame = TIMELINE[0];
  for (const f of TIMELINE) if (elapsed >= f.at) frame = f;

  const finished = elapsed >= TOTAL_MS;

  // Only reveal rows whose store has completed, so the table fills in the way
  // it does against the real backend.
  const revealed = new Set(frame.done.map((d) => SITE_BY_LABEL[d]));
  const rows = RESULT.rows.filter((r) => revealed.has(r.website));

  const partial: SearchResponse = {
    ...RESULT,
    rows,
    success_count: rows.filter((r) => r.has_price).length,
  };

  return {
    job_id: jobId,
    query: demoRun.query,
    status: finished ? "done" : "running",
    progress: {
      percent: frame.percent,
      message: frame.message,
      stores_done: frame.done,
      stores_total: RESULT.total_sites,
    },
    result: finished ? RESULT : partial,
    error: null,
  };
}

/** The query the recording was made with, shown as the field's placeholder. */
export const DEMO_QUERY = demoRun.query;
