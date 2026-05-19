"""Plain-language progress labels for the web UI."""

from __future__ import annotations

FRIENDLY_STORE: dict[str, str] = {
    "Amazon.com": "Amazon",
    "Walmart.com": "Walmart",
    "BestBuy.com": "Best Buy",
    "Newegg.com": "Newegg",
}


def friendly_store(website: str) -> str:
    return FRIENDLY_STORE.get(website, website.replace(".com", ""))


def message_site_started(website: str) -> str:
    return f"Checking {friendly_store(website)}…"


def message_all_stores_started() -> str:
    return "Checking prices on Amazon, Walmart, Best Buy, and Newegg…"


def message_store_finished(website: str, *, got_price: bool) -> str:
    name = friendly_store(website)
    if got_price:
        return f"Finished with {name} — found a price."
    return f"Finished with {name} — no price found this time."


def message_recheck_start(stores: list[str]) -> str:
    names = ", ".join(friendly_store(s) for s in stores)
    return f"Some prices look very different. Checking again: {names}."


def message_recheck_store(website: str) -> str:
    return f"Checking {friendly_store(website)} again…"


def message_done(success_count: int, total: int) -> str:
    if success_count == 0:
        return "Search finished, but we couldn't find prices on any store."
    if success_count == total:
        return "All done! Here is your comparison."
    return f"All done! We found prices on {success_count} of {total} stores."


def message_starting() -> str:
    return "Starting your search…"


def message_wrapping_up() -> str:
    return "Putting your table together…"
