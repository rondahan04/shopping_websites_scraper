export type ProductRow = {
  website: string;
  product_title: string;
  price: string;
  average_rating: string;
  review_count: string;
  status: string;
  method: string;
  source_url: string;
  has_price: boolean;
  trust_label: string;
  trust_reason: string;
};

/** An LLM-backed check that did not run for this result. */
export type SkippedCheck = {
  component: string;
  consequence: string;
  cause: string;
};

export type SearchResponse = {
  query: string;
  rows: ProductRow[];
  success_count: number;
  total_sites: number;
  // Optional: older backends and the recorded demo fixture omit it. Every LLM
  // check in the pipeline fails open, so without this the UI would present a
  // run with no verification exactly like a fully verified one.
  checks_skipped?: SkippedCheck[];
};

export type JobProgress = {
  percent: number;
  message: string;
  stores_done: string[];
  stores_total: number;
};

export type JobStatus = {
  job_id: string;
  query: string;
  status: "running" | "done" | "error";
  progress: JobProgress;
  result: SearchResponse | null;
  error: string | null;
};

export async function startSearchJob(
  query: string,
  signal?: AbortSignal,
): Promise<string> {
  // Demo build: no backend exists, so replay the recorded run. Imported
  // lazily so the fixture is never pulled into a normal build.
  if (process.env.NEXT_PUBLIC_DEMO === "1") {
    const { startDemoJob } = await import("@/lib/demo");
    return startDemoJob();
  }

  const res = await fetch("/api/search/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, rescrape_price_gaps: true }),
    signal,
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  const data = (await res.json()) as { job_id: string };
  return data.job_id;
}

export async function getSearchJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<JobStatus> {
  if (process.env.NEXT_PUBLIC_DEMO === "1") {
    const { getDemoJob } = await import("@/lib/demo");
    return getDemoJob(jobId);
  }

  const res = await fetch(`/api/search/jobs/${jobId}`, { signal });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  return res.json() as Promise<JobStatus>;
}

async function readErrorMessage(res: Response): Promise<string> {
  let detail = "Something went wrong. Please try again.";
  try {
    const body = (await res.json()) as { detail?: string };
    if (body.detail) detail = body.detail;
  } catch {
    /* ignore */
  }
  return detail;
}
