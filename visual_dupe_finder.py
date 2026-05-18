"""
Visual "Dupes" Finder using OpenAI CLIP + ChromaDB.

Given a corpus of scraped products (with image URLs or local paths), this module:
  1. Extracts dense image embeddings using CLIP (ViT-B/32 from HuggingFace).
  2. Stores those embeddings in a persistent ChromaDB vector collection.
  3. Accepts a query image (e.g., a user uploads a photo of a designer bag) and
     returns the most visually similar products from the indexed corpus,
     sorted by price so the user instantly sees the cheapest "dupe".

Why CLIP?
  CLIP was trained on 400M image-text pairs and produces embeddings that capture
  semantic visual similarity (not just pixel-level difference).  "A black leather
  tote bag" from Zara and from Louis Vuitton will be nearby in CLIP space even if
  the images have different backgrounds, lighting, and aspect ratios.

Why ChromaDB?
  It's an in-process vector database with zero infrastructure setup — no Docker,
  no cloud account.  Embeddings persist to disk between runs so we only recompute
  them when new products are added.
"""

from __future__ import annotations

import io
import os
import traceback
from pathlib import Path
from typing import Any

import chromadb
import requests
import torch
from PIL import Image
from pydantic import BaseModel, Field
from transformers import CLIPModel, CLIPProcessor


# ---------------------------------------------------------------------------
# Data schemas
# ---------------------------------------------------------------------------


class ScrapedProduct(BaseModel):
    """A product as returned by the scraper, with an image source."""

    product_id: str
    title: str
    price: float = Field(..., description="Price in USD")
    # Can be a local filesystem path or an https:// URL.
    image_url_or_local_path: str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
_COLLECTION_NAME = "product_images"
_CHROMA_PERSIST_DIR = "./chroma_db"
_IMAGE_DOWNLOAD_TIMEOUT_S = 15
_MAX_IMAGE_SIZE_PX = 512  # Resize large images before CLIP to cap memory usage


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_image(source: str) -> Image.Image | None:
    """
    Load a PIL Image from either a local path or an HTTP(S) URL.

    Returns None on failure rather than raising, so the caller can skip
    individual broken products without aborting the entire indexing batch.
    """
    try:
        if source.startswith("http://") or source.startswith("https://"):
            response = requests.get(
                source,
                timeout=_IMAGE_DOWNLOAD_TIMEOUT_S,
                # Mimic a browser UA to avoid 403s from CDNs that block scripts
                headers={"User-Agent": "Mozilla/5.0 (compatible; DupeFinder/1.0)"},
            )
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content)).convert("RGB")
        else:
            path = Path(source)
            if not path.exists():
                print(f"  [warn] Local image not found: {source}")
                return None
            return Image.open(path).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] Failed to load image from {source!r}: {exc}")
        return None


def _resize_if_needed(image: Image.Image) -> Image.Image:
    """
    Downsample images that are larger than _MAX_IMAGE_SIZE_PX on the longest
    side.  CLIP's patch-based encoder doesn't benefit from very large inputs
    and smaller images speed up batched preprocessing significantly.
    """
    w, h = image.size
    longest = max(w, h)
    if longest <= _MAX_IMAGE_SIZE_PX:
        return image
    scale = _MAX_IMAGE_SIZE_PX / longest
    return image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Main finder class
# ---------------------------------------------------------------------------


class VisualDupeFinder:
    """
    Index product images with CLIP embeddings and search for visual duplicates.

    Usage:
        finder = VisualDupeFinder()
        finder.index_products(products)
        dupes = finder.find_dupes("my_dress.jpg", top_k=5)
    """

    def __init__(
        self,
        chroma_persist_dir: str = _CHROMA_PERSIST_DIR,
        model_id: str = _CLIP_MODEL_ID,
        device: str | None = None,
    ) -> None:
        """
        Load CLIP and initialise ChromaDB.

        Args:
            chroma_persist_dir: Where ChromaDB writes its on-disk index.
                                 The directory is created automatically if absent.
            model_id: HuggingFace model ID for the CLIP variant to load.
            device: "cpu" | "cuda" | "mps".  Auto-detected when None.
        """
        self.device = device or self._pick_device()
        print(f"[VisualDupeFinder] Loading CLIP ({model_id}) on {self.device}…")

        self._processor: CLIPProcessor = CLIPProcessor.from_pretrained(model_id)
        self._model: CLIPModel = CLIPModel.from_pretrained(model_id).to(self.device)
        self._model.eval()  # Disable dropout — we're doing inference only

        print(f"[VisualDupeFinder] Initialising ChromaDB at {chroma_persist_dir!r}…")
        self._chroma = chromadb.PersistentClient(path=chroma_persist_dir)
        self._collection = self._chroma.get_or_create_collection(
            name=_COLLECTION_NAME,
            # ChromaDB's default distance metric is L2; cosine works better for
            # normalised CLIP embeddings and returns 0=identical, 1=orthogonal.
            metadata={"hnsw:space": "cosine"},
        )
        print(
            f"[VisualDupeFinder] Ready.  "
            f"Collection currently holds {self._collection.count()} products."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_products(self, products: list[ScrapedProduct]) -> None:
        """
        Download/load each product's image, compute its CLIP embedding, and
        upsert it into ChromaDB.

        We upsert (not add) so re-indexing the same product IDs is idempotent —
        safe to call multiple times as the catalogue grows.

        Args:
            products: List of ScrapedProduct objects to index.
        """
        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []
        documents: list[str] = []  # ChromaDB requires a "document" string per entry

        for product in products:
            print(f"  Indexing [{product.product_id}] {product.title!r}…")
            image = _load_image(product.image_url_or_local_path)
            if image is None:
                print(f"    → Skipped (could not load image).")
                continue

            image = _resize_if_needed(image)
            embedding = self._embed_image(image)

            ids.append(product.product_id)
            embeddings.append(embedding)
            metadatas.append(
                {
                    "title": product.title,
                    "price": product.price,
                    "image_source": product.image_url_or_local_path,
                }
            )
            # The "document" field is ChromaDB's text payload — we store the
            # title so the collection is also text-searchable as a bonus.
            documents.append(product.title)

        if not ids:
            print("[index_products] No products were successfully indexed.")
            return

        # Upsert: update existing entries, insert new ones — single call
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )
        print(
            f"[index_products] Upserted {len(ids)} products. "
            f"Collection total: {self._collection.count()}."
        )

    def find_dupes(
        self, query_image_path: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """
        Find the visually most-similar products to a query image.

        Args:
            query_image_path: Local file path or URL of the query image.
            top_k: Number of candidates to retrieve from ChromaDB.

        Returns:
            List of dicts sorted by price ascending (cheapest dupe first).
            Each dict contains: product_id, title, price, image_source,
            similarity_score (0-1, higher = more similar).
        """
        if self._collection.count() == 0:
            print("[find_dupes] Collection is empty — call index_products() first.")
            return []

        query_image = _load_image(query_image_path)
        if query_image is None:
            raise ValueError(f"Could not load query image from: {query_image_path!r}")

        query_image = _resize_if_needed(query_image)
        query_embedding = self._embed_image(query_image)

        # ChromaDB cosine distance: 0 = identical, 2 = maximally dissimilar.
        # We clamp to [0, 1] and flip to a similarity score for readability.
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count()),
        )

        hits: list[dict[str, Any]] = []
        if not results["ids"] or not results["ids"][0]:
            return hits

        for pid, meta, distance in zip(
            results["ids"][0],
            results["metadatas"][0],  # type: ignore[index]
            results["distances"][0],  # type: ignore[index]
        ):
            # Convert cosine distance [0, 2] → similarity [0, 1]
            similarity = max(0.0, 1.0 - distance / 2.0)
            hits.append(
                {
                    "product_id": pid,
                    "title": meta["title"],
                    "price": meta["price"],
                    "image_source": meta["image_source"],
                    "similarity_score": round(similarity, 4),
                }
            )

        # Sort by price so the user sees the cheapest dupe at the top
        hits.sort(key=lambda h: h["price"])
        return hits

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _embed_image(self, image: Image.Image) -> list[float]:
        """
        Run the image through CLIP's vision encoder and return a normalised
        float embedding vector.

        Normalisation is important: ChromaDB's cosine similarity is only
        well-defined on unit vectors, and CLIP embeddings benefit from it.
        """
        with torch.no_grad():
            inputs = self._processor(images=image, return_tensors="pt", padding=True)
            # Move tensors to the same device as the model
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            features = self._model.get_image_features(**inputs)
            # L2-normalise so cosine similarity == dot product (faster at query time)
            features = features / features.norm(dim=-1, keepdim=True)

        # Detach from the compute graph and convert to a plain Python list
        return features.squeeze().cpu().tolist()

    @staticmethod
    def _pick_device() -> str:
        """
        Select the best available compute device.

        Preference order: CUDA GPU > Apple MPS > CPU.
        For the typical e-commerce laptop use-case this will be "cpu",
        which is fast enough for batches of ~100 product images.
        """
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"


# ---------------------------------------------------------------------------
# Dummy data + smoke test
# ---------------------------------------------------------------------------

# Public-domain placeholder images from Unsplash (no sign-in required).
# In production these would be real product image URLs from your scrapers.
_DUMMY_PRODUCTS = [
    ScrapedProduct(
        product_id="amazon-001",
        title="Classic Black Leather Tote Bag",
        price=39.99,
        image_url_or_local_path="https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=400",
    ),
    ScrapedProduct(
        product_id="bestbuy-002",
        title="Minimalist Canvas Shoulder Bag",
        price=24.95,
        image_url_or_local_path="https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=400",
    ),
    ScrapedProduct(
        product_id="walmart-003",
        title="Vegan Leather Crossbody Bag",
        price=18.49,
        image_url_or_local_path="https://images.unsplash.com/photo-1591561954557-26941169b49e?w=400",
    ),
    ScrapedProduct(
        product_id="target-004",
        title="Woven Straw Beach Bag",
        price=14.99,
        image_url_or_local_path="https://images.unsplash.com/photo-1622560480605-d83c853bc5c3?w=400",
    ),
    ScrapedProduct(
        product_id="newegg-005",
        title="Tech Backpack with USB Charging Port",
        price=49.00,
        image_url_or_local_path="https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400",
    ),
]

# We use the same "Classic Black Leather Tote" image as our query
# to verify that amazon-001 comes back as the top match.
_QUERY_IMAGE_URL = "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=400"


if __name__ == "__main__":
    print("=" * 60)
    print("Visual Dupe Finder — Demo")
    print("=" * 60)

    finder = VisualDupeFinder()

    print("\n[1/2] Indexing dummy product catalogue…")
    finder.index_products(_DUMMY_PRODUCTS)

    print("\n[2/2] Searching for dupes of query image…")
    print(f"Query: {_QUERY_IMAGE_URL}\n")

    try:
        dupes = finder.find_dupes(query_image_path=_QUERY_IMAGE_URL, top_k=5)
    except ValueError as exc:
        print(f"Error during search: {exc}")
        traceback.print_exc()
        dupes = []

    if dupes:
        print(f"Top {len(dupes)} visual dupes (sorted cheapest first):\n")
        for rank, hit in enumerate(dupes, start=1):
            print(
                f"  #{rank}  [{hit['product_id']}]  ${hit['price']:.2f}  "
                f"sim={hit['similarity_score']:.3f}  {hit['title']!r}"
            )
    else:
        print("No results returned.")
