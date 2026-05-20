"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { WaitGame } from "@/components/WaitGame";
import { MatrixBackground } from "@/components/MatrixBackground";
import { ScrapeGoatLogo } from "@/components/ScrapeGoatLogo";
import {
  getSearchJob,
  startSearchJob,
  type JobStatus,
  type ProductRow,
  type SearchResponse,
} from "@/lib/api";
import { formatScrapeMethod, productLink } from "@/lib/methodLabels";

const TRUST_PILL_CLASS: Record<string, string> = {
  High: "trust-pill trust-pill-high",
  Medium: "trust-pill trust-pill-medium",
  Low: "trust-pill trust-pill-low",
  Unknown: "trust-pill trust-pill-unknown",
};

const TRUST_DOT: Record<string, string> = {
  High: "●", Medium: "●", Low: "●", Unknown: "○",
};

function renderStars(rating: string): string {
  const n = parseFloat(rating);
  if (isNaN(n)) return "";
  const full = Math.round(n);
  return "★".repeat(full) + "☆".repeat(Math.max(0, 5 - full));
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
          Done so far: {progress.stores_done.join(", ")}
        </p>
      )}
    </div>
  );
}

type SortKey = "price" | "average_rating" | "review_count";
type SortDir = "asc" | "desc";

function parseNumeric(val: string): number | null {
  if (val === "N/A") return null;
  const n = parseFloat(val.replace(/[$,]/g, ""));
  return isNaN(n) ? null : n;
}

function ResultsCards({
  data,
  inProgress = false,
  storesDone = 0,
}: {
  data: SearchResponse;
  inProgress?: boolean;
  storesDone?: number;
}) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const rows = sortKey
    ? [...data.rows].sort((a, b) => {
        const av = parseNumeric(a[sortKey] as string);
        const bv = parseNumeric(b[sortKey] as string);
        if (av === null && bv === null) return 0;
        if (av === null) return 1;
        if (bv === null) return -1;
        return sortDir === "asc" ? av - bv : bv - av;
      })
    : data.rows;

  const SORT_OPTIONS: { key: SortKey; label: string }[] = [
    { key: "price", label: "Price" },
    { key: "average_rating", label: "Rating" },
    { key: "review_count", label: "Reviews" },
  ];

  return (
    <section className="results" aria-live="polite">
      <div className="results-header">
        <h2>Results for &ldquo;{data.query}&rdquo;</h2>
        <p className="results-meta">
          {inProgress ? (
            <>
              Showing {data.rows.length} of {data.total_sites} stores so far
              {data.success_count > 0 && ` · ${data.success_count} with prices`}
              . Still checking…
            </>
          ) : (
            <>Found prices on {data.success_count} of {data.total_sites} stores</>
          )}
        </p>
        {inProgress && storesDone > 0 && (
          <p className="results-partial-note">
            Cards appear as each store finishes — no need to wait for all four.
          </p>
        )}
      </div>

      <div className="sort-controls">
        <span className="sort-label">// sort by:</span>
        {SORT_OPTIONS.map(({ key, label }) => {
          const active = sortKey === key;
          return (
            <button
              key={key}
              className={`sort-btn${active ? " active" : ""}`}
              onClick={() => handleSort(key)}
            >
              {label} {active ? (sortDir === "asc" ? "▲" : "▼") : ""}
            </button>
          );
        })}
        {sortKey && (
          <button className="sort-btn" onClick={() => setSortKey(null)}>
            clear
          </button>
        )}
      </div>

      <div className="results-cards">
        {rows.map((row) => {
          const href = productLink(row.source_url);
          const ok = row.status === "Success" && row.has_price;
          const label = row.trust_label || "Unknown";
          const pillClass = TRUST_PILL_CLASS[label] ?? TRUST_PILL_CLASS.Unknown;
          const dot = TRUST_DOT[label] ?? "○";
          const stars = renderStars(row.average_rating);

          return (
            <div key={row.website} className="result-card">
              <div className="result-card-top">
                <span className="result-card-store">{row.website}</span>
                <span className={`result-card-status ${ok ? "ok" : "fail"}`}>
                  {ok ? "found" : "missing"}
                </span>
              </div>

              <div className={`result-card-price${row.price === "N/A" ? " na" : ""}`}>
                {row.price === "N/A" ? "No price" : row.price}
              </div>

              <div className="result-card-title">
                {row.product_title === "N/A" ? "Product not found" : row.product_title}
              </div>

              <div className="result-card-meta">
                {stars && (
                  <span className="result-card-stars" aria-hidden>{stars}</span>
                )}
                {row.average_rating !== "N/A" && (
                  <span className="result-card-rating">{row.average_rating}</span>
                )}
                {row.review_count !== "N/A" && (
                  <span className="result-card-reviews">({row.review_count})</span>
                )}
                {row.average_rating === "N/A" && (
                  <span className="na" style={{ fontSize: "0.78rem" }}>No ratings</span>
                )}
              </div>

              <div className="result-card-footer">
                <span className={pillClass} title={row.trust_reason || undefined}>
                  {dot} {label}
                </span>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                  <span className="result-card-method">{formatScrapeMethod(row.method)}</span>
                  {href ? (
                    <a className="result-card-link" href={href} target="_blank" rel="noopener noreferrer">
                      View →
                    </a>
                  ) : (
                    <span className="na" style={{ fontSize: "0.78rem" }}>No link</span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
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

          if (status.result && status.result.rows.length > 0) {
            setResult(status.result);
          }

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
    <>
    <MatrixBackground />
    <main>
      <header className="site-header">
        <ScrapeGoatLogo size={56} />
        <div className="site-header-text">
          <div className="terminal-bar">
            <span className="terminal-dot dot-red" aria-hidden />
            <span className="terminal-dot dot-yellow" aria-hidden />
            <span className="terminal-dot dot-green" aria-hidden />
            <span className="terminal-session">scrapegoat — session active</span>
          </div>
          <h1 className="brand-title">ScrapeGoat</h1>
          <p className="brand-tagline">
            <span className="comment-slash">// </span>
            one search, four big stores — live prices, ratings &amp; reviews
          </p>
        </div>
      </header>

      <section className="card">
        <form className="search-form" onSubmit={onSubmit}>
          <label htmlFor="product-query">
            <span className="search-label-text">// what are you comparing?</span>
            <div className="search-input-wrap">
              <span className="search-prefix" aria-hidden>$</span>
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
            </div>
          </label>
          <button type="submit" disabled={loading || !query.trim()} className="scan-btn">
            {loading ? (
              <span>&gt;_ scanning<span className="scan-ellipsis">...</span></span>
            ) : (
              <span>&gt;_ scan</span>
            )}
          </button>
        </form>

        {loading && (
          <>
            {job && <ProgressPanel job={job} />}
            {!job && (
              <div className="status-bar" role="status">
                Getting ready…
              </div>
            )}
            <WaitGame />
          </>
        )}

        {error && (
          <div className="status-bar error" role="alert">
            {error}
          </div>
        )}
      </section>

      {result && result.rows.length > 0 && (
        <ResultsCards
          data={result}
          inProgress={loading}
          storesDone={job?.progress.stores_done.length ?? result.rows.length}
        />
      )}

      <footer>
        ScrapeGoat checks Amazon, Walmart, Best Buy, and Newegg when you search.
      </footer>
    </main>
    </>
  );
}
