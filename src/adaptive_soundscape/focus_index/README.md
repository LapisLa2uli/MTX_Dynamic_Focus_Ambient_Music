# Focus Likelihood Index (FLI)

Privacy-first, local-only focus scoring for the Adaptive Focus Music System.

## Privacy

FLI **never** stores:

- window titles, URLs, or page content
- keystroke contents, clipboard, screenshots
- microphone or camera data

Stored signals are coarse: app **category**, durations, switch counts, idle intervals, and optional go/no-go probe aggregates.

Default retention: **7 days**. Export/delete from Settings.

This index is **non-clinical** and **non-surveillance**. It estimates likelihood of focused work from coarse behavioral proxies and can be wrong when:

- the user is thinking without input (looks idle)
- aligned tools are mis-categorized
- calibration patterns are outdated
- attention probes are skipped or stale

## Scoring

### Measured weighted sum (calibrated / full)

\[
W = 0.35 A + 0.25 S + 0.20 I + 0.20 P
\]

Missing components drop their weight; remaining weights renormalize to 1.

`measured_focus = 100 · W`

### Uncalibrated default (no user patterns yet)

Until a calibration pattern exists for the task profile, FLI uses **only** the
default 3-parameter metric — alignment **A**, switch stability **S**, and idle
quality **I** — with no probe term and no pattern similarity:

\[
W = \mathrm{renorm}(0.35 A + 0.25 S + 0.20 I)
\]

Smoothing is also lighter in this mode so the focus bar tracks live activity
more visibly. After calibration, probe (P) and pattern assist are enabled.

### Calibration-pattern similarity

During calibration, a privacy-safe feature vector is stored (category time fractions, alignment ratio, switch rate, idle metrics, optional probe score). Live windows compute cosine similarity to stored patterns for the task profile (`pattern_focus = 100 · similarity`).

### Final focus level

When calibrated, pattern may gently assist a moderate/high measured score (gated;
it cannot floor focus while measured has collapsed). When uncalibrated, focus is
measured A/S/I only.

Live scoring uses a shorter window (~180s), stronger recency (~45s), and
**asymmetric EMA** (falls faster than it rises). Settings → Concentration Threshold
maps into FLI sensitivity (switch rate / recency). Sustained low focus can auto-switch
the UI/music context to Distraction without rewriting classification events.

Result payload includes `focus_source`: `measured` | `pattern_similarity` | `tie`.

## Events

| Type | Fields (privacy-safe) |
|------|------------------------|
| `app_activity` | category, duration_s, aligned, task_profile |
| `context_switch` | from/to category, alignment flags |
| `idle_state` | duration_s, is_idle |
| `attention_probe` | accuracy, omission/commission rates, RT mean/std, optional self-rating |
| `session_config` | task_profile, probes_enabled |

## Bands

| Band | Range |
|------|-------|
| low | &lt; 40 |
| moderate | 40–60 |
| high | 60–80 |
| very_high | ≥ 80 |
| uncertain | insufficient / high-idle low-active |

## Local DB

`config/focus_index.sqlite` (gitignored).
