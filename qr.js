/* qr.js — minimal, dependency-free QR encoder (byte mode, versions 1–40).
   Replaces the old CDN-hosted qrcodejs so the card renders with no network.
   Renders to SVG rather than canvas: crisp at any size, and safe to scale up
   for someone scanning across a table.
   Implements ISO/IEC 18004. Validated module-for-module against segno. */
(function (global) {
  'use strict';

  /* ---- GF(256), primitive polynomial x^8 + x^4 + x^3 + x^2 + 1 ---- */
  var EXP = new Uint8Array(512), LOG = new Uint8Array(256);
  (function () {
    for (var i = 0, x = 1; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11d; }
    for (var j = 255; j < 512; j++) EXP[j] = EXP[j - 255];
  })();
  function mul(a, b) { return (a === 0 || b === 0) ? 0 : EXP[LOG[a] + LOG[b]]; }

  /* ---- Error-correction structure, indexed [level][version] ---- */
  var ECL = { L: 0, M: 1, Q: 2, H: 3 };
  var ECL_FORMAT_BITS = [1, 0, 3, 2];

  var ECC_PER_BLOCK = [
    [0, 7,10,15,20,26,18,20,24,30,18,20,24,26,30,22,24,28,30,28,28,28,28,30,30,26,28,30,30,30,30,30,30,30,30,30,30,30,30,30,30],
    [0,10,16,26,18,24,16,18,22,22,26,30,22,22,24,24,28,28,26,26,26,26,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28],
    [0,13,22,18,26,18,24,18,22,20,24,28,26,24,20,30,24,28,28,26,30,28,30,30,30,30,28,30,30,30,30,30,30,30,30,30,30,30,30,30,30],
    [0,17,28,22,16,22,28,26,26,24,28,24,28,22,24,24,30,28,28,26,28,30,24,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30]
  ];
  var NUM_BLOCKS = [
    [0,1,1,1,1,1,2,2,2,2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9,10,12,12,12,13,14,15,16,17,18,19,19,20,21,22,24,25],
    [0,1,1,1,2,2,4,4,4,5, 5, 5, 8, 9, 9,10,10,11,13,14,16,17,17,18,20,21,23,25,26,28,29,31,33,35,37,38,40,43,45,47,49],
    [0,1,1,2,2,4,4,6,6,8, 8, 8,10,12,16,12,17,16,18,21,20,23,23,25,27,29,34,34,35,38,40,43,45,48,51,53,56,59,62,65,68],
    [0,1,1,2,4,4,4,5,6,8, 8,11,11,16,16,18,16,19,21,25,25,25,34,30,32,35,37,40,42,45,48,51,54,57,60,63,66,70,74,77,81]
  ];

  /* Raw data modules available at a version, before EC is subtracted. */
  function rawDataModules(ver) {
    var n = (16 * ver + 128) * ver + 64;
    if (ver >= 2) {
      var na = Math.floor(ver / 7) + 2;
      n -= (25 * na - 10) * na - 55;
      if (ver >= 7) n -= 36;
    }
    return n;
  }
  function dataCodewords(ver, ecl) {
    return Math.floor(rawDataModules(ver) / 8) - ECC_PER_BLOCK[ecl][ver] * NUM_BLOCKS[ecl][ver];
  }

  function alignPositions(ver) {
    if (ver === 1) return [];
    var na = Math.floor(ver / 7) + 2, size = ver * 4 + 17;
    var step = (ver === 32) ? 26 : Math.ceil((ver * 4 + 4) / (na * 2 - 2)) * 2;
    var out = [6];
    for (var pos = size - 7; out.length < na; pos -= step) out.splice(1, 0, pos);
    return out;
  }

  /* ---- Reed–Solomon ---- */
  function genPoly(deg) {
    var poly = new Uint8Array([1]);
    for (var i = 0; i < deg; i++) {
      var next = new Uint8Array(poly.length + 1);
      for (var j = 0; j < poly.length; j++) {
        next[j] ^= poly[j];
        next[j + 1] ^= mul(poly[j], EXP[i]);
      }
      poly = next;
    }
    return poly;
  }
  function rsRemainder(data, ecLen) {
    var gen = genPoly(ecLen), res = new Uint8Array(ecLen);
    for (var i = 0; i < data.length; i++) {
      var factor = data[i] ^ res[0];
      res.copyWithin(0, 1); res[ecLen - 1] = 0;
      for (var j = 0; j < ecLen; j++) res[j] ^= mul(gen[j + 1], factor);
    }
    return res;
  }

  /* ---- Bit buffer ---- */
  function appendBits(bb, val, len) {
    for (var i = len - 1; i >= 0; i--) bb.push((val >>> i) & 1);
  }

  function encode(text, eclName) {
    var ecl = ECL[eclName || 'M'];
    if (ecl === undefined) throw new Error('bad EC level: ' + eclName);
    var bytes = new TextEncoder().encode(text);

    /* Smallest version that fits. */
    var ver = 0;
    for (var v = 1; v <= 40; v++) {
      var ccBits = v < 10 ? 8 : 16;
      if (bytes.length < (1 << ccBits) && 4 + ccBits + 8 * bytes.length <= dataCodewords(v, ecl) * 8) { ver = v; break; }
    }
    if (!ver) throw new Error('data too long for a QR code');

    var numData = dataCodewords(ver, ecl), capBits = numData * 8;
    var bb = [];
    appendBits(bb, 4, 4);                              // byte mode
    appendBits(bb, bytes.length, ver < 10 ? 8 : 16);   // character count
    for (var i = 0; i < bytes.length; i++) appendBits(bb, bytes[i], 8);
    appendBits(bb, 0, Math.min(4, capBits - bb.length));   // terminator
    appendBits(bb, 0, (8 - bb.length % 8) % 8);            // byte-align
    for (var pad = 0xEC; bb.length < capBits; pad ^= 0xEC ^ 0x11) appendBits(bb, pad, 8);

    var dat = new Uint8Array(numData);
    for (var b = 0; b < bb.length; b++) dat[b >>> 3] |= bb[b] << (7 - (b & 7));

    return buildMatrix(ver, ecl, interleave(dat, ver, ecl));
  }

  /* Split into blocks, append EC, then interleave per spec.
     Short blocks get a placeholder byte so every block is the same length;
     the interleave loop skips that one position. Without the placeholder the
     skip lands on a real EC codeword instead. */
  function interleave(data, ver, ecl) {
    var numBlocks = NUM_BLOCKS[ecl][ver], ecLen = ECC_PER_BLOCK[ecl][ver];
    var totalCw = Math.floor(rawDataModules(ver) / 8);
    var shortLen = Math.floor(totalCw / numBlocks) - ecLen;   // data bytes in a short block
    var numShort = numBlocks - totalCw % numBlocks;

    var blocks = [], k = 0;
    for (var i = 0; i < numBlocks; i++) {
      var len = shortLen + (i < numShort ? 0 : 1);
      var d = data.slice(k, k + len); k += len;
      var ec = rsRemainder(d, ecLen);
      var full = new Uint8Array(shortLen + 1 + ecLen);        // uniform length
      full.set(d);
      full.set(ec, shortLen + 1);                             // EC always starts past the placeholder
      blocks.push(full);
    }

    var out = new Uint8Array(totalCw), o = 0;
    for (var c = 0; c < shortLen + 1 + ecLen; c++) {
      for (var bi = 0; bi < numBlocks; bi++) {
        if (c === shortLen && bi < numShort) continue;        // skip the placeholder
        out[o++] = blocks[bi][c];
      }
    }
    return out;
  }

  function buildMatrix(ver, ecl, codewords) {
    var size = ver * 4 + 17;
    var mod = [], fn = [];
    for (var y = 0; y < size; y++) { mod.push(new Uint8Array(size)); fn.push(new Uint8Array(size)); }

    function setFn(x, y, v) { mod[y][x] = v ? 1 : 0; fn[y][x] = 1; }

    /* Timing patterns */
    for (var i = 0; i < size; i++) { setFn(6, i, i % 2 === 0); setFn(i, 6, i % 2 === 0); }

    /* Finder patterns + separators */
    [[3, 3], [size - 4, 3], [3, size - 4]].forEach(function (p) {
      for (var dy = -4; dy <= 4; dy++) for (var dx = -4; dx <= 4; dx++) {
        var d = Math.max(Math.abs(dx), Math.abs(dy)), xx = p[0] + dx, yy = p[1] + dy;
        if (xx >= 0 && xx < size && yy >= 0 && yy < size) setFn(xx, yy, d !== 2 && d !== 4);
      }
    });

    /* Alignment patterns, minus the three finder corners */
    var ap = alignPositions(ver), n = ap.length;
    for (var a = 0; a < n; a++) for (var b2 = 0; b2 < n; b2++) {
      if ((a === 0 && b2 === 0) || (a === 0 && b2 === n - 1) || (a === n - 1 && b2 === 0)) continue;
      for (var ddy = -2; ddy <= 2; ddy++) for (var ddx = -2; ddx <= 2; ddx++)
        setFn(ap[b2] + ddx, ap[a] + ddy, Math.max(Math.abs(ddx), Math.abs(ddy)) !== 1);
    }

    function drawFormat(mask) {
      var d = ECL_FORMAT_BITS[ecl] << 3 | mask, rem = d;
      for (var i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
      var bits = ((d << 10) | rem) ^ 0x5412;
      function bit(k) { return (bits >>> k) & 1; }
      for (var j = 0; j <= 5; j++) setFn(8, j, bit(j));
      setFn(8, 7, bit(6)); setFn(8, 8, bit(7)); setFn(7, 8, bit(8));
      for (var m = 9; m < 15; m++) setFn(14 - m, 8, bit(m));
      for (var p = 0; p < 8; p++) setFn(size - 1 - p, 8, bit(p));
      for (var q = 8; q < 15; q++) setFn(8, size - 15 + q, bit(q));
      setFn(8, size - 8, 1);   // always-dark module
    }
    drawFormat(0);

    if (ver >= 7) {
      var rem2 = ver;
      for (var r = 0; r < 12; r++) rem2 = (rem2 << 1) ^ ((rem2 >>> 11) * 0x1F25);
      var vbits = ver << 12 | rem2;
      for (var vi = 0; vi < 18; vi++) {
        var vb = (vbits >>> vi) & 1, aa = size - 11 + vi % 3, bb2 = Math.floor(vi / 3);
        setFn(aa, bb2, vb); setFn(bb2, aa, vb);
      }
    }

    /* Zigzag codeword placement, skipping the vertical timing column */
    var bitIdx = 0;
    for (var right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (var vert = 0; vert < size; vert++) {
        for (var jj = 0; jj < 2; jj++) {
          var x = right - jj, upward = ((right + 1) & 2) === 0;
          var yy2 = upward ? size - 1 - vert : vert;
          if (!fn[yy2][x] && bitIdx < codewords.length * 8) {
            mod[yy2][x] = (codewords[bitIdx >>> 3] >>> (7 - (bitIdx & 7))) & 1;
            bitIdx++;
          }
        }
      }
    }

    var MASKS = [
      function (y, x) { return (x + y) % 2 === 0; },
      function (y) { return y % 2 === 0; },
      function (y, x) { return x % 3 === 0; },
      function (y, x) { return (x + y) % 3 === 0; },
      function (y, x) { return (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0; },
      function (y, x) { return x * y % 2 + x * y % 3 === 0; },
      function (y, x) { return (x * y % 2 + x * y % 3) % 2 === 0; },
      function (y, x) { return ((x + y) % 2 + x * y % 3) % 2 === 0; }
    ];

    function applyMask(m) {
      for (var y = 0; y < size; y++) for (var x = 0; x < size; x++)
        if (!fn[y][x] && MASKS[m](y, x)) mod[y][x] ^= 1;
    }

    /* Pick the mask with the lowest penalty, per spec. */
    var best = -1, bestScore = Infinity;
    for (var m2 = 0; m2 < 8; m2++) {
      applyMask(m2); drawFormat(m2);
      var s = penalty(mod, size);
      if (s < bestScore) { bestScore = s; best = m2; }
      applyMask(m2);   // masks are involutive — undo
    }
    applyMask(best); drawFormat(best);

    return { size: size, version: ver, mask: best, modules: mod };
  }

  function penalty(mod, size) {
    var N1 = 3, N2 = 3, N3 = 40, N4 = 10, score = 0, x, y;

    /* Rule 1 — runs of 5+ same-colour modules, both directions */
    for (y = 0; y < size; y++) {
      var runColor = mod[y][0], runLen = 1;
      for (x = 1; x < size; x++) {
        if (mod[y][x] === runColor) { runLen++; if (runLen === 5) score += N1; else if (runLen > 5) score++; }
        else { runColor = mod[y][x]; runLen = 1; }
      }
    }
    for (x = 0; x < size; x++) {
      var rc = mod[0][x], rl = 1;
      for (y = 1; y < size; y++) {
        if (mod[y][x] === rc) { rl++; if (rl === 5) score += N1; else if (rl > 5) score++; }
        else { rc = mod[y][x]; rl = 1; }
      }
    }

    /* Rule 2 — 2x2 blocks of one colour */
    for (y = 0; y < size - 1; y++) for (x = 0; x < size - 1; x++) {
      var c = mod[y][x];
      if (c === mod[y][x + 1] && c === mod[y + 1][x] && c === mod[y + 1][x + 1]) score += N2;
    }

    /* Rule 3 — finder-like 1:1:3:1:1 patterns with a 4-module quiet run */
    var P = [1, 0, 1, 1, 1, 0, 1], Q4 = [0, 0, 0, 0];
    function matches(get, at, pat) {
      for (var i = 0; i < pat.length; i++) if (get(at + i) !== pat[i]) return false;
      return true;
    }
    for (y = 0; y < size; y++) for (x = 0; x < size; x++) {
      var row = (function (yy) { return function (i) { return (i < 0 || i >= size) ? -1 : mod[yy][i]; }; })(y);
      var col = (function (xx) { return function (i) { return (i < 0 || i >= size) ? -1 : mod[i][xx]; }; })(x);
      if (matches(row, x, P) && (matches(row, x - 4, Q4) || matches(row, x + 7, Q4))) score += N3;
      if (matches(col, y, P) && (matches(col, y - 4, Q4) || matches(col, y + 7, Q4))) score += N3;
    }

    /* Rule 4 — deviation from 50% dark */
    var dark = 0;
    for (y = 0; y < size; y++) for (x = 0; x < size; x++) dark += mod[y][x];
    var total = size * size;
    var k = Math.floor(Math.abs(dark * 20 - total * 10) / total);
    score += k * N4;

    return score;
  }

  /* Render as a single SVG path — one DOM node, scales cleanly. */
  function toSVG(text, opts) {
    opts = opts || {};
    var q = opts.quiet === undefined ? 4 : opts.quiet;
    var dark = opts.dark || '#000000';
    var light = opts.light || '#ffffff';
    var r = encode(text, opts.ecl || 'M');
    var dim = r.size + q * 2, d = '';
    for (var y = 0; y < r.size; y++) for (var x = 0; x < r.size; x++)
      if (r.modules[y][x]) d += 'M' + (x + q) + ' ' + (y + q) + 'h1v1h-1z';
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + dim + ' ' + dim + '" ' +
      'shape-rendering="crispEdges" role="img" aria-label="' + (opts.label || 'QR code') + '">' +
      '<rect width="' + dim + '" height="' + dim + '" fill="' + light + '"/>' +
      '<path d="' + d + '" fill="' + dark + '"/></svg>';
  }

  global.QR = { encode: encode, toSVG: toSVG };
})(typeof window !== 'undefined' ? window : globalThis);
