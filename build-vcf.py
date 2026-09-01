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

PHOTO = 'assets/vcard-photo.jpg'
INDEX_HTML = 'index.html'

# The minified card's photo is sized to fit inside a QR code someone scans off
# a phone screen with no network -- there is no server round trip to fall back
# to, so this budget IS the image quality. 1450 bytes leaves ~80 bytes of slack
# under the 1465-byte cap of a version-27 code at EC level L (see qr.js), so a
# future edit to a phone number or email does not silently jump the QR to the
# next version tier. EC level L, not M or Q: this is scanned off a lit screen
# at close range, the easiest condition a QR reader ever sees, so the extra
# error-correction those levels spend is better spent as photo bytes instead.
QR_PHOTO_SIZE = 56
QR_PHOTO_BUDGET = 1450
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


def fit_photo_for_qr(skeleton, path=PHOTO, size=QR_PHOTO_SIZE, budget=QR_PHOTO_BUDGET):
    """Binary-searches JPEG quality for the largest, best-looking thumbnail that
    still keeps the finished vCard under `budget` bytes once folded."""
    src = Image.open(path).convert('RGB').resize((size, size), Image.LANCZOS)

    def assemble(quality):
        buf = io.BytesIO()
        src.save(buf, 'JPEG', quality=quality, optimize=True)
        jpeg = buf.getvalue()
        b64 = base64.b64encode(jpeg).decode()
        lines = list(skeleton)
        lines.append('PHOTO;TYPE=JPEG;ENCODING=b:')
        lines.extend(' ' + c for c in textwrap.wrap(b64, 74))
        lines.append('END:VCARD')
        folded = []
        for l in lines:
            folded.extend(fold(l))
        total = len(('\r\n'.join(folded) + '\r\n').encode('utf-8'))
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
          f'{total} bytes total (budget {budget}, EC level {QR_PHOTO_ECL})')
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

photo = base64.b64encode(open(PHOTO, 'rb').read()).decode()
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
