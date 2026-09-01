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

/* Unfolds a vCard's physical lines back to logical properties, per RFC 2425:
   a line starting with a single space is a continuation of the previous one. */
const unfold = (text) => {
  const out = [];
  for (const line of text.split('\r\n')) {
    if (line.startsWith(' ') && out.length) out[out.length - 1] += line.slice(1);
    else out.push(line);
  }
  return out;
};

const photoOf = (text) => {
  const line = unfold(text).find((l) => l.startsWith('PHOTO'));
  return line ? Buffer.from(line.split(':')[1], 'base64') : Buffer.alloc(0);
};

const isJpeg = (buf) => buf[0] === 0xff && buf[1] === 0xd8;

const fullPhoto = photoOf(full);
check('full vCard photo unfolds to a valid JPEG', isJpeg(fullPhoto), `${fullPhoto.length} bytes`);

/* The QR-embedded photo is the whole reason the min vCard exists: it is what
   makes the Contact QR work with zero network. If this photo were ever
   missing or corrupt, the QR would still encode fine -- only a phone actually
   scanning it would ever notice, at a conference, with no way to fall back. */
const minPhoto = photoOf(onDisk);
check('QR-embedded photo is present', minPhoto.length > 0, `${minPhoto.length} bytes`);
check('QR-embedded photo unfolds to a valid JPEG', isJpeg(minPhoto), `${minPhoto.length} bytes`);

/* EC levels are read out of index.html rather than hardcoded here, so this
   check tracks whatever renderQR() actually requests instead of silently
   testing a level the page no longer uses. */
const eclMatch = html.match(/ecl:\s*isUrl\s*\?\s*'([A-Z])'\s*:\s*'([A-Z])'/);
check('renderQR EC levels are readable from index.html', !!eclMatch);
const [, urlEcl, vcardEcl] = eclMatch ?? [, 'Q', 'L'];

/* Both codes must encode, and stay a sane size to scan off a phone screen. */
const u = g.QR.encode(CARD_URL, urlEcl);
const v = g.QR.encode(inlined, vcardEcl);
check('link QR encodes', true, `v${u.version}, ${u.size} modules, EC ${urlEcl}`);
check('contact QR encodes', true, `v${v.version}, ${v.size} modules, EC ${vcardEcl}`);
/* 145 modules is roughly version 32 -- comfortably inside what qr.js's own
   validation proved reliable (284/284 payloads through zxing-cpp up to
   version 40). The photo is fit to a byte budget in build-vcf.py specifically
   to stay well under this; this check exists to catch a future edit to that
   budget (or to the contact fields) creeping the code past a size that is
   still easy to scan off a phone screen, not to police the current number. */
check('contact QR stays under 145 modules', v.size <= 145, `${v.size} modules`);

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

/* The host sends Cache-Control: max-age=7200 on everything (a Bluehost
   default, not set by this project's .htaccess). A plain fetch() in the SW
   would honor that and silently hand back the browser's own stale HTTP cache
   instead of asking the server for anything -- discovered when a real deploy
   took two reloads to show up. Both fetch paths must force past it, or a
   future edit here could quietly reintroduce a redeploy delay of up to two
   hours with no error anywhere to notice it by. */
check('install-time precache bypasses the host\'s HTTP cache',
      /new Request\(url, \{ cache: 'reload' \}\)/.test(sw));
check('same-origin revalidation bypasses the host\'s HTTP cache',
      /fetch\(req, \{ cache: 'reload' \}\)/.test(sw));

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
