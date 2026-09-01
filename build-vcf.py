#!/usr/bin/env python3
"""Regenerates drew-sparks.vcf and drew-sparks.min.vcf, and patches the VCARD
string inlined in index.html to match the minified card exactly.

Contact details live here, in index.html's CONTACT rows, and in that inlined
VCARD string. Change one, change the others -- the inlined string must stay
byte-identical to drew-sparks.min.vcf or the Contact QR and the downloaded
card disagree. This script keeps that last pair in sync automatically: with a
base64 photo blob involved, hand-copying it into index.html is exactly the
kind of thing that silently drifts.

    python3 build-vcf.py

Requires Pillow (already a dependency of build-icons.py):
    pip install Pillow
"""
import base64, io, os, re, textwrap

from PIL import Image

PHOTO = 'assets/vcard-photo.jpg'          # 400x400 master, source for both cards
PHOTO_OVERRIDE = 'assets/vcard-photo-qr.jpg'   # optional hand-made QR thumbnail
INDEX_HTML = 'index.html'

# The downloadable card is fetched over the network like any file, so its photo
# is only limited by taste. 300px matches what the pre-DriverLanding card
# shipped, at ~13KB.
FULL_PHOTO_SIZE = 300
FULL_PHOTO_QUALITY = 72

# The minified card's photo has to fit inside a QR code someone scans off a
# phone screen with no network -- there is no server round trip to fall back
# to, so this budget IS the image quality.
#
# Sizing rule, measured rather than guessed: a QR needs roughly 2.3 captured
# camera pixels per module to decode. At 96px/2050 bytes the code lands on
# version 33 (149 modules), needing ~342px of camera resolution against ~289px
# for the old 56px thumbnail -- about 18% more demanding, which any modern
# phone clears by a wide margin at normal scanning distance. Going further hits
# diminishing visual returns: 112px looks barely different but needs ~360px.
#
# 2050 leaves ~18 bytes under version 33's 2068-byte cap at EC level L, so a
# short future edit to a field will not silently push the code a version
# larger. Raise both together if you want a bigger photo -- see README for the
# version/capacity table.
#
# EC level L, not M or Q: this is read off a lit screen at close range, the
# easiest condition a reader ever sees, so the redundancy those levels spend is
# better spent as photo bytes.
QR_PHOTO_SIZE = 96
QR_PHOTO_BUDGET = 2050
QR_PHOTO_ECL = 'L'

C = dict(
    fn='Drew Sparks', n='Sparks;Drew;;;', org='DriverLanding, LLC', title='Founder',
    tel='(865) 236-1194', tel_e164='+18652361194', email='drew@driverlanding.com',
    site='https://driverlanding.com', card='https://www.driverlanding.com/card/',
    li='https://www.linkedin.com/in/drewksparks/',
    cal='https://calendly.com/driverlanding/intro',
    note='Driver recruiting landing pages, job distribution, and pipeline '
         'analytics for trucking carriers.',
)


def fold(line, limit=75):
    """RFC 2425 folding: <=75 octets per line, continuations prefixed with one space."""
    b = line.encode('utf-8')
    if len(b) <= limit:
        return [line]
    out, first = [], True
    while b:
        take = limit if first else limit - 1
        cut = min(take, len(b))
        while cut > 0 and cut < len(b) and (b[cut] & 0xC0) == 0x80:
            cut -= 1                      # never split a multi-byte character
        chunk, b = b[:cut], b[cut:]
        out.append(chunk.decode('utf-8') if first else ' ' + chunk.decode('utf-8'))
        first = False
    return out


def write(path, lines):
    with open(path, 'wb') as fh:
        fh.write(('\r\n'.join(lines) + '\r\n').encode('utf-8'))
    print(f'{path}: {os.path.getsize(path)} bytes, {len(lines)} lines')


def assemble_with_photo(skeleton, jpeg):
    """Folds a skeleton plus a base64 PHOTO into finished vCard lines."""
    b64 = base64.b64encode(jpeg).decode()
    lines = list(skeleton)
    lines.append('PHOTO;TYPE=JPEG;ENCODING=b:')
    lines.extend(' ' + c for c in textwrap.wrap(b64, 74))
    lines.append('END:VCARD')
    folded = []
    for l in lines:
        folded.extend(fold(l))
    total = len(('\r\n'.join(folded) + '\r\n').encode('utf-8'))
    return folded, total


def fit_photo_for_qr(skeleton, path=PHOTO, size=QR_PHOTO_SIZE, budget=QR_PHOTO_BUDGET):
    """Produces the QR thumbnail.

    If a hand-made JPEG exists at PHOTO_OVERRIDE it is embedded byte for byte,
    so you can tune it in whatever editor you like; this only checks that it
    actually fits and reports the headroom. Otherwise the photo is resized from
    the master and its JPEG quality binary-searched for the best-looking version
    that stays under `budget`.
    """
    if os.path.exists(PHOTO_OVERRIDE):
        jpeg = open(PHOTO_OVERRIDE, 'rb').read()
        with Image.open(io.BytesIO(jpeg)) as probe:
            dims = probe.size
        folded, total = assemble_with_photo(skeleton, jpeg)
        if total > budget:
            # Base64 inflates by 4/3 and folding adds ~3 bytes per 74 chars, so
            # spell out the actual ceiling rather than leaving it to be guessed.
            allowance = (budget - (total - len(base64.b64encode(jpeg)) -
                                   3 * ((len(base64.b64encode(jpeg)) + 73) // 74)))
            raise SystemExit(
                f'{PHOTO_OVERRIDE} is {len(jpeg)} bytes at {dims[0]}x{dims[1]}, which makes a '
                f'{total}-byte vCard -- {total - budget} over the {budget}-byte budget.\n'
                f'The JPEG itself must be at most ~{allowance * 3 // 4} bytes. '
                f'Re-export smaller, or raise QR_PHOTO_BUDGET (and check the version table '
                f'in the README first).')
        print(f'QR photo: {PHOTO_OVERRIDE} used as-is -- {dims[0]}x{dims[1]}, {len(jpeg)} bytes '
              f'jpeg, {total} bytes total ({budget - total} bytes under budget)')
        return folded

    src = Image.open(path).convert('RGB').resize((size, size), Image.LANCZOS)

    def assemble(quality):
        buf = io.BytesIO()
        src.save(buf, 'JPEG', quality=quality, optimize=True)
        jpeg = buf.getvalue()
        folded, total = assemble_with_photo(skeleton, jpeg)
        return folded, jpeg, total

    lo, hi, best = 5, 95, None
    while lo <= hi:
        mid = (lo + hi) // 2
        folded, jpeg, total = assemble(mid)
        if total <= budget:
            best = (folded, jpeg, mid, total)
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        raise SystemExit(f'no JPEG quality at {size}x{size}px fits the {budget}-byte budget; '
                          f'shrink QR_PHOTO_SIZE')
    folded, jpeg, quality, total = best
    print(f'QR photo: {size}x{size}px @ quality {quality} -> {len(jpeg)} bytes jpeg, '
          f'{total} bytes total ({budget - total} under budget, EC level {QR_PHOTO_ECL})')
    return folded


def patch_index_html(min_lines, card_url):
    """Rewrites the inlined VCARD array to match min_lines exactly, keeping the
    URL line as a `+ CARD_URL` expression rather than a baked-in literal."""
    html = open(INDEX_HTML, encoding='utf-8').read()

    js_lines = []
    for l in min_lines:
        if l == 'URL:' + card_url:
            js_lines.append("'URL:' + CARD_URL")
        else:
            escaped = l.replace('\\', '\\\\').replace("'", "\\'")
            js_lines.append(f"'{escaped}'")

    new_block = "var VCARD = [\n    " + ',\n    '.join(js_lines) + "\n  ].join('\\r\\n') + '\\r\\n';"

    pattern = re.compile(r"var VCARD = \[[\s\S]*?\]\.join\('\\r\\n'\) \+ '\\r\\n';")
    if not pattern.search(html):
        raise SystemExit('could not find the VCARD array in index.html -- has it been renamed?')
    html = pattern.sub(lambda _m: new_block, html, count=1)

    open(INDEX_HTML, 'w', encoding='utf-8').write(html)
    print(f'{INDEX_HTML}: VCARD array patched ({len(js_lines)} lines)')


# --- Full card: every field plus a full-quality photo. This is the download
#     target, fetched over the network like any file, so it does not need to
#     fit inside a QR's data budget. ---
props = [
    'BEGIN:VCARD', 'VERSION:3.0',
    'N:' + C['n'], 'FN:' + C['fn'], 'ORG:' + C['org'], 'TITLE:' + C['title'],
    'TEL;TYPE=CELL,VOICE:' + C['tel'],
    'EMAIL;TYPE=WORK,INTERNET:' + C['email'],
    'URL;TYPE=WORK:' + C['site'],
    'X-SOCIALPROFILE;TYPE=linkedin:' + C['li'],
    # item-grouped URLs give iOS a real label instead of "url".
    'item1.URL:' + C['cal'],  'item1.X-ABLabel:Book a Meeting',
    'item2.URL:' + C['li'],   'item2.X-ABLabel:LinkedIn',
    'item3.URL:' + C['card'], 'item3.X-ABLabel:Digital Card',
    'ADR;TYPE=WORK:;;;Knoxville;TN;;USA',
    'NOTE:' + C['note'],
]

lines = []
for p in props:
    lines.extend(fold(p))

_full = Image.open(PHOTO).convert('RGB').resize((FULL_PHOTO_SIZE, FULL_PHOTO_SIZE), Image.LANCZOS)
_buf = io.BytesIO()
_full.save(_buf, 'JPEG', quality=FULL_PHOTO_QUALITY, optimize=True)
print(f'full-card photo: {FULL_PHOTO_SIZE}x{FULL_PHOTO_SIZE} @ quality {FULL_PHOTO_QUALITY} -> '
      f'{len(_buf.getvalue())} bytes jpeg')
photo = base64.b64encode(_buf.getvalue()).decode()
# vCard 3.0 base64: break immediately after the property colon, then one
# leading space on every continuation line.
lines.append('PHOTO;TYPE=JPEG;ENCODING=b:')
lines.extend(' ' + c for c in textwrap.wrap(photo, 74))
lines.append('END:VCARD')
write('drew-sparks.vcf', lines)

# --- Minified card: fields kept short, plus a heavily compressed photo sized
#     to fit a QR code. This is what the Contact QR encodes, so it has to work
#     with zero network -- that is the entire reason it exists. ---
min_skeleton = [
    'BEGIN:VCARD', 'VERSION:3.0',
    'N:' + C['n'], 'FN:' + C['fn'], 'ORG:DriverLanding', 'TITLE:' + C['title'],
    'TEL;TYPE=CELL:' + C['tel_e164'], 'EMAIL:' + C['email'],
    'URL:' + C['card'],
]
min_lines = fit_photo_for_qr(min_skeleton)
write('drew-sparks.min.vcf', min_lines)
patch_index_html(min_lines, C['card'])
