"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  getSearchJob,
  startSearchJob,
  type JobStatus,
  type ProductRow,
  type SearchResponse,
} from "@/lib/api";

function StatusBadge({ row }: { row: ProductRow }) {
  const ok = row.status === "Success" && row.has_price;
  return (
    <span className={`badge ${ok ? "ok" : "fail"}`}>
      {ok ? "found" : "missing"}
    </span>
  );
}

function ProgressPanel({ job }: { job: JobStatus }) {
  const { progress } = job;
  return (
    <div className="progress-panel" role="status" aria-live="polite">
      <div className="progress-label">
        <span>{progress.message}</span>
        <span className="progress-percent">{progress.percent}%</span>
      </div>
      <div
        className="progress-track"
        aria-valuenow={progress.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        role="progressbar"
        aria-label="Search progress"
      >
        <div
          className="progress-fill"
          style={{ width: `${progress.percent}%` }}
        />
      </div>
      {progress.stores_done.length > 0 && (
        <p className="progress-stores">
          Finished: {progress.stores_done.join(", ")}
        </p>
      )}
    </div>
  );
}

function ResultsTable({ data }: { data: SearchResponse }) {
  return (
    <section className="results" aria-live="polite">
      <div className="results-header">
        <h2>Results for &ldquo;{data.query}&rdquo;</h2>
        <p className="results-meta">
          Found prices on {data.success_count} of {data.total_sites} stores
        </p>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Website</th>
              <th scope="col">Product title</th>
              <th scope="col">Price</th>
              <th scope="col">Average rating</th>
              <th scope="col">Review count</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.website}>
                <td className="site-name">
                  {row.website}
                  <StatusBadge row={row} />
                </td>
                <td className="title-cell">
                  {row.product_title === "N/A" ? (
                    <span className="na">Not available</span>
                  ) : (
                    row.product_title
                  )}
                </td>
                <td className="price">
                  {row.price === "N/A" ? (
                    <span className="na">Not available</span>
                  ) : (
                    row.price
                  )}
                </td>
                <td>
                  {row.average_rating === "N/A" ? (
                    <span className="na">Not available</span>
                  ) : (
                    row.average_rating
                  )}
                </td>
                <td>
                  {row.review_count === "N/A" ? (
                    <span className="na">Not available</span>
                  ) : (
                    row.review_count
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const onSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      const q = query.trim();
      if (!q) return;

      abortRef.current?.abort();
      stopPolling();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);
      setResult(null);
      setJob(null);

      try {
        const jobId = await startSearchJob(q, controller.signal);

        const poll = async () => {
          if (controller.signal.aborted) return;
          const status = await getSearchJob(jobId, controller.signal);
          setJob(status);

          if (status.status === "done" && status.result) {
            setResult(status.result);
            setLoading(false);
            stopPolling();
          } else if (status.status === "error") {
            setError(
              status.error ??
                "Something went wrong while searching. Please try again.",
            );
            setLoading(false);
            stopPolling();
          }
        };

        await poll();
        pollRef.current = setInterval(poll, 800);
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong. Please try again.",
        );
        setLoading(false);
        stopPolling();
      }
    },
    [query, stopPolling],
  );

  return (
    <main>
      <header>
        <h1>Multi-store price compare</h1>
        <p className="lead">
          Type a product name and we will check Amazon, Walmart, Best Buy, and
          Newegg for you. This usually takes a few minutes — you can watch the
          progress bar below.
        </p>
      </header>

      <section className="card">
        <form className="search-form" onSubmit={onSubmit}>
          <label htmlFor="product-query">
            What are you looking for?
            <input
              id="product-query"
              name="query"
              type="search"
              placeholder="e.g. Bose QC Ultra headphones"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={loading}
              autoComplete="off"
              required
            />
          </label>
          <button type="submit" disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Compare prices"}
          </button>
        </form>

        {loading && job && <ProgressPanel job={job} />}

        {loading && !job && (
          <div className="status-bar loading" role="status">
            Getting ready…
          </div>
        )}

        {error && (
          <div className="status-bar error" role="alert">
            {error}
          </div>
        )}
      </section>

      {result && <ResultsTable data={result} />}

      <footer>
        Prices are fetched live from each store when you search.
      </footer>
    </main>
  );
}
