#!/usr/bin/env python3
"""Regenerates drew-sparks.vcf and drew-sparks.min.vcf.

Contact details live here, in index.html's CONTACT rows, and in the VCARD
string inlined in index.html's script. Change one, change all three -- the
inlined string must stay byte-identical to drew-sparks.min.vcf or the Contact
QR and the downloaded card will disagree.

    python3 build-vcf.py
"""
import base64, os, textwrap

PHOTO = 'assets/vcard-photo.jpg'

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


# --- Full card: every field plus the photo. This is the download target. ---
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

# --- Minified card: no photo, no labels, kept small so the QR stays low
#     density and scans quickly. Must match the VCARD string in index.html. ---
write('drew-sparks.min.vcf', [
    'BEGIN:VCARD', 'VERSION:3.0',
    'N:' + C['n'], 'FN:' + C['fn'], 'ORG:DriverLanding', 'TITLE:' + C['title'],
    'TEL;TYPE=CELL:' + C['tel_e164'], 'EMAIL:' + C['email'],
    'URL:' + C['card'], 'END:VCARD',
])
