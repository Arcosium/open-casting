# Design and verification record

Design read: a playful, free challenge platform for Shorts viewers. A casting clapperboard supplies the metaphor; pale green-yellow, graphite and a light neutral background make time, score and entry actions easy to find. Variance 5 / motion 2 / density 3. Native CSS, no motion library, no external assets or fonts.

Reference search on 2026-11-06: [Digital Dunes, VALMAX and collaborators](https://www.behance.net/gallery/231114955/Digital-Dunes-Branding-and-Web-Design-Gaming-Company). The project page returned HTTP 403 in web access; Chromium also failed certificate verification. Its actual project visuals could not be inspected, so no claim of applying that reference is made. The implementation follows SPEC §6 and arka-design's fallback rules. The design-system search suggested vibrant blocks and large type; no suggested fonts, fake ratings or unrelated app-store controls were adopted.

Installed local fonts were checked with `fc-match`: Malgun Gothic, Arial Black and Arial. Korean and numeric displays use Malgun Gothic; English headings use Arial Black and body copy uses Arial. No font files are embedded or distributed.

| Location | Before | After | Why |
|---|---|---|---|
| Global type | Arial before Korean family | Malgun Gothic first; English locale has Arial body | Honor the script-specific house font rule |
| Clapperboard | Repeating CSS gradient | Original local SVG flat graphic | Remove the checker flag without third-party assets |
| Accessibility labels | A clipped 1px label was reported as visible content | Explicitly transparent, non-interactive screen-reader labels | Preserve accessible names and make their visual state explicit |
| Closed FAQ answers | Checker saw the retained layout of hidden answer text | Closed answers explicitly `display:none` | Closed details have no visible overlapping text |
| Studio entry | Login view probed a protected endpoint and generated an expected HTTP 401 | Check a public session-status endpoint before protected reads | The regular sign-in screen produces no HTTP error |
| Mobile report table | Score and percentage digits wrapped across lines | Horizontally scrollable table, unbroken numeric cells and a swipe hint | Keep measurements readable at 390px |
| Short-link mission selector | Long selected title clipped at 390px | Explicit text ellipsis | Keep the full accessible name while fitting the control |

Verification artifacts: `_workspace/design/`, `_workspace/browser-results.json`, `_workspace/shots/`. `scripts/capture.py` exercises real HTTP and UI operations against a temporary synthetic SQLite fixture, closes its own Chromium, and stops only its own server process. No production contacts or browser profiles are used.

Final local checks: 45 pytest cases passed. Browser journeys produced 44 screenshots at 390px and 1280px with zero layout/page errors. The graph builder was attempted, but this installation lacks Python/JavaScript parsers, so code exploration used direct reads instead.
