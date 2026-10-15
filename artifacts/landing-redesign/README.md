# Implemented landing redesign verification

Status: delivered in PR #61; independent review, all five PR checks and main CI passed.
This directory is separate from
`artifacts/landing-visual-review`, which remains historical baseline evidence.

Implementation branch: `abdelhamid-khaled/feat/landing-mobile-diagram-copy-and-motion`.
Implementation: `05b9eb5d17b68ef40add9c12d986115abec2668f`.
Integrated base: `d8b3051c48439144c4df393cfd57f2591598cf3b`.
Local review URL: `http://127.0.0.1:5174`.

The walkthrough is simulated and does not call a provider or activate a class.
Screenshots and recordings validate the implemented interface, not classification
quality or live-backend workflow completeness.

## Fresh artifacts

Captured from the actual running application on 2026-10-15. Full-page PNGs use
the default UNKNOWN observation step. Dimensions below are viewport dimensions,
not the taller full-page image dimensions.
`manifest.json` records canonical Git source hashes, actual PNG dimensions and
artifact hashes. Full-page captures exclude the reserved 15px scrollbar.

| Artifact | Viewport | Layout |
| --- | --- | --- |
| `desktop-1440-full.png` | 1440 × 1000 | Horizontal SVG |
| `desktop-1280-full.png` | 1280 × 800 | Horizontal SVG |
| `tablet-834-full.png` | 834 × 1112 | Connected vertical cards |
| `mobile-390-full.png` | 390 × 844 | Connected vertical cards |
| `mobile-375-full.png` | 375 × 812 | Connected vertical cards |
| `mobile-390-decision-loop.png` | 390 × 844, element capture | UNKNOWN evidence step |
| `mobile-390-reduced-motion.png` | 390 × 844, element capture | Manual abstention-score step |
| `landing-desktop-motion.mp4` | 1440 × 1000 | Playback, scenario/step selection, telemetry |

The MP4 was recorded using Chrome's actual screencast, not generated from
screenshots. Browser media decoding measured **103.592333 seconds**, 1440 × 1000,
`readyState=4`. It shows explicit playback and all four simulated scenarios.
Nonblank frames decoded successfully at 20%, 50% and 90% of its duration.
It was captured before the safe base fast-forward; the landing source is the
same implementation committed as `05b9eb5`.

## Interaction and accessibility checks

- 22 component tests pass, including all 20 scenario/step probability invariants,
  mobile navigation, explicit playback, reduced motion, keyboard tabs, disclosure
  focus, and stale clipboard completion.
- Latest actual-browser pass: **40 scenario/step checks**, four scenarios × five
  steps at desktop and phone widths. Progress, normalized distributions,
  outage isolation and mobile title bounds pass.
- All five viewports have `scrollWidth == clientWidth`: 1425, 1265, 819, 375
  and 360px respectively. This desktop Chromium instance reserves a 15px
  scrollbar. There is no horizontal page overflow.
- At 390px, card titles are **14px**, active badges **11px**, the SVG is hidden
  and connected cards are displayed. Tablet uses cards too, rather than a
  compressed diagram.
- Reduced-motion runtime check: playback disabled, manual Next reaches step 2,
  `data-motion=instant`, card transition `0s`, headline animation `none`.
- Actual browser checks also exercised playback/pause, keyboard scenario and
  quickstart tabs, clipboard success, progressive disclosure and the workspace
  CTA's sign-in gate. Clipboard failure/race paths have component regressions.
- Independent final code/visual review approved the implementation and fresh
  desktop/tablet/phone artifacts. Earlier findings covering keyboard motion,
  clipboard races, disclosure identity and UNKNOWN probability attribution were
  fixed and re-reviewed.

## Commands and results

Run from the repository root in PowerShell 7:

```powershell
pnpm --filter @openclass/portal test
make check
$env:PYTEST_ADDOPTS='-q -m "not postgres and not live" --tb=short'
make test
$env:CIRCLE_NODE_TOTAL='3'
$env:NODE_OPTIONS='--max-old-space-size=1024'
$env:NEXT_TELEMETRY_DISABLED='1'
npm run build
uv build --all-packages
```

All exit 0. `make check` includes 109 control-plane, 22 portal and 18 SDK tests.
The offline Python result is **725 passed, 7 skipped, 58 deselected**, 948 warnings,
188.33 seconds. PostgreSQL/live cases were deliberately excluded because the
local Docker engine remains unavailable. All three JavaScript applications and
all 11 Python workspace packages build; Next uses two bounded workers.

## Limits

These checks verify landing behavior and layout, not genuine authenticated
backend workflows, model accuracy, automatic class discovery or release
readiness. Hosted PostgreSQL/live-stack delivery has separate gates. No physical
phone or cross-browser matrix is claimed. PR #61 merged as
`227169358fe321dfed59be89dd47829be6da8781`; main CI `38797682622` passed.
The takeover ledger records delivery links and post-merge verification.

During the video sampling probe, the local browser logged a media range-cache
error despite the successful sampled decodes. No independent full sequential
video replay is claimed.
