# Paper (`paper/`)

MTX复试任务报告 LaTeX sources.

## Build

Requires **XeLaTeX** and **Biber** (MiKTeX or TeX Live). On Windows with `ctex`, use the `windows` font set (configured in `main.tex`).

```bash
cd paper
xelatex main.tex
biber main
xelatex main.tex
xelatex main.tex
```

## Assets in this folder

| File | Purpose |
|------|---------|
| `main.tex` | Main report |
| `ref.bib` | Bibliography |
| `Focus Music Requirements.pdf` | Appendix (optional; compile succeeds without it) |

**Note:** The MindMelody flowchart is drawn inline with TikZ (no external image required). Place `Focus Music Requirements.pdf` in `paper/` to include the appendix PDF.

## Sync with codebase

When changing implementation details (audio backend, architecture, config, symbols), update `paper/main.tex` section **2.2** to match. See `.cursor/rules/paper-sync.mdc`.
