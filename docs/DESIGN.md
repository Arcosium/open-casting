# Design and verification record

Design read (2026-11-06 redesign): a green-screen casting set. Viewers step onto a chroma-key stage and play in front of a camera monitor. Pure white set, chroma green `#00b140` stage panels, near-black `#0b0b0b` type and one REC red `#ff2d20` used only for the "forbidden" slash, the stamp and the low-time state. No cream, beige or ivory backgrounds anywhere (owner rule for all services). Dials: variance 7 / motion 6 / density 3. Native CSS and a few lines of JS, no motion library, no web fonts.

The owner rejected the first version (pale yellow-green on an off-white background, generic list layout) and asked for a fresh design with motion.

## Reference

[Juicyvice | Tinted Lip Balms, by Viktoriia Parii](https://www.behance.net/gallery/257203277/Juicyvice-Tinted-Lip-Balms-A-Bold-Take-on-Beauty), Behance, opened 2026-11-06 in a real Chrome session. Inspected the main-page presentation screens. Adopted: the thin full-width info strip above the header, the oversized wordmark sitting on the bottom edge of the hero, and small label/barcode-style metadata boxes. Not adopted: its lime palette, photography and fashion layout. Other projects opened (ACT IT GAME, Saca La Lengua) were game art or campaign pages, not usable as web UI references.

## System

- Type: Malgun Gothic for Korean and numbers, Arial Black for English headings and the wordmark, Arial for English body. Installed fonts only.
- Stage: home hero, page headers and the mission header are chroma panels with slowly rotating tracking-marker crosses. The home hero carries a camera viewfinder (corner brackets, REC label, running timecode) and the `OPEN CASTING` wordmark on its bottom edge.
- Missions: a call-sheet list with one glyph tile per template (ㄹ with a red slash, two rings, a 3×3 dig grid). Hover wipes the row green from the left.
- Play: a black camera monitor with green corner brackets, a large timer, a time bar that drains and turns red under 30% time, and a stamped "컷! / CUT!" with a counting score on the result.
- Motion: line wipes on headlines, a staggered list fade, viewfinder focus-in, prompt reveal, stamp, score count-up, toast entrance and cross-document view transitions. Entrance motion uses opacity, clip-path or shrinking scale only, so nothing overflows its box while it plays. `prefers-reduced-motion` removes animation and the timecode.
- The sponsor label stays pinned to the top of every sponsored screen (legal guardrail).

## Defects found and fixed

| Location | Before | After | Why |
|---|---|---|---|
| Mission rows | `style="--i:n"` stagger | `nth-child` delays in CSS | The app CSP (`style-src 'self'`) blocked inline style attributes |
| Header, eyebrow, viewfinder | Blinking REC dots, "On air now" ticker item, infinite marquee | Static dots, static info strip with real facts | Fake live status and marquee are rejected patterns (impeccable `pulsing-dot`, `marquee`) |
| Casting band, monitor | Corner brackets drawn as background gradients | Brackets as `::before`/`::after` borders | The analyzer read the gradient colour as the text background |
| Secondary and language buttons | `background: transparent` | Explicit white (black inside the monitor) | Static contrast check resolved transparent to the base black |
| Viewfinder | Gradient-only background | Explicit chroma background colour | Same contrast misread |
| Entrance motion | `translateY` and `scale(>1)` | Opacity, clip-path, `scale(<1)` | Moving boxes overflowed their parents while animating |
| Hero and footer wordmarks | Negative bottom offset inside `overflow:hidden` | Sits on the edge, `contain: paint`, extra bottom space | Glyph metrics overflowed and overlapped the footer text |
| Timer, result score | `line-height: 0.9` | `1.1` with em margins | Text boxes overlapped the labels below |
| Global scroll | `scroll-behavior: smooth` | Removed | The sticky sponsor-label check measured mid-scroll |
| Language button | White text on white | Black text | Inherited button colour |
| Rank 1 row | Grey demo label on green | Black label | 2.4:1 contrast |
| 390px hero, page headers | Markers and crosshair over the headline | Only one corner marker; crosshair hidden | Overlap with type |
| English hero | Four-line headline at 1280px | Smaller English size, two lines | Hero headline limit |
| FAQ | Rotating `+` box overflowed the row | Swap to a minus sign | 7px horizontal spill |
| `.sr-only` labels | Reported as clipped visible text | `opacity: 0` | Screen-reader labels stay accessible and invisible |

## Verification

- `scripts/capture.py`: real browser journeys at 390px and 1280px against a temporary synthetic SQLite fixture. All three missions are played, plus the leaderboard, casting, studio, the sponsor report, the sponsor page, the FAQ and the English home. 44 screenshots, zero layout or page errors. It now waits for one-shot entrance animations to finish before each screenshot.
- `arka-design/scripts/check.py` on home, a mission, leaderboard, casting, FAQ, sponsor and studio: 0 defects at 1440×900 and 390×844, including impeccable.
- `pytest -q`: 54 passed, 5 PostgreSQL-only skipped.
