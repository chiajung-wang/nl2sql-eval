"""Profiling-derived field metadata (Step 12, #140) — offline unit coverage.

The deterministic half of the paper's metadata lever (arXiv:2505.19988v2 §2.1) is
fully offline and proven here: the profiler's per-column statistics, the mechanical
English rendering, the version-controlled cache round-trip, the metadata-source
selector (supplied / profiling / fused), and the summarizer with an injected fake
client. No network, no key — the live summarization refresh + the A/B are deferred.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from nl2sql.llm.client import LLMResponse
from nl2sql.profiling import (
    CharClass,
    FieldDescription,
    MetadataSource,
    active_metadata_source,
    load_field_descriptions,
    profile_db,
    render_column_english,
    render_table_english,
    resolve_column_descriptions,
    save_field_descriptions,
    select_descriptions,
)
from nl2sql.profiling.profiler import profile_column
from nl2sql.profiling.summarize import _parse_summary, summarize_column, summarize_db
from nl2sql.schema_index import build_schema_index


@pytest.fixture
def profiled_engine():
    """A small db with deliberately shaped columns: a fixed-width digit id, a
    'YYYY-YYYY' code, an enum, a nullable numeric, and a free-text column."""
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE schools (cds TEXT, year TEXT, status TEXT, "
                "enrollment INTEGER, note TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO schools VALUES "
                "('01100170000001','2013-2014','open',420,'ok'), "
                "('01100170000002','2013-2014','open',530,NULL), "
                "('01100170000003','2014-2015','closed',NULL,'a longer note here')"
            )
        )
    return engine


# --- profiler ---------------------------------------------------------------


def test_profiler_records_counts_nulls_and_distinct(profiled_engine):
    prof = profile_db(profiled_engine, "schools_db")
    cols = {c.name: c for c in prof.tables[0].columns}
    assert prof.tables[0].row_count == 3
    assert cols["enrollment"].non_null_count == 2
    assert cols["enrollment"].null_count == 1
    assert cols["enrollment"].null_fraction == pytest.approx(1 / 3)
    assert cols["status"].distinct_count == 2  # open, closed


def test_profiler_detects_fixed_width_digit_id(profiled_engine):
    cds = {c.name: c for c in profile_db(profiled_engine, "d").tables[0].columns}["cds"]
    assert cds.char_class is CharClass.DIGITS
    assert cds.is_constant_length and cds.min_len == 14
    assert cds.is_unique  # a candidate key
    assert cds.common_prefix == "0110017000000"


def test_profiler_detects_year_shape_and_enum(profiled_engine):
    cols = {c.name: c for c in profile_db(profiled_engine, "d").tables[0].columns}
    assert cols["year"].char_class is CharClass.MIXED  # the dash
    assert cols["year"].is_constant_length and cols["year"].min_len == 9
    # status is a low-cardinality enum: top_values carries the value/count signal.
    top = dict(cols["status"].top_values)
    assert top == {"open": 2, "closed": 1}
    assert not cols["status"].is_unique


def test_profiler_value_and_length_ranges(profiled_engine):
    cols = {c.name: c for c in profile_db(profiled_engine, "d").tables[0].columns}
    enrollment = cols["enrollment"]
    assert enrollment.min_value == "420" and enrollment.max_value == "530"
    assert cols["note"].min_len == 2
    assert cols["note"].max_len == len("a longer note here")


def test_profiler_handles_empty_table():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (a INTEGER, b TEXT)"))
    prof = profile_db(engine, "empty")
    col = prof.tables[0].columns[0]
    assert prof.tables[0].row_count == 0
    assert col.non_null_count == 0 and col.char_class is CharClass.EMPTY
    assert col.min_value is None and not col.is_unique


def test_profiler_handles_all_null_column():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (a INTEGER)"))
        conn.execute(text("INSERT INTO t VALUES (NULL), (NULL)"))
    col = profile_db(engine, "d").tables[0].columns[0]
    assert col.row_count == 2 and col.non_null_count == 0
    assert col.null_fraction == 1.0 and col.char_class is CharClass.EMPTY


# --- PII redaction: shape-only profile for policy columns -------------------


def test_redacted_column_suppresses_raw_values(profiled_engine):
    # A PII column keeps shape-only stats but never a raw value.
    prof = profile_db(profiled_engine, "d", redact_columns=frozenset({"schools.cds"}))
    cols = {c.name: c for c in prof.tables[0].columns}
    cds = cols["cds"]
    # Shape-only stats survive (no value revealed).
    assert cds.non_null_count == 3 and cds.distinct_count == 3
    assert cds.char_class is CharClass.DIGITS and cds.is_constant_length
    # Value-bearing fields are suppressed.
    assert cds.min_value is None and cds.max_value is None
    assert cds.common_prefix == "" and cds.top_values == ()
    # A non-redacted column in the same table is unaffected.
    assert cols["status"].top_values  # still carries its enum values


def test_redacted_column_english_leaks_no_value(profiled_engine):
    prof = profile_db(profiled_engine, "d", redact_columns=frozenset({"schools.cds"}))
    cds = {c.name: c for c in prof.tables[0].columns}["cds"]
    english = render_column_english(cds)
    assert "01100170000001" not in english  # no raw value
    assert "0110017000000" not in english  # not even the common prefix
    assert "all digits" in english  # shape still described


def test_profile_column_redact_flag_is_a_noop_off(profiled_engine):
    # The default (redact=False) is unchanged behaviour — values present.
    with profiled_engine.connect() as conn:
        col = profile_column(conn, "schools", "cds", "TEXT", 3)
    assert col.min_value is not None and col.common_prefix


# --- mechanical English renderer -------------------------------------------


def test_render_english_surfaces_the_id_format(profiled_engine):
    cds = {c.name: c for c in profile_db(profiled_engine, "d").tables[0].columns}["cds"]
    english = render_column_english(cds)
    assert "exactly 14 characters long" in english
    assert "all digits" in english
    assert "unique" in english
    assert 'beginning with "0110017000000"' in english


def test_render_english_reports_nulls_and_enum(profiled_engine):
    cols = {c.name: c for c in profile_db(profiled_engine, "d").tables[0].columns}
    assert "33%" in render_column_english(cols["enrollment"])  # 1/3 null
    status_en = render_column_english(cols["status"])
    assert "Most common:" in status_en and '"open" (2)' in status_en


def test_render_english_is_deterministic(profiled_engine):
    col = profile_db(profiled_engine, "d").tables[0].columns[0]
    assert render_column_english(col) == render_column_english(col)


def test_render_table_english_has_header_and_a_line_per_column(profiled_engine):
    table_en = render_table_english(profile_db(profiled_engine, "d").tables[0])
    assert table_en.startswith('Table "schools" (3 rows):')
    assert table_en.count("\n- Column") == 5  # one bullet per column


def test_render_english_empty_table_is_short():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (a INTEGER)"))
    en = render_column_english(profile_db(engine, "d").tables[0].columns[0])
    assert "table is empty" in en.lower()


# --- cache round-trip -------------------------------------------------------


def test_cache_save_load_roundtrip(tmp_path: Path):
    descs = {
        "schools.cds": FieldDescription(short="school code", long="A 14-char id."),
        "schools.year": FieldDescription(short="academic year", long="'YYYY-YYYY'."),
    }
    save_field_descriptions("d", descs, profiles_dir=tmp_path, generated_by="test")
    assert load_field_descriptions("d", profiles_dir=tmp_path) == descs


def test_cache_missing_file_is_empty_not_error(tmp_path: Path):
    # A db with no artifact degrades to supplied-only, never raises.
    assert load_field_descriptions("nope", profiles_dir=tmp_path) == {}


def test_cache_keys_are_sorted_on_disk(tmp_path: Path):
    descs = {
        "z.c": FieldDescription(long="z"),
        "a.c": FieldDescription(long="a"),
    }
    path = save_field_descriptions("d", descs, profiles_dir=tmp_path)
    body = path.read_text()
    assert body.index('"a.c"') < body.index('"z.c"')  # sorted → minimal diffs


# --- metadata-source selector ----------------------------------------------


def test_select_supplied_returns_supplied_only():
    out = select_descriptions(
        MetadataSource.SUPPLIED,
        supplied={"t.a": "human note"},
        profiling={"t.a": FieldDescription(long="profiled")},
    )
    assert out == {"t.a": "human note"}


def test_select_profiling_returns_profiling_only():
    out = select_descriptions(
        MetadataSource.PROFILING,
        supplied={"t.a": "human note"},
        profiling={"t.a": FieldDescription(long="profiled note")},
    )
    assert out == {"t.a": "profiled note"}


def test_select_fused_combines_both_when_they_differ():
    out = select_descriptions(
        MetadataSource.FUSED,
        supplied={"t.a": "human note", "t.b": "only supplied"},
        profiling={
            "t.a": FieldDescription(long="profiled note"),
            "t.c": FieldDescription(long="only profiled"),
        },
    )
    assert out["t.a"] == "human note profiled note"  # both, combined
    assert out["t.b"] == "only supplied"  # supplied-only key kept
    assert out["t.c"] == "only profiled"  # profiling-only key kept


def test_select_short_vs_long():
    profiling = {"t.a": FieldDescription(short="terse", long="the long one")}
    long_out = select_descriptions(MetadataSource.PROFILING, profiling=profiling)
    short_out = select_descriptions(
        MetadataSource.PROFILING, profiling=profiling, use_long=False
    )
    assert long_out["t.a"] == "the long one"
    assert short_out["t.a"] == "terse"


def test_active_metadata_source_env(monkeypatch):
    monkeypatch.delenv("METADATA_SOURCE", raising=False)
    assert active_metadata_source() is MetadataSource.SUPPLIED  # default
    monkeypatch.setenv("METADATA_SOURCE", "fused")
    assert active_metadata_source() is MetadataSource.FUSED
    monkeypatch.setenv("METADATA_SOURCE", "bogus")  # typo → default, no crash
    assert active_metadata_source() is MetadataSource.SUPPLIED


def test_resolve_column_descriptions_end_to_end(tmp_path: Path):
    save_field_descriptions(
        "d",
        {"t.a": FieldDescription(long="profiled a")},
        profiles_dir=tmp_path,
    )
    out = resolve_column_descriptions(
        "d", MetadataSource.PROFILING, profiles_dir=tmp_path
    )
    assert out == {"t.a": "profiled a"}


# --- selector wired into the schema render ---------------------------------


def test_column_descriptions_ride_into_the_rendered_schema(profiled_engine):
    idx = build_schema_index(
        profiled_engine,
        column_descriptions={"schools.cds": "A 14-char school identifier."},
    )
    rendered = idx.render(["schools"])
    assert "-- A 14-char school identifier." in rendered
    # Leading comment (not trailing) keeps the column comma intact.
    assert "-- A 14-char school identifier.\n  cds TEXT" in rendered


def test_no_descriptions_leaves_render_unchanged(profiled_engine):
    with_none = build_schema_index(profiled_engine).render(["schools"])
    assert "--" in with_none  # sample-value comments still present
    assert "-- A 14-char" not in with_none


# --- summarizer (fake client) ----------------------------------------------


class _FakeClient:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self.reply, input_tokens=10, output_tokens=8)


def test_summarize_column_parses_json(profiled_engine):
    col = profile_db(profiled_engine, "d").tables[0].columns[0]
    client = _FakeClient('{"short": "school code", "long": "A 14-char id."}')
    out = summarize_column(client, "d", col, model="fake")
    assert out.short == "school code" and out.long == "A 14-char id."
    assert client.calls == 1


def test_summarize_parses_json_wrapped_in_fence_and_prose():
    out = _parse_summary(
        'Here you go:\n```json\n{"short": "s", "long": "l"}\n```',
        fallback_long="ENGLISH",
    )
    assert out.short == "s" and out.long == "l"


def test_summarize_malformed_reply_degrades_to_english():
    out = _parse_summary("not json at all", fallback_long="the deterministic english")
    assert out.short == "" and out.long == "the deterministic english"


def test_summarize_db_keys_every_column(profiled_engine):
    prof = profile_db(profiled_engine, "d")
    client = _FakeClient('{"short": "x", "long": "y"}')
    out = summarize_db(client, prof, model="fake")
    assert set(out) == {
        "schools.cds",
        "schools.year",
        "schools.status",
        "schools.enrollment",
        "schools.note",
    }
    assert client.calls == 5  # one call per column
