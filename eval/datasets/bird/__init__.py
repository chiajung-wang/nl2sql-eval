"""BIRD benchmark loader/adapter — the quantitative backbone.

``loader`` loads the questions and opens each tagged SQLite db read-only
(file-per-db; single-db per run). ``slice`` selects the frozen, seeded,
stratified small-schema evaluation slice, whose ID list is checked in here as
``slice_step3.json`` (the benchmark data itself is downloaded separately and
gitignored). The full-schema / larger-slice path lands at Step 6 with retrieval.
"""
