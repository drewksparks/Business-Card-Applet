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

PHOTO = 'assets/vcard-photo.jpg'          # 400x400 master
INDEX_HTML = 'index.html'

# The downloadable card is fetched over the network like any file, so its photo
# is only limited by taste. 300px matches what the pre-DriverLanding card
# shipped, at ~11KB.
FULL_PHOTO_SIZE = 300
FULL_PHOTO_QUALITY = 72

# The minified card carries NO photo, deliberately.
#
# A 96x96 thumbnail was tried and reverted: it pushed the QR from 57 to 149
# modules, and real-world scanning got noticeably harder -- enough that the
# picture was not worth it. A simulation had suggested the density was fine;
# scanning it on an actual phone in an actual room said otherwise, and that is
# the measurement that counts.
#
# Keeping this text-only holds the code at version 10 / 57 modules, which is
# 3.3 CSS pixels per module at the 200px it renders at -- chunky and forgiving.
# For a contact photo offline, the Send Contact button shares the full .vcf
# (with its 300px photo) straight to a nearby phone instead; see README.
QR_ECL = 'M'

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

# --- Minified card: text only, kept small so the QR stays easy to scan. This
#     is what the Contact QR encodes. ---
min_lines = [
    'BEGIN:VCARD', 'VERSION:3.0',
    'N:' + C['n'], 'FN:' + C['fn'], 'ORG:DriverLanding', 'TITLE:' + C['title'],
    'TEL;TYPE=CELL:' + C['tel_e164'], 'EMAIL:' + C['email'],
    'URL:' + C['card'], 'END:VCARD',
]
write('drew-sparks.min.vcf', min_lines)
patch_index_html(min_lines, C['card'])
