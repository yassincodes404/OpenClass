# OC-BG-045 / OC-046: landing redesign

Status: implemented locally and independently reviewed; focused PR delivery pending.
Priority: P1. Dependencies: OC-012 and OC-043 / OC-BG-042.

The previous planner returned this task in chat on 2026-10-15 at 11:08:58 UTC,
under the title “Landing-Page Redesign: Readable Mobile Diagram, Simpler Copy &
Purposeful Motion.” It did not save a repository document. This file preserves
the recoverable requirements and records the current implementation direction.
The existing screenshots and recording under `artifacts/landing-visual-review`
are baseline evidence, not evidence of this redesign.

## Product and visual direction

Present OpenClass as an evidence-first open-world decision engine, not a generic
chatbot or an autonomous learning promise. Use an editorial, light technical
canvas around a dark decision instrument: clear large typography, restrained
color, precise labels, generous spacing, and a conspicuous UNKNOWN outcome.
Create a coherent visual language rather than adding decorative cards.

The hero explains classification and abstention in one short statement. Follow
with the interactive decision loop, then progressively disclosed architecture,
evidence and a three-step local quickstart. Primary actions must lead to working
onboarding or actual repository instructions, not an invented hosted service.

## Recovered requirements

1. Preserve the desktop horizontal diagram. Below approximately 768px, replace
   it with five vertically connected, tappable step cards rather than scaling
   down the desktop SVG. Show lane, node title, outcome, active indicator and
   progress. Titles must be at least 13px and badges 11px. No clipped labels or
   horizontal overflow.
2. Extract `ObservatoryArchitectureSections`, `GROUNDED_PROOFS`, and
   `QUICKSTART_TABS` into `apps/portal/src/observatory-sections.tsx`, preserving
   compatibility re-exports where current imports need them.
3. Shorten hero and lane copy. Pillar descriptions must be no more than
   22 words. Provide a three-step developer quickstart. Reveal technical detail
   on demand. Preserve the single-source scenario probabilities and existing
   scenario, step, playback and tab behavior.
4. Use purposeful state entrances near 180ms and progress/connector transitions
   near 240ms. Prefer transform and opacity, with
   `cubic-bezier(0.23, 1, 0.32, 1)` or
   `cubic-bezier(0.77, 0, 0.175, 1)`. Do not use `transition: all`.
   Respect reduced motion and coarse pointers.
5. Keep all demonstration scenarios explicitly simulated. UNKNOWN is not proof
   of a new class. Evaluation and human approval remain required before
   activation. Do not claim measured accuracy, performance, or cost without
   evidence.

## Accessibility and verification

- Semantic controls, visible focus, keyboard navigation, readable contrast,
  and accessible active/playback state.
- Test scenario switching, all steps, playback and pause, quickstart tabs,
  links and primary actions. Paused/manual navigation must not restart playback
  unexpectedly.
- Component tests preserve probability calculations and exercise new mobile
  controls.
- Inspect the running application at desktop, tablet and mobile sizes,
  including the recovered 1280×800 and 375×812 targets. Verify no horizontal
  overflow or clipped diagram labels.
- Verify reduced-motion behavior and responsive layout through actual browser
  tools. Do not count route-mocked browser results as live-backend evidence.
- Save fresh desktop/tablet/mobile screenshots and an interaction recording
  under a new implementation-specific artifact directory, with commands,
  viewport dimensions and a manifest identifying the tested commit.
- Run portal checks, repository checks and independent visual/code review.

## Ownership boundaries

Landing implementation primarily owns `apps/portal/src/open-world-stage.tsx`,
`portal.tsx`, the new `observatory-sections.tsx`, relevant styles and component
tests. Serialize changes with the separate frontend feature-parity work.
Do not retire `apps/web` as a side effect of a landing redesign.

## Implementation evidence

Implementation: `05b9eb5d17b68ef40add9c12d986115abec2668f`, based on merged
main `d8b3051c48439144c4df393cfd57f2591598cf3b`. The responsive switch uses
1160px so tablet labels stay readable; both recovered desktop targets retain
the horizontal diagram.

The implementation has 22 passing component tests, 40 actual-browser
scenario/step checks, five fresh viewport screenshots and a desktop interaction
recording under `artifacts/landing-redesign/`. Mobile titles are 14px and active
badges 11px. Reduced motion disables playback while preserving manual controls;
actual computed transition duration is `0s` and headline animation is `none`.
Independent final code/visual review reported no remaining high-confidence bugs.
See the artifact README for exact dimensions, commands, revision and limitations.

Repository checks, the explicit offline Python suite, JavaScript builds and all
11 Python package builds pass. These are not authenticated live-backend
workflow evidence. PR CI and merge are still required for delivery.
