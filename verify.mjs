/* Consistency guard. Run after editing contact details:
 *     node verify.mjs
 *
 * Contact info lives in three places that must agree — build-vcf.py (the
 * source), the .vcf files it emits, and the VCARD string inlined in
 * index.html. A mismatch is silent and nasty: the QR someone scans would
 * hand them different details from the card they download.
 */
import fs from 'fs';

const html = fs.readFileSync('index.html', 'utf8');
const g = {};
new Function('globalThis', fs.readFileSync('qr.js', 'utf8')).call(g, g);

let failures = 0;
const check = (label, ok, detail) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label}${detail ? '  — ' + detail : ''}`);
  if (!ok) failures++;
};

const CARD_URL = html.match(/var CARD_URL = '([^']+)'/)[1];
const block = html.match(/var VCARD = \[([\s\S]*?)\]\.join/)[1];
const inlined = eval('[' + block + ']').join('\r\n') + '\r\n';
const onDisk = fs.readFileSync('drew-sparks.min.vcf', 'utf8');
const full = fs.readFileSync('drew-sparks.vcf', 'utf8');

check('inlined VCARD matches drew-sparks.min.vcf', inlined === onDisk);
check('full vCard carries the same card URL', full.includes(CARD_URL));
check('card URL is the canonical www + trailing slash form',
      /^https:\/\/www\.driverlanding\.com\/card\/$/.test(CARD_URL), CARD_URL);

/* Every line of a vCard must fit 75 octets, continuations prefixed by a space. */
const longLines = full.split('\r\n').filter((l) => Buffer.byteLength(l, 'utf8') > 75);
check('all vCard lines fold to <= 75 octets', longLines.length === 0,
      longLines.length ? `${longLines.length} long line(s)` : '');

/* The photo must survive unfolding. */
const unfolded = [];
for (const line of full.split('\r\n')) {
  if (line.startsWith(' ') && unfolded.length) unfolded[unfolded.length - 1] += line.slice(1);
  else unfolded.push(line);
}
const photo = unfolded.find((l) => l.startsWith('PHOTO'));
const jpeg = photo ? Buffer.from(photo.split(':')[1], 'base64') : Buffer.alloc(0);
check('embedded photo unfolds to a valid JPEG', jpeg[0] === 0xff && jpeg[1] === 0xd8,
      `${jpeg.length} bytes`);

/* Both codes must encode, and stay a sane size to scan off a phone screen. */
const u = g.QR.encode(CARD_URL, 'Q');
const v = g.QR.encode(inlined, 'M');
check('link QR encodes', true, `v${u.version}, ${u.size} modules`);
check('contact QR encodes', true, `v${v.version}, ${v.size} modules`);
check('contact QR stays under 65 modules', v.size <= 65, `${v.size} modules`);

/* Every asset the service worker precaches has to exist, or install() rejects
   and the card silently loses offline support. Read the ASSETS array only —
   scanning the whole file also picks up navigation targets like
   './index.html?view=qr', which are URLs rather than files on disk. */
const sw = fs.readFileSync('sw.js', 'utf8');
const assetBlock = sw.match(/const ASSETS = \[([\s\S]*?)\];/);
check('service worker declares a precache list', !!assetBlock);
const assets = assetBlock
  ? [...assetBlock[1].matchAll(/'\.\/([^']*)'/g)].map((m) => m[1]).filter(Boolean)
  : [];
const missing = assets.filter((a) => !fs.existsSync(a));
check(`all ${assets.length} precache assets exist`, missing.length === 0, missing.join(', '));

/* Icons. These only misbehave on a real handset — a clipped maskable or a blob
   of a badge is invisible from here — so the declarations get checked instead. */
const manifest = JSON.parse(fs.readFileSync('manifest.json', 'utf8'));
const icons = manifest.icons ?? [];
const purposes = icons.map((i) => i.purpose);

check('manifest declares each icon purpose separately',
      ['any', 'maskable', 'monochrome'].every((p) => purposes.includes(p)),
      purposes.join(' | '));

/* "any maskable" on one file is the classic mistake: the launcher masks art
   that was never laid out for it, and the corners go. */
check('no icon claims both any and maskable',
      !purposes.some((p) => p && p.includes('any') && p.includes('maskable')));

const missingIcons = icons.map((i) => i.src).filter((src) => !fs.existsSync(src));
check(`all ${icons.length} declared icons exist`, missingIcons.length === 0, missingIcons.join(', '));

/* Android draws the badge from the alpha channel only. */
const badge = html.match(/badge:\s*'([^']+)'/)?.[1] ?? '';
check('notification badge uses the monochrome art',
      /monochrome|badge/.test(badge) && fs.existsSync(badge), badge);

/* The shortcut and notification both navigate here; a typo would send them to
   a 404 that only shows up on a phone, at a conference. */
const shortcutUrl = manifest.shortcuts?.[0]?.url ?? '';
check('manifest shortcut points at an existing page',
      fs.existsSync(shortcutUrl.split('?')[0].replace('./', '')), shortcutUrl);
check('page handles the ?view=qr the shortcut uses', /view=qr/.test(html));

console.log(failures ? `\n${failures} check(s) failed` : '\nall checks passed');
process.exit(failures ? 1 : 0);
