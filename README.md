# Drew Sparks — Digital Business Card

A single-page PWA business card for Drew Sparks, Founder of DriverLanding.
Zero build step, zero runtime dependencies, works offline.

**Live at:** `https://www.driverlanding.com/card/`

## Files

| File | Purpose |
|---|---|
| `index.html` | The whole app — markup, styles, and behaviour. |
| `qr.js` | Self-contained QR encoder (byte mode, versions 1–40) rendering to SVG. |
| `sw.js` | Service worker; precaches the card so it works with no signal. |
| `manifest.json` | PWA manifest for home-screen install. |
| `drew-sparks.vcf` | Full contact card with embedded photo — the download target. |
| `drew-sparks.min.vcf` | Stripped card with a QR-sized photo — this is what the Contact QR encodes. |
| `assets/knox-BG.png` | Knoxville street map used as the page background. |
| `assets/headshot-cutout.png` | Transparent portrait that overhangs the card. |
| `build-vcf.py` | Regenerates both `.vcf` files. |
| `build-icons.py` | Regenerates the icon set from `assets/icon.png`. |
| `verify.mjs` | Consistency checks. Run after any change to contact details. |
| `.htaccess` | Deployment rules — **required**, see below. |

## Changing contact details

Details live in three places that must agree:

1. `build-vcf.py` — the source of truth for the `.vcf` files
2. the `VCARD` string inlined in `index.html` (so the Contact QR renders offline)
3. the visible contact rows in `index.html`

After editing, regenerate and check:

```bash
python3 build-vcf.py && node verify.mjs
```

`verify.mjs` fails loudly if the inlined vCard and the `.vcf` file drift apart —
which would otherwise mean the QR someone scans hands them different details
from the card they download. `build-vcf.py` also patches the `VCARD` array in
`index.html` directly, rather than leaving it to be copied by hand — the array
now contains a base64 photo blob, and hand-copying that is exactly the kind of
thing that silently drifts.

## The Contact QR, and getting a photo offline

**The Contact QR is text-only, deliberately.** A 96×96 embedded photo was tried
and reverted: it pushed the code from 57 to 149 modules, and scanning it on a
real phone in a real room got noticeably harder. A camera simulation had said
the density was fine — it was wrong, and the phone was right. The picture
wasn't worth the friction.

Text-only holds the code at version 10 / 57 modules — about **3.3 CSS pixels
per module** at the 200px it renders at. Chunky and forgiving.

`verify.mjs` enforces a 73-module ceiling so this can't creep back. The
regression is invisible from a desk: the code still encodes, and still decodes
from a clean render. It only bites when someone is pointing a phone at it.

### Send Contact — the actual answer for offline

The QR was the wrong place to put a photo. **Send Contact** (the paper-plane in
the QR sidebar) shares the real `drew-sparks.vcf` — 300px photo, LinkedIn,
scheduling link, everything — straight to a nearby phone over Quick Share or
AirDrop. No network on either side, and no pressure on the QR's density.

The file is precached by the service worker, so it works with no signal. The
button only appears where `navigator.canShare({ files })` is true, since
`navigator.share` existing says nothing about file support.

So there are three handoffs, each right for a different moment:

| | Needs network | Carries photo | Good for |
|---|---|---|---|
| Contact QR | no | no | anyone, instantly, no setup |
| Send Contact | no | **yes** | in person, phone to phone |
| Share (link) | recipient only | yes, once loaded | texting someone later |

### If you want more in the QR later

There's headroom before density becomes a problem again — roughly 100 more
bytes keeps it under 73 modules. A one-line `NOTE:` saying what DriverLanding
does, or `ADR` with Knoxville/TN, would help someone remember the conversation
when they find your card weeks later. Both are cheap; a photo is not.

## Icons

`assets/icon.png` is the only source. Everything else is generated:

```bash
python3 build-icons.py && node verify.mjs
```

Android does not use one icon for everything, and giving it the same file for
every purpose is what produces clipped corners and blobby badges:

| Purpose | File | Notes |
|---|---|---|
| `any` | `icon-192`, `icon-512` | Drawn as-is, never masked. |
| `maskable` | `icon-maskable-512` | Artwork scaled to 88% so it sits inside the safe zone; background bleeds to the edge. |
| `monochrome` | `icon-monochrome-512` | Alpha-only silhouette for OS theming. |
| badge | `icon-badge-96` | Alpha-only, for the pinned notification. |

The maskable safe zone is a circle 80% of the icon's width — anything outside it
can be cropped, and how much depends on the launcher's mask. The source art's
corners sit at r=220px on a 512px canvas against a 205px safe radius, so a
circular mask cut both edges off the card. Scaling to 88% brings them to r=194.

Never declare `"purpose": "any maskable"` on one file. That tells the launcher
it may mask artwork laid out to be seen whole, and the corners go.

## Deployment notes

Drop this directory in at the web root as `card/`. Two things are not optional:

- **`.htaccess` must ship with it.** The site root sets
  `X-Content-Type-Options: nosniff` globally, so a `.vcf` served without an
  explicit `text/vcard` type will not be handed to the contacts app — "Save to
  Contacts" would download a dead file instead. The `.htaccess` here adds that
  MIME type.
- **The URL is `https://www.driverlanding.com/card/`,** with the `www.` and the
  trailing slash. The site 301s bare→`www`, and Apache 301s `/card`→`/card/`;
  encoding the final address in the QR skips two redirects on the bad
  conference-hall connections this card exists for.

Bump `CACHE` in `sw.js` whenever a precached asset changes, or returning
visitors keep the old version.

**The host sends `Cache-Control: max-age=7200` on everything** — a Bluehost
default, not set by either `.htaccess` here. Discovered the hard way: right
after a deploy, the Contact QR's new photo took two reloads to show up. A
plain `fetch()` in the service worker's stale-while-revalidate logic honors
that header, so it can silently hand back the browser's own 2-hour-old HTTP
cache instead of ever asking the server for anything — defeating the whole
point of revalidating on every visit. Both the install-time precache and the
same-origin fetch handler in `sw.js` pass `{ cache: 'reload' }` to force past
it; `verify.mjs` checks both are still there, since dropping either silently
reintroduces a redeploy delay with nothing to notice it by.

## Design

The layout is deliberately the original: the Knoxville street map behind a white
sheet, the avatar overhanging an angled header, the footer logo and accent bar
pinned to the bottom, and a fixed 650px frame so that toggling the QR morphs
only the middle channel — nothing jumps. The palette is DriverLanding's navy and
amber in place of Tenstreet red.

The QR view keeps the phone, email and LinkedIn rows on screen alongside the
code. Someone scanning it can read the details at the same time; only the
scheduling row drops out, to make room.

Departures from the original:

- **The portrait is an uncropped cutout**, not a circular crop, so the
  silhouette breaks the card's top edge. `drop-shadow` follows the alpha, so the
  shadow traces the figure. The amber chevron is baked into the artwork.
- **The header's bottom edge is a landing curve**, not the old straight
  diagonal — the descent flattening out, the company name drawn literally. It is
  an SVG with `preserveAspectRatio="none"` so it stretches to any card width; a
  `clip-path` polygon could only ever be straight.
- **The icon circles carry the tint, not the glyphs.** The original used a red
  glyph on a grey circle; amber is too light to read that way, so the circle
  takes the colour and the glyph stays navy.

## Motion

Two ambient layers, both of which stop under `prefers-reduced-motion`:

- **Header starfield** — the site's three-layer `box-shadow` starfield, with
  larger stars and faster layers so it still reads in a header this short.
  Positions are in container query units (`cqw`/`cqh`) so they track the
  header's box: the card is 320–400px wide depending on the handset, and px
  offsets tuned for 400 would drop stars off the right edge on a narrow phone.
  `container-type: size` sits on `.header-stars`, which takes its size from
  `inset:0` — putting it on `.header` would collapse the header to nothing.
- **Accent bar** — the site's `.text-shimmer` gradient and keyframes, run across
  the bar rather than clipped to text, at 16s against the site's 5s.

### Parallax

Tilting the phone shifts the map and the star layers against the card. Two
custom properties, `--px` / `--py`, are the whole interface: JavaScript eases
them toward a target and CSS does the rest.

The reason it costs nothing is that the stars move via the independent
`translate` property while their drift animation owns `transform`. The two
compose, so parallax needed no wrapper elements and clobbers no animation. Each
layer takes a different multiplier (0.4 / 0.85 / 1.5), so near stars travel
almost four times as far as distant ones. The map plane is bled 26px past the
viewport so the shift never uncovers an edge.

Constraints worth keeping in mind if this is ever touched:

- **Nothing here affects layout** — transforms and translates only, so no
  reflow. The rAF loop stops once the easing settles rather than idling.
- **iOS is deliberately excluded.** Device orientation there needs a permission
  prompt behind a user gesture, and prompting for motion access on a business
  card costs more goodwill than the effect is worth. Desktop gets the same
  effect from pointer movement instead.
- **The neutral point drifts toward the current pose**, so holding a tilt
  settles back to centre rather than pinning the background off-axis.
- **`prefers-reduced-motion` stops it twice over:** the JS refuses to update,
  and a `!important` rule pins `--px` / `--py` to zero. Inline styles lose to
  `!important` in a stylesheet, so that holds even mid-ease. Parallax is a known
  vestibular trigger — this is not optional.

## At a conference

- Launching from the home screen opens straight to the QR view, with the phone,
  email and LinkedIn rows still readable beside it.
- **Tap the code to fill the screen with it.** A web page cannot raise screen
  brightness, but a white field and a much larger code are what actually rescue
  a scan in bad hall lighting or across a table.
- The screen is held awake (`navigator.wakeLock`) the whole time the code is up.
  A phone sleeping mid-scan is the most common reason a handoff needs a retry,
  and this is the one piece of screen behaviour a web page is allowed to control.
- **Long-pressing the home screen icon** jumps straight to the code, via a
  manifest shortcut pointing at `?view=qr`.
- **The bell in the QR sidebar pins the card to the notification shade** — a
  notification with `requireInteraction`, so it stays until dismissed, shows on
  the lock screen, and reopens the card on the code. The button only renders in
  standalone mode; a recipient viewing the card in a browser never sees it.

### On lock-screen access

The pinned notification is as close as the web gets. Worth being clear about
what it is not:

- **It is not a Live Activity.** ActivityKit is iOS-only and native-only; there
  is no web equivalent, and Android's Live Updates API is likewise native-only.
- **It does not survive a reboot,** and the user can swipe it away.
- Whether it appears on the lock screen depends on the phone's notification
  settings.

**Google Wallet** is the stronger option and is genuinely worth doing, but it
cannot be built from a static page. It needs a Google Wallet API issuer account,
a service account key, and a server-side endpoint that signs an RS256 JWT — the
"Add to Google Wallet" button is a signed token, not a link. A generic pass
carries a `QR_CODE` barcode, which would be the card URL. Wallet passes also
accept location triggers intended to surface the pass near a given place, which
would fit a conference venue well — confirm the current behaviour against
Google's docs before relying on it, as pass surfacing has changed over time.

The signing endpoint would sit naturally in `DriverLanding-Home` alongside the
existing PHP. The issuer account has to be set up first.

## Notes on the rewrite

- **NFC was removed, not fixed.** Phone-to-phone NFC transfer (Android Beam)
  was removed from Android in 2019, so no web page can push a contact to
  another handset by tapping — the old build's NFC button could never have
  worked against a Pixel. Web NFC only writes to physical tags. QR, the share
  sheet, and the `.vcf` download cover every real handoff.
- **No CDNs.** The old card pulled Font Awesome and `qrcode.js` from
  cdnjs at runtime, so a weak connection meant no icons and no QR — exactly
  when you need them. Icons are now inline SVG and the QR encoder is local.
- **The frame no longer clips.** The original pinned 650px and hid the overflow,
  which cut the buttons off on shorter handsets. The frame is still fixed, but
  the contact channel scrolls as a last resort instead of being cut, and short
  screens get a compact variant with a smaller code.
- **Row padding is not animated.** Transitioning it reflowed the column every
  frame and the in-flight value held rows at full height long enough to
  overflow the frame. Only opacity fades, as the original intended.

## Verifying the QR encoder

`qr.js` was validated against the `segno` reference implementation and decoded
with `zxing-cpp` (the engine family Android and Google Lens use): 284/284
payloads across versions 1–40 and all four EC levels decode to the exact input,
with every Reed–Solomon block showing zero syndromes.
