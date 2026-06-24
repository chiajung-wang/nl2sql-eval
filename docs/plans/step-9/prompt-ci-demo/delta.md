### 🧪 Prompt-CI — pass@1 / pass@k delta

⚠️ **Potential regression** — a pass rate dropped on the frozen slice.

| metric | base (`generate/v3`) | PR (`generate/_demo_regression`) | Δ |
| --- | --- | --- | --- |
| pass@1 | 0.417 (5/12) | 0.000 (0/12) | -0.417 ▼ |
| pass@k | 0.417 (5/12) | 0.000 (0/12) | -0.417 ▼ |

_Frozen slice `step9-prompt-ci` · 12 questions · model `anthropic/claude-sonnet-4-6` · k=3 · 1 question ≈ 0.083. Base `sha256:4a12c21…` → PR `sha256:99535ed…`._
