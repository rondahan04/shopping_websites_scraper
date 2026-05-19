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

export type SearchResponse = {
  query: string;
  rows: ProductRow[];
  success_count: number;
  total_sites: number;
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
