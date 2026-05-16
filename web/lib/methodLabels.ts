/** Scrape pipeline method ids returned by the API (models.ExtractionMethod). */
export function formatScrapeMethod(method: string): string {
  if (!method || method === "N/A") return "N/A";
  return method.toLowerCase();
}

export function productLink(url: string): string | null {
  if (!url || url === "N/A" || !url.startsWith("http")) return null;
  return url;
}
