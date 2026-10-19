"""Shared constants for trigram-based category matching.

``SIMILARITY_THRESHOLD`` is the pg_trgm floor ``CategoryRepository.find_similar_active``
is called with. The store-name heuristic that used to live here (trigram on the
extractor's category label, then the most-used category of the last 90 days) was
retired when receipts moved to the decision-model classifier in
``app.services.category_classifier``, which is now the single categorization path for
both manual entry and scanned receipts.
"""

# pg_trgm similarity floor. Below this, a "match" is noise.
SIMILARITY_THRESHOLD = 0.3
