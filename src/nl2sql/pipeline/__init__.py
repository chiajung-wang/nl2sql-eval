"""The instrumented NL-to-SQL pipeline (the system-under-test).

One module per stage: retrieve → generate → guard → execute → correct → redact,
wired by ``graph``. Stages are never collapsed into one file. This pipeline is
import-shared by ``eval.harness`` and ``apps.demo`` — never forked for the demo.
"""
