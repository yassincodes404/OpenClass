# Portal Visual Experience — Evidence & Capture Manifest

This directory preserves separate visual evidence across three distinct checkpoints of the OpenClass Portal visual-experience workstream (`abdelhamid-khaled/feat/cohesive-portal-visual-system`):

1. **`baseline/` (`16` PNGs)** — Original pre-edit baseline screenshots captured before Kimi's Evidence Atlas styling pass.
2. **`takeover-baseline/` (`16` PNGs)** — Exact Chromium captures of Kimi's saved uncommitted worktree state at takeover time (`PORTAL_CAPTURE_STAGE=takeover-baseline`), before Antigravity's visual, diagram, responsive, and accessibility completion pass.
3. **`final/` (`20` PNGs + `2` WebM recordings)** — Final Chromium captures (`PORTAL_CAPTURE_STAGE=final`, default) across desktop (`1440×900`), mobile (`390×844`), and `prefers-reduced-motion: reduce` viewports, plus genuine Chromium WebM recordings of landing and route-mocked authenticated interactions.

## Reproduction Commands

```bash
# Default final captures (writes to artifacts/portal-visual-experience/final/)
pnpm exec playwright test --config=playwright.portal.config.ts --workers=1

# Optional stage override (e.g. baseline or takeover-baseline)
PORTAL_CAPTURE_STAGE=takeover-baseline pnpm exec playwright test --config=playwright.portal.config.ts --workers=1

# Optional WebM video recording
PORTAL_VIDEO=1 pnpm exec playwright test --config=playwright.portal.config.ts --project=desktop
```

## Capture Inventory (`final/`)

### Public Landing Atlas (`1440×900` Desktop & `390×844` Mobile)
- `landing-desktop.png` / `landing-mobile.png` — Public landing page with the interactive `DecisionSpecimen` (`Open-world` vs `Closed-world guess` contrast), `#open-world-loop` 4-lane SVG architecture diagram + routing calibration legend (mobile 5-card loop on `390×844`), Dual-Speed Architecture cards with authority boundary strip, 6-card Domain Invariants matrix, Verifiable Artifacts proof explorer, and local quickstart console.
- `landing-reduced-motion-desktop.png` / `landing-reduced-motion-mobile.png` — Public landing page with `prefers-reduced-motion: reduce` enabled (`Play walkthrough` disabled, reduced-motion notice visible, `data-motion="instant"`, manual step `05 / GOVERN` selected).
- `landing-motion-walkthrough.webm` — Chromium interaction recording of the public landing page exercising scenario tabs, step scrubbing, and `DecisionSpecimen` regime comparison.

### Route-Mocked Authenticated Observatory (`1440×900` Desktop & `390×844` Mobile)
All authenticated captures below use explicitly mocked browser routes (`tests/portal/support.ts`, `route-mocked-*`) and synthetic fixtures (`visual-fixture-token`, `oc_visual_fixture…`). They validate UI layout, typography, SVG telemetry charts, responsive containment, and keyboard/dialog accessibility—not live backend or PostgreSQL execution.

- `route-mocked-projects-desktop.png` / `route-mocked-projects-mobile.png` — Workspace projects overview.
- `route-mocked-project-create-dialog-desktop.png` / `route-mocked-project-create-dialog-mobile.png` — Accessible `Dialog` modal (`Create a project`) with initial focus, `Tab` trap, `Escape` dismissal, and focus restoration.
- `route-mocked-project-overview-desktop.png` / `route-mocked-project-overview-mobile.png` — Project overview with 4-column metric grid, wrapped desktop `SectionNav` (`Audit` and `Settings` visible), and scoped API keys table inside `.table-wrap`.
- `route-mocked-classifiers-desktop.png` / `route-mocked-classifiers-mobile.png` — Classifiers view showing locked permanent `UNKNOWN` chip.
- `route-mocked-unknowns-desktop.png` / `route-mocked-unknowns-mobile.png` — `Unknowns` triage workspace with monospace `metric-text` phrase card, full-width `1120×192` SVG daily trend chart with area gradient and callout badges, filter bar, keyboard-operable rows, and centered active mobile `SectionNav` pill.
- `route-mocked-unknown-detail-dialog-desktop.png` / `route-mocked-unknown-detail-dialog-mobile.png` — `UNKNOWN detail` triage dialog with framed bounded probability distribution (`UNKNOWN 91.0%`, `billing 5.0%`, `technical 2.5%`, `sales 1.5%`) and visible focus ring.
- `route-mocked-analytics-desktop.png` / `route-mocked-analytics-mobile.png` — `Analytics` workspace with dual-series `Runs vs UNKNOWN (30d)` SVG chart, `Top classes` volume bars, and `Alert rules`.
- `route-mocked-ontology-desktop.png` / `route-mocked-ontology-mobile.png` — `Ontology` immutable versions workspace with left-aligned chronological SVG lineage (`v1` → `v2` → `NEXT SNAPSHOT GATE (v3): Replay (OC-008) + Human (OC-009)`).
- `authenticated-journey-walkthrough.webm` — Chromium interaction recording of the route-mocked authenticated Portal journey covering dialog keyboard interactions, tab navigation, and `UNKNOWN` triage inspection.
