# Design and verification record

Design read (2026-11-06 redesign): a green-screen casting set. Viewers step onto a chroma-key stage and play in front of a camera monitor. Pure white set, chroma green `#00b140` stage panels, near-black `#0b0b0b` type and one REC red `#ff2d20` used only for the "forbidden" slash, the stamp and the low-time state. No cream, beige or ivory backgrounds anywhere (owner rule for all services). Dials: variance 7 / motion 6 / density 3. Native CSS and a few lines of JS, no motion library, no web fonts.

The owner rejected the first version (pale yellow-green on an off-white background, generic list layout) and asked for a fresh design with motion.

## Reference

[Juicyvice | Tinted Lip Balms, by Viktoriia Parii](https://www.behance.net/gallery/257203277/Juicyvice-Tinted-Lip-Balms-A-Bold-Take-on-Beauty), Behance, opened 2026-11-06 in a real Chrome session. Inspected the main-page presentation screens. Adopted: the thin full-width info strip above the header, the oversized wordmark sitting on the bottom edge of the hero, and small label/barcode-style metadata boxes. Not adopted: its lime palette, photography and fashion layout. Other projects opened (ACT IT GAME, Saca La Lengua) were game art or campaign pages, not usable as web UI references.

## System

- Type: Malgun Gothic for Korean and numbers, Arial Black for English headings and the wordmark, Arial for English body. Installed fonts only.
- Stage: home hero, page headers and the mission header are chroma panels with slowly rotating tracking-marker crosses. The home hero carries a camera viewfinder (corner brackets, REC label, running timecode, an autofocus box and a take counter) and the `OPEN CASTING` wordmark on its bottom edge.
- Missions: a call-sheet list with one glyph tile per template (ㄹ with a red slash, two rings, a 3×3 dig grid). Hover wipes the row green from the left.
- Play: a black camera monitor with green corner brackets, a large timer, a time bar that drains and turns red under 30% time, and a stamped "컷! / CUT!" with a counting score on the result.
- Motion: line wipes on headlines, a staggered list fade, viewfinder focus-in, prompt reveal, stamp, score count-up, toast entrance and cross-document view transitions.
- Interaction (owner request, 2026-11-06 second pass): the viewfinder tilts toward the mouse and its autofocus box follows the pointer; pressing it fires a shutter flash, locks the box red and counts `TAKE 02, 03…`. Wordmark letters hop when the mouse passes and ripple outward from a tapped letter. Every button shows a ripple from the touch point. Score bumps when it rises, a freshly dug ore cell drops in (found ore overshoots), the newest cleared word slides into the list, answer options and leaderboard rows stagger in, and a tapped mission row fills green on touch screens. Content below the fold is hidden only after the first scroll and reappears as it scrolls in, so screenshots and link previews without scrolling never show blank space.
- Copy: rewritten in plain 해요체 with concrete facts (round length, eligibility). Removed the hero kicker, the viewfinder slogan, the daily-limit badge beside the mission heading, the casting band subtitle, page-header subtitles on rankings, casting and studio, and the outlined footer wordmark. Entrance motion uses opacity, clip-path or shrinking scale only, so nothing overflows its box while it plays. `prefers-reduced-motion` removes animation and the timecode.
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

| Scroll-in reveal | Hid below-fold content at load | Hide only on the first scroll | Full-page screenshots without scrolling showed blank mission rows |
| Scroll-in reveal | IntersectionObserver | Position check on every scroll | Jumping to the bottom left skipped rows hidden |
| 390px viewfinder | 16:10 | 4:3 | Autofocus box overlapped `TAKE 01` |
| Casting band headline | Broke as "신청할 / 수 있어요." | No-break space in "신청할 수" | Split phrase |
| English 390px info strip | Two items | First item only | 25px horizontal overflow |
| Scroll-in reveal (cross-review) | Re-checked only on scroll | Also on resize | Growing the window left rows in view at opacity 0 |
| Ore hunt retry (cross-review) | Last dug cell kept between runs | Reset in the intro screen | A new run replayed the dig animation on the previous run's last cell |
| Player-facing Korean copy | Mixed 해요체 and 합니다체 in one sentence | 해요체 (consent and studio text stay formal) | Inconsistent voice |

## Verification

- `scripts/capture.py`: real browser journeys at 390px and 1280px against a temporary synthetic SQLite fixture. All three missions are played, plus the leaderboard, casting, studio, the sponsor report, the sponsor page, the FAQ and the English home. 44 screenshots, zero layout or page errors. It now waits for one-shot entrance animations to finish before each screenshot.
- `arka-design/scripts/check.py` on home, a mission, leaderboard, casting, FAQ, sponsor and studio: 0 defects at 1440×900 and 390×844, including impeccable.
- `pytest -q`: 54 passed, 5 PostgreSQL-only skipped.
