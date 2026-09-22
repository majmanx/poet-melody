/* poet-melody browser engine.
 *
 * A faithful JavaScript port of the Python package `poet_melody` (theory,
 * analysis, tones, progressions, styles, interpret, melody, synth, compose,
 * score, midi). Text (Chinese / English letters, poems) -> Composition JSON
 * with the exact shape of `Composition.to_dict()`, plus a type-1 MIDI writer.
 *
 * Plain browser script: no build step, no imports, ES2019 only. Exposes
 * `window.PoetMelody`. Requires `web/tones.js` (`window.POET_TONES`) for the
 * Mandarin tone table; without it every tone is 0 (unknown).
 *
 * Seeding: the piece is seeded from the SHA-256 of the text (same as Python),
 * but the pseudo-random generator is sfc32 rather than Python's Mersenne
 * Twister, so pieces are deterministic here but not bit-identical to Python.
 */
(function (root) {
  'use strict';

  var VERSION = '0.1.0';

  // =========================================================================
  // Small Python-compatibility helpers
  // =========================================================================
  function mod(a, n) { return ((a % n) + n) % n; }

  // Python round(): round half to even.
  function pyRound(x) {
    var f = Math.floor(x), d = x - f;
    if (d < 0.5) return f;
    if (d > 0.5) return f + 1;
    return (f % 2 === 0) ? f : f + 1;
  }
  function roundN(x, n) {
    var m = Math.pow(10, n);
    var v = pyRound(x * m) / m;
    return Object.is(v, -0) ? 0 : v;
  }
  // Python format spec ':.nf' (half-even on exact ties, like repr-based rounding).
  function fixed(x, n) {
    var m = Math.pow(10, n), s = x * m;
    var r = (Math.abs(s - Math.trunc(s)) === 0.5) ? pyRound(s) : Math.round(s);
    var v = r / m;
    var out = v.toFixed(n);
    if (out === '-0' || /^-0\.0*$/.test(out)) out = out.slice(1);
    return out;
  }
  // Python format spec ':g'.
  function fmtG(x) {
    if (Number.isInteger(x)) return String(x);
    var s = x.toPrecision(6);
    if (s.indexOf('e') >= 0) return String(Number(s));
    return String(Number(s));
  }
  // Python format spec ':+d'.
  function fmtSigned(n) { return (n >= 0 ? '+' : '') + String(n); }
  function pct0(x) { return fixed(x * 100, 0) + '%'; }

  function sum(arr) { var s = 0; for (var i = 0; i < arr.length; i++) s += arr[i]; return s; }
  function maxOf(arr) { var m = -Infinity; for (var i = 0; i < arr.length; i++) if (arr[i] > m) m = arr[i]; return m; }
  function minOf(arr) { var m = Infinity; for (var i = 0; i < arr.length; i++) if (arr[i] < m) m = arr[i]; return m; }
  function uniq(arr) { var out = []; for (var i = 0; i < arr.length; i++) if (out.indexOf(arr[i]) < 0) out.push(arr[i]); return out; }
  function includes(arr, x) { return arr.indexOf(x) >= 0; }
  function chars(s) { return Array.from(s); }
  function clamp(x, lo, hi) { return Math.min(hi, Math.max(lo, x)); }
  function assign(target, src) { for (var k in src) if (Object.prototype.hasOwnProperty.call(src, k)) target[k] = src[k]; return target; }
  function copy(o) { return assign({}, o); }
  function deepCopy(o) { return JSON.parse(JSON.stringify(o)); }
  function utf8(str) {
    if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(str);
    var out = [], s = unescape(encodeURIComponent(str));
    for (var i = 0; i < s.length; i++) out.push(s.charCodeAt(i));
    return new Uint8Array(out);
  }

  // =========================================================================
  // SHA-256 (for text / token seeds, same values as Python's hashlib)
  // =========================================================================
  var K256 = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];

  function sha256(bytes) {
    var h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var len = bytes.length, bitLen = len * 8;
    var padded = new Uint8Array(((len + 9 + 63) >> 6) << 6);
    padded.set(bytes);
    padded[len] = 0x80;
    var dv = new DataView(padded.buffer);
    dv.setUint32(padded.length - 8, Math.floor(bitLen / 0x100000000));
    dv.setUint32(padded.length - 4, bitLen >>> 0);
    var w = new Array(64);
    for (var off = 0; off < padded.length; off += 64) {
      for (var i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
      for (i = 16; i < 64; i++) {
        var w15 = w[i - 15], w2 = w[i - 2];
        var s0 = ((w15 >>> 7) | (w15 << 25)) ^ ((w15 >>> 18) | (w15 << 14)) ^ (w15 >>> 3);
        var s1 = ((w2 >>> 17) | (w2 << 15)) ^ ((w2 >>> 19) | (w2 << 13)) ^ (w2 >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
      for (i = 0; i < 64; i++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var ch = (e & f) ^ (~e & g);
        var t1 = (hh + S1 + ch + K256[i] + w[i]) >>> 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) >>> 0;
        hh = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      h[0] = (h[0] + a) >>> 0; h[1] = (h[1] + b) >>> 0; h[2] = (h[2] + c) >>> 0; h[3] = (h[3] + d) >>> 0;
      h[4] = (h[4] + e) >>> 0; h[5] = (h[5] + f) >>> 0; h[6] = (h[6] + g) >>> 0; h[7] = (h[7] + hh) >>> 0;
    }
    return h;
  }
  // First 4 bytes big-endian of sha256(utf8) as an unsigned 32-bit int (= Python text_seed / token_seed).
  function seedOf(str) { return sha256(utf8(str))[0] >>> 0; }

  // =========================================================================
  // Seeded PRNG (sfc32) with a random.Random-like API
  // =========================================================================
  function Random(seed) {
    seed = seed >>> 0;
    // Expand the 32-bit seed into four state words with splitmix-style mixing.
    var s = seed;
    function next() {
      s = (s + 0x9e3779b9) >>> 0;
      var z = s;
      z = Math.imul(z ^ (z >>> 16), 0x85ebca6b) >>> 0;
      z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35) >>> 0;
      return (z ^ (z >>> 16)) >>> 0;
    }
    this.a = next(); this.b = next(); this.c = next(); this.d = next();
    this.gaussNext = null;
    for (var i = 0; i < 12; i++) this.uint32();
  }
  Random.prototype.uint32 = function () {
    var a = this.a, b = this.b, c = this.c, d = this.d;
    var t = (a + b) >>> 0;
    t = (t + d) >>> 0;
    d = (d + 1) >>> 0;
    a = b ^ (b >>> 9);
    b = (c + (c << 3)) >>> 0;
    c = ((c << 21) | (c >>> 11)) >>> 0;
    c = (c + t) >>> 0;
    this.a = a >>> 0; this.b = b; this.c = c; this.d = d;
    return t;
  };
  // 53-bit float in [0, 1) like Python's random().
  Random.prototype.random = function () {
    var hi = this.uint32() >>> 5, lo = this.uint32() >>> 6;
    return (hi * 67108864 + lo) / 9007199254740992;
  };
  Random.prototype.uniform = function (a, b) { return a + (b - a) * this.random(); };
  Random.prototype.randint = function (a, b) { return a + Math.floor(this.random() * (b - a + 1)); };
  Random.prototype.choice = function (seq) {
    if (!seq.length) throw new Error('choice from empty sequence');
    return seq[Math.floor(this.random() * seq.length)];
  };
  // random.choices(population, weights, k) semantics (cumulative weights + bisect_right).
  Random.prototype.choices = function (seq, weights, k) {
    k = k || 1;
    var out = [], i;
    if (!weights) {
      for (i = 0; i < k; i++) out.push(this.choice(seq));
      return out;
    }
    var cum = [], total = 0;
    for (i = 0; i < weights.length; i++) { total += weights[i]; cum.push(total); }
    if (!(total > 0)) throw new Error('total of weights must be greater than zero');
    for (i = 0; i < k; i++) {
      var r = this.random() * total, idx = 0;
      while (idx < cum.length - 1 && cum[idx] <= r) idx++;
      out.push(seq[idx]);
    }
    return out;
  };
  Random.prototype.gauss = function (mu, sigma) {
    var z = this.gaussNext;
    this.gaussNext = null;
    if (z === null) {
      var x2pi = this.random() * 2 * Math.PI;
      var g2rad = Math.sqrt(-2.0 * Math.log(1.0 - this.random()));
      z = Math.cos(x2pi) * g2rad;
      this.gaussNext = Math.sin(x2pi) * g2rad;
    }
    return mu + z * sigma;
  };
  function subRandom(rng) { return new Random(Math.floor(rng.random() * 4294967296) >>> 0); }

  // =========================================================================
  // theory.py
  // =========================================================================
  var SHARP_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  var FLAT_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
  var FLAT_KEYS = [5, 10, 3, 8, 1]; // F, Bb, Eb, Ab, Db
  var NOTE_TO_PC = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'Fb': 4, 'E#': 5,
    'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10,
    'B': 11, 'Cb': 11, 'B#': 0
  };

  var SCALES = {
    ionian: [0, 2, 4, 5, 7, 9, 11],
    dorian: [0, 2, 3, 5, 7, 9, 10],
    phrygian: [0, 1, 3, 5, 7, 8, 10],
    lydian: [0, 2, 4, 6, 7, 9, 11],
    mixolydian: [0, 2, 4, 5, 7, 9, 10],
    aeolian: [0, 2, 3, 5, 7, 8, 10],
    locrian: [0, 1, 3, 5, 6, 8, 10],
    harmonic_minor: [0, 2, 3, 5, 7, 8, 11],
    melodic_minor: [0, 2, 3, 5, 7, 9, 11],
    phrygian_dominant: [0, 1, 4, 5, 7, 8, 10],
    lydian_dominant: [0, 2, 4, 6, 7, 9, 10],
    major_pentatonic: [0, 2, 4, 7, 9],
    shang: [0, 2, 5, 7, 10],
    jue: [0, 3, 5, 8, 10],
    zhi: [0, 2, 5, 7, 9],
    minor_pentatonic: [0, 3, 5, 7, 10],
    hirajoshi: [0, 2, 3, 7, 8],
    in_sen: [0, 1, 5, 7, 10],
    blues: [0, 3, 5, 6, 7, 10],
    whole_tone: [0, 2, 4, 6, 8, 10],
    octatonic: [0, 2, 3, 5, 6, 8, 9, 11],
    chromatic: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
  };
  SCALES.major = SCALES.ionian;
  SCALES.minor = SCALES.aeolian;
  SCALES.gong = SCALES.major_pentatonic;
  SCALES.yu = SCALES.minor_pentatonic;

  var MAJOR_LIKE = ['ionian', 'major', 'lydian', 'mixolydian', 'lydian_dominant', 'major_pentatonic',
    'gong', 'zhi', 'whole_tone', 'phrygian_dominant'];
  var MINOR_LIKE = ['aeolian', 'minor', 'dorian', 'phrygian', 'locrian', 'harmonic_minor',
    'melodic_minor', 'minor_pentatonic', 'yu', 'shang', 'jue', 'hirajoshi', 'in_sen', 'blues', 'octatonic'];

  var CHORD_QUALITIES = {
    'maj': [0, 4, 7], 'min': [0, 3, 7], 'dim': [0, 3, 6], 'aug': [0, 4, 8], 'sus2': [0, 2, 7], 'sus4': [0, 5, 7],
    'power': [0, 7], '6': [0, 4, 7, 9], 'm6': [0, 3, 7, 9], '69': [0, 4, 7, 9, 14], 'maj7': [0, 4, 7, 11],
    'min7': [0, 3, 7, 10], '7': [0, 4, 7, 10], 'dim7': [0, 3, 6, 9], 'm7b5': [0, 3, 6, 10], 'minmaj7': [0, 3, 7, 11],
    'aug7': [0, 4, 8, 10], 'augmaj7': [0, 4, 8, 11], '7sus4': [0, 5, 7, 10], 'add9': [0, 4, 7, 14],
    'madd9': [0, 3, 7, 14], 'maj9': [0, 4, 7, 11, 14], 'min9': [0, 3, 7, 10, 14], '9': [0, 4, 7, 10, 14],
    '7b9': [0, 4, 7, 10, 13], '7#9': [0, 4, 7, 10, 15], 'min11': [0, 3, 7, 10, 14, 17], '11': [0, 4, 7, 10, 14, 17],
    'maj7#11': [0, 4, 7, 11, 18], '13': [0, 4, 7, 10, 14, 21], 'maj13': [0, 4, 7, 11, 14, 21],
    'min13': [0, 3, 7, 10, 14, 21]
  };
  var QUALITY_SYMBOL = {
    'maj': '', 'min': 'm', 'dim': 'dim', 'aug': 'aug', 'sus2': 'sus2', 'sus4': 'sus4', 'power': '5', '6': '6',
    'm6': 'm6', '69': '6/9', 'maj7': 'maj7', 'min7': 'm7', '7': '7', 'dim7': 'dim7', 'm7b5': 'm7b5',
    'minmaj7': 'mMaj7', 'aug7': 'aug7', 'augmaj7': 'augMaj7', '7sus4': '7sus4', 'add9': 'add9', 'madd9': 'madd9',
    'maj9': 'maj9', 'min9': 'm9', '9': '9', '7b9': '7b9', '7#9': '7#9', 'min11': 'm11', '11': '11',
    'maj7#11': 'maj7#11', '13': '13', 'maj13': 'maj13', 'min13': 'm13'
  };
  var SUFFIX_QUALITY = {
    '': ['maj', 'min'],
    '°': ['dim', 'dim'], 'o': ['dim', 'dim'], 'dim': ['dim', 'dim'],
    '°7': ['dim7', 'dim7'], 'o7': ['dim7', 'dim7'], 'dim7': ['dim7', 'dim7'],
    'ø': ['m7b5', 'm7b5'], 'ø7': ['m7b5', 'm7b5'], 'm7b5': ['m7b5', 'm7b5'], 'h7': ['m7b5', 'm7b5'],
    '+': ['aug', 'aug'], 'aug': ['aug', 'aug'], '+7': ['aug7', 'aug7'], 'aug7': ['aug7', 'aug7'],
    '7': ['7', 'min7'],
    'maj7': ['maj7', 'minmaj7'], 'M7': ['maj7', 'minmaj7'], 'Δ': ['maj7', 'minmaj7'], 'Δ7': ['maj7', 'minmaj7'],
    '9': ['9', 'min9'], 'maj9': ['maj9', 'min9'], 'M9': ['maj9', 'min9'],
    'add9': ['add9', 'madd9'],
    '6': ['6', 'm6'], '69': ['69', '69'], '6/9': ['69', '69'],
    '11': ['11', 'min11'], '13': ['13', 'min13'], 'maj13': ['maj13', 'min13'],
    'sus2': ['sus2', 'sus2'], 'sus4': ['sus4', 'sus4'], 'sus': ['sus4', 'sus4'], '7sus4': ['7sus4', '7sus4'],
    '5': ['power', 'power'],
    'maj7#11': ['maj7#11', 'maj7#11'], '7b9': ['7b9', '7b9'], '7#9': ['7#9', '7#9']
  };
  var DEGREE_RE_SRC = '(?:VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)';
  var ROMAN_RE = new RegExp('^([b#]?)(' + DEGREE_RE_SRC + ')([^/]*)(?:/([b#]?' + DEGREE_RE_SRC + '))?$');
  var SEC_RE = new RegExp('^([b#]?)(' + DEGREE_RE_SRC + ')$');
  var DEGREE_INDEX = { i: 0, ii: 1, iii: 2, iv: 3, v: 4, vi: 5, vii: 6 };

  function pcName(pc, preferFlats) { return (preferFlats ? FLAT_NAMES : SHARP_NAMES)[mod(pc, 12)]; }
  function midiName(midi, preferFlats) { return pcName(midi, preferFlats) + (Math.floor(midi / 12) - 1); }
  function scalePcs(tonic, mode) {
    if (!SCALES[mode]) throw new Error('unknown mode ' + JSON.stringify(mode));
    return SCALES[mode].map(function (i) { return mod(tonic + i, 12); });
  }
  function scalePitches(tonic, mode, low, high) {
    if (low === undefined) low = 36;
    if (high === undefined) high = 96;
    var pcs = scalePcs(tonic, mode), out = [];
    for (var p = low; p <= high; p++) if (includes(pcs, mod(p, 12))) out.push(p);
    return out;
  }
  function isMajorLike(mode) { return includes(MAJOR_LIKE, mode); }

  function Chord(root, quality, numeral, bass) {
    this.root = root;
    this.quality = quality;
    this.numeral = numeral || '';
    this.bass = (bass === undefined) ? null : bass;
  }
  Chord.prototype.intervals = function () { return CHORD_QUALITIES[this.quality]; };
  Chord.prototype.pcs = function () {
    var out = [], iv = this.intervals();
    for (var i = 0; i < iv.length; i++) {
      var pc = mod(this.root + iv[i], 12);
      if (!includes(out, pc)) out.push(pc);
    }
    return out;
  };
  // Pitch classes to voice in the pad/keys: extended chords drop the fifth first,
  // then the root (the bass supplies it), so 9th/13th chords never become clusters.
  Chord.prototype.voicingPcs = function (maxVoices) {
    if (maxVoices === undefined) maxVoices = 4;
    var pcs = this.pcs();
    if (pcs.length <= maxVoices) return pcs;
    var fifth = this.fifth();
    if (fifth !== null && pcs.length > maxVoices) pcs = pcs.filter(function (pc) { return pc !== fifth; });
    if (pcs.length > maxVoices) pcs = pcs.slice(1);
    return pcs.slice(0, maxVoices);
  };
  Chord.prototype.third = function () {
    var iv = this.intervals();
    for (var i = 0; i < iv.length; i++) if (iv[i] === 3 || iv[i] === 4) return mod(this.root + iv[i], 12);
    return null;
  };
  Chord.prototype.fifth = function () {
    var iv = this.intervals();
    for (var i = 0; i < iv.length; i++) if (iv[i] === 6 || iv[i] === 7 || iv[i] === 8) return mod(this.root + iv[i], 12);
    return null;
  };
  Chord.prototype.isMinor = function () { var iv = this.intervals(); return includes(iv, 3) && !includes(iv, 4); };
  Chord.prototype.symbol = function (preferFlats) {
    var s = pcName(this.root, preferFlats) + QUALITY_SYMBOL[this.quality];
    if (this.bass !== null && this.bass !== this.root) s += '/' + pcName(this.bass, preferFlats);
    return s;
  };
  Chord.prototype.toDict = function (preferFlats) {
    return { symbol: this.symbol(preferFlats), numeral: this.numeral, root: pcName(this.root, preferFlats),
      quality: this.quality, pcs: this.pcs() };
  };

  function parseRoman(numeral, tonic, mode) {
    var text = numeral.trim();
    var m = ROMAN_RE.exec(text);
    if (!m) throw new Error('cannot parse Roman numeral ' + JSON.stringify(numeral));
    var scale = SCALES[mode];
    if (!scale) throw new Error('unknown mode ' + JSON.stringify(mode));
    if (scale.length < 7) scale = isMajorLike(mode) ? SCALES.ionian : SCALES.aeolian;
    function degreeRoot(acc, deg) {
      var r = scale[DEGREE_INDEX[deg.toLowerCase()]];
      if (acc === 'b') r -= 1; else if (acc === '#') r += 1;
      return r;
    }
    var deg = m[2];
    var r = degreeRoot(m[1], deg);
    if (m[4]) {
      var sm = SEC_RE.exec(m[4]);
      var target = degreeRoot(sm[1], sm[2]);
      var rel = SCALES.ionian[DEGREE_INDEX[deg.toLowerCase()]];
      if (m[1] === 'b') rel -= 1; else if (m[1] === '#') rel += 1;
      r = target + rel;
    }
    var qual = m[3];
    if (!Object.prototype.hasOwnProperty.call(SUFFIX_QUALITY, qual)) {
      throw new Error('unknown chord suffix ' + JSON.stringify(qual) + ' in ' + JSON.stringify(numeral));
    }
    var pair = SUFFIX_QUALITY[qual];
    var upper = deg === deg.toUpperCase();
    return new Chord(mod(tonic + r, 12), upper ? pair[0] : pair[1], text);
  }

  function chordFromSymbol(symbol) {
    var m = /^([A-G][b#]?)(.*?)(?:\/([A-G][b#]?))?$/.exec(symbol.trim());
    if (!m) throw new Error('bad chord symbol ' + JSON.stringify(symbol));
    var root = NOTE_TO_PC[m[1]], suffix = m[2];
    var inverse = {};
    for (var k in QUALITY_SYMBOL) inverse[QUALITY_SYMBOL[k]] = k;
    assign(inverse, { 'm': 'min', 'M7': 'maj7', '-7': 'min7', 'min7': 'min7', 'maj': 'maj', 'min': 'min',
      '°': 'dim', 'ø7': 'm7b5', 'ø': 'm7b5', '+': 'aug', 'Δ7': 'maj7', 'Δ': 'maj7' });
    if (!Object.prototype.hasOwnProperty.call(inverse, suffix)) throw new Error('unknown chord suffix ' + JSON.stringify(suffix));
    var bass = m[3] ? NOTE_TO_PC[m[3]] : null;
    return new Chord(root, inverse[suffix], '', bass);
  }

  // ---- Voice leading --------------------------------------------------------
  function nearestOctave(pc, target, low, high) {
    var base = target - mod(target - pc, 12);
    var cands = [base, base + 12, base - 12].filter(function (c) { return low <= c && c <= high; });
    if (!cands.length) cands = [Math.min(Math.max(base, low), high)];
    var best = null;
    for (var i = 0; i < cands.length; i++) {
      var c = cands[i];
      if (best === null || Math.abs(c - target) < Math.abs(best - target) ||
          (Math.abs(c - target) === Math.abs(best - target) && c < best)) best = c;
    }
    return best;
  }

  function closeVoicing(chord, low, high, maxVoices) {
    if (low === undefined) low = 48;
    if (high === undefined) high = 72;
    if (maxVoices === undefined) maxVoices = 4;
    var pcs = chord.voicingPcs(maxVoices);
    var r = low + mod(pcs[0] - low, 12);
    var voicing = [r];
    for (var i = 1; i < pcs.length; i++) {
      var prev = voicing[voicing.length - 1];
      voicing.push(prev + (mod(pcs[i] - prev, 12) || 12));
    }
    // A seventh a semitone below the next voice (maj7 under the root) is opened up by
    // dropping the lower voice an octave when there is room.
    for (i = 0; i < voicing.length - 1; i++) {
      if (voicing[i + 1] - voicing[i] === 1 && voicing[i] - 12 >= low - 5) voicing[i] -= 12;
    }
    voicing.sort(function (a, b) { return a - b; });
    while (voicing.length && voicing[voicing.length - 1] > high && voicing[0] - 12 >= low - 12) {
      voicing = voicing.map(function (v) { return v - 12; });
    }
    return voicing;
  }

  function permutations(arr) {
    var out = [];
    (function rec(prefix, rest) {
      if (!rest.length) { out.push(prefix); return; }
      for (var i = 0; i < rest.length; i++) {
        rec(prefix.concat([rest[i]]), rest.slice(0, i).concat(rest.slice(i + 1)));
      }
    })([], arr);
    return out;
  }

  function voiceLead(prev, chord, low, high, maxVoices) {
    if (low === undefined) low = 48;
    if (high === undefined) high = 76;
    if (maxVoices === undefined) maxVoices = 4;
    var pcs = chord.voicingPcs(maxVoices);
    if (!prev || !prev.length) return closeVoicing(chord, low, high, maxVoices);
    prev = prev.slice().sort(function (a, b) { return a - b; });
    if (prev.length < pcs.length) {
      while (prev.length < pcs.length) prev = prev.concat([Math.min(high, prev[prev.length - 1] + 4)]);
    } else if (prev.length > pcs.length) {
      prev = pcs.length < 3 ? prev.slice(0, pcs.length) : prev.slice(prev.length - pcs.length);
    }
    var best = null, perms = permutations(pcs);
    for (var k = 0; k < perms.length; k++) {
      var perm = perms[k], voicing = [], motion = 0;
      for (var i = 0; i < perm.length; i++) {
        var v = nearestOctave(perm[i], prev[i], low, high);
        voicing.push(v);
        motion += Math.abs(v - prev[i]);
      }
      var s = voicing.slice().sort(function (a, b) { return a - b; });
      var unisons = voicing.length - uniq(voicing).length;
      var spread = s[s.length - 1] - s[0];
      // Adjacent semitones (a maj7 stacked right under its root) and seconds below
      // middle C are the sour, muddy voicings: penalise them.
      var seconds = 0;
      for (var si = 0; si + 1 < s.length; si++) {
        if (s[si + 1] - s[si] === 1) seconds += 8;
        else if (s[si + 1] - s[si] === 2 && s[si] < 60) seconds += 4;
      }
      var score = motion + 6 * unisons + (spread > 19 ? 2 : 0) + seconds;
      if (best === null || score < best[0]) best = [score, s];
    }
    return best[1];
  }

  function spreadVoicing(chord, low, high) {
    if (low === undefined) low = 40;
    if (high === undefined) high = 84;
    var pcs = chord.pcs();
    var r = low + mod(pcs[0] - low, 12);
    var out = [r];
    var fifth = chord.fifth();
    if (fifth !== null) out.push(r + mod(fifth - r, 12));
    var upper = pcs.filter(function (pc) { return pc !== pcs[0] && pc !== fifth; });
    var anchor = r + 12;
    for (var i = 0; i < upper.length; i++) {
      var cand = anchor + mod(upper[i] - anchor, 12);
      out.push(cand);
      anchor = cand;
    }
    out = out.filter(function (p) { return p <= high; });
    return uniq(out).sort(function (a, b) { return a - b; });
  }

  function transpose(pitches, semitones) { return pitches.map(function (p) { return p + semitones; }); }
  function nearestScalePitch(pitch, allowedPcs) {
    var allowed = allowedPcs.map(function (p) { return mod(p, 12); });
    for (var d = 0; d < 7; d++) {
      var cands = [pitch - d, pitch + d];
      for (var i = 0; i < 2; i++) if (includes(allowed, mod(cands[i], 12))) return cands[i];
    }
    return pitch;
  }
  function intervalName(semitones) {
    var names = ['P1', 'm2', 'M2', 'm3', 'M3', 'P4', 'TT', 'P5', 'm6', 'M6', 'm7', 'M7'];
    var a = Math.abs(semitones), octs = Math.floor(a / 12), rem = a % 12;
    return names[rem] + (octs ? '+' + octs + 'oct' : '');
  }

  // =========================================================================
  // analysis.py
  // =========================================================================
  var CJK_CLASS = '[㐀-䶿一-鿿豈-﫿]';
  var CJK_RE = new RegExp(CJK_CLASS);
  var CJK_START_RE = new RegExp('^' + CJK_CLASS);
  var CJK_PUNCT = '，。！？；：、（）「」『』《》〈〉“”‘’…—～·';

  function words(s) { return s.split(/\s+/).filter(function (w) { return w.length; }); }

  var POSITIVE_ZH = words('爱 喜 乐 笑 光 暖 春 花 梦 希望 温柔 幸福 美 甜 阳光 拥抱 家 归 安 欢 舞 歌 生 星 海 蓝 晴 好 谢 亲爱 想念\n' +
    '微笑 柔 香 明亮 晨 桃 燕 鸟 蝶 糖 礼物 快乐 平安 温暖 依然 相信 永远 成长 青 绿 喜欢 感动 珍惜 陪伴 祝福 自由 勇敢 灿烂\n' +
    '清澈 宁静 甘 蜜 暖阳 晨光 彩虹 拥 亲吻 欣喜 欢喜 欢乐 幸运 圆满 团圆 重逢 盛开 绽放 明媚 灵动 温情 慈 善 美好 顺利 安心 安然\n' +
    '安稳 舒展 轻盈 飞翔 翱翔 微风 春风 暖风 晴朗 皎洁 璀璨 辉煌 荣耀 胜利 收获 丰盈 富足 感恩 谢谢 可爱 迷人 动人 心动 心安 心暖');
  var NEGATIVE_ZH = words('哭 泪 痛 伤 死 别 离 孤 冷 灰 忘 悲 愁 苦 恨 怕 空 断 失 落 暗 沉 病 老 远 无 伤心 寂寞 孤独 绝望 荒 坟 血 灭 碎 弃\n' +
    '逝 憾 悔 叹 殇 哀 泣 寒 枯 尘 夜 悲伤 忧伤 忧愁 哀愁 哀伤 惆怅 落寞 孤单 无助 无奈 疲惫 迷茫 恐惧 害怕 恐慌 焦虑 不安 崩溃\n' +
    '破碎 凋零 枯萎 腐烂 废墟 阴影 阴暗 黑暗 深渊 沉默 沉沦 沉重 冰冷 冷漠 冷酷 残忍 残酷 折磨 挣扎 疼 疼痛 苦涩 辛酸 心碎 心痛 眼泪\n' +
    '告别 离别 分离 分手 失去 失落 失望 消失 遗忘 遗憾 后悔 怨 怨恨 仇 愤怒 抛弃 背叛 欺骗 谎言 战争 死亡 葬 墓 哭泣 呜咽 叹息');
  var POSITIVE_EN = words('love loves loved loving joy joyful light warm warmth spring bright hope hopes hopeful gentle happy sweet home embrace\n' +
    'peace peaceful calm smile smiles smiling laugh laughter dream dreams star stars sea blue sun sunlight sunshine kind kindness thank thanks\n' +
    'grateful dear beloved darling bloom blossom tender grace glow golden morning garden bird birds song sing singing alive forever always\n' +
    'believe grow green gift treasure cherish delight delighted glad cheer cheerful comfort comforting safe sweetness honey blessing blessed\n' +
    'free freedom brave courage radiant shining shine sparkle wonder wonderful beautiful beauty lovely pretty precious heaven angel paradise\n' +
    'harmony serene soft softly hug kiss kisses together reunion welcome celebrate celebration victory triumph flourish thrive rainbow dawn');
  var NEGATIVE_EN = words('cry cried crying tears tear pain painful hurt hurts death dead die dying died goodbye farewell lonely alone loneliness cold\n' +
    'grey gray forget forgotten sorrow sorrowful grief grieve bitter hate hatred fear afraid empty emptiness broken lost dark darkness sink\n' +
    'sinking sick old far never nothing ache aches ashes grave blood ruin ruins regret sigh mourn mourning wound wounds winter ghost silence\n' +
    'silent gone sad sadness unhappy miserable misery despair hopeless helpless weary tired exhausted numb hollow shadow shadows abyss\n' +
    'cruel cruelty torment agony anguish suffer suffering struggle wither withered decay rot rotten wreck wreckage wasted waste lie lies\n' +
    'betray betrayal betrayed abandon abandoned war fight fought bury buried funeral coffin weep weeping sob sobbing scar scars poison');

  var HIGH_AROUSAL_ZH = words('火 燃 跑 冲 狂 风暴 雷 心跳 疯 快 战 舞 闪 电 霓虹 呐喊 叫 燃烧 奔 撞 炸 鼓 震 醒 起来 冲刺 呼喊 热 沸 奔跑 狂奔\n' +
    '飞奔 疾驰 爆发 爆炸 轰 咆哮 怒吼 尖叫 呐 呼啸 呼喊 激动 兴奋 热血 沸腾 燃起 点燃 闪电 暴雨 狂风 巨浪 海啸 地震 战斗 冲锋 突围\n' +
    '急促 急切 紧张 剧烈 汹涌 澎湃 跳动 心跳 脉搏 急速 高速 飞驰 呼吸急 喘 挣扎 摇滚 狂欢 舞动 跳舞 起舞 欢呼 喝彩 高喊 大笑 狂笑');
  var LOW_AROUSAL_ZH = words('静 慢 睡 眠 月 云 雾 湖 息 轻 悄 淡 缓 沉默 安静 寂静 微 柔 低语 呼吸 冬 雪 溪 浅 空 夜 静谧 宁静 幽静 清幽 悠然\n' +
    '悠悠 缓缓 慢慢 轻轻 悄悄 淡淡 薄薄 朦胧 迷蒙 氤氲 袅袅 飘 漂 浮 荡 摇 摇曳 摇晃 微光 月光 星光 烛光 灯火 余晖 黄昏 暮 晚 深夜\n' +
    '午夜 凌晨 清晨 拂晓 露 霜 冰 湖面 河面 水面 倒影 影 梦 梦境 睡梦 入睡 沉睡 安眠 长眠 停 停留 停下 驻足 凝望 凝视 凝 沉思 冥想');
  var HIGH_AROUSAL_EN = words('fire burn burning burns run running runs rush rushing wild storm storms thunder lightning heartbeat mad madness fast\n' +
    'faster fight fighting dance dancing flash electric city neon loud louder scream screaming shout shouting drum drums pulse race racing\n' +
    'crash crashing explode explosion awake rise rising hot boil boiling blaze blazing roar roaring rage raging fury furious frantic frenzy\n' +
    'chaos chase chasing leap leaping jump jumping sprint speed speeding engine engines highway fever fevered hammer hammering pound pounding\n' +
    'shake shaking tremble trembling burst bursting spark sparks ignite alive electric strobe bass beat beats throb throbbing stomp');
  var LOW_AROUSAL_EN = words('sleep sleeping slow slowly quiet quietly still stillness moon moonlight cloud clouds mist misty lake breath breathe\n' +
    'breathing hush hushed soft softly whisper whispers whispering gentle gently calm calmly silent silence winter snow snowfall stream\n' +
    'shallow drift drifting float floating linger lingering dusk twilight evening midnight dawn candle candlelight lamp lamplight pale dim\n' +
    'faint fading fade fog foggy haze hazy dream dreaming dreamy rest resting pause paused wait waiting patient patience slumber hum humming\n' +
    'lull lullaby cradle drowsy sleepy lazy idle wander wandering meadow willow river riverbank shore tide tides ripple ripples');

  var TENSION_ZH = words('但 却 可是 然而 如果 为什么 为何 是否 难道 也许 或许 不知 不能 无法 还是 直到 等待 犹豫 徘徊 矛盾 不确定 疑惑 困惑\n' +
    '迷惑 怀疑 质疑 追问 询问 疑问 问 究竟 到底 何时 何处 何以 怎 怎么 怎样 如何 万一 倘若 假如 若 除非 只是 只不过 偏偏 竟 竟然\n' +
    '居然 却又 又或 抑或 还 仍 仍然 依旧 尚未 未 尚 仍旧 挣扎 摇摆 动摇 迟疑 踌躇 彷徨 纠结 焦灼 悬 悬念 未知 未来 不知道 不明白');
  var TENSION_EN = words('but yet however if why whether maybe perhaps unless until wait waiting hesitate hesitation torn doubt doubts doubtful\n' +
    'question questions unsure uncertain uncertainty cannot can\'t couldn\'t wouldn\'t shouldn\'t should would could might although though\n' +
    'still nevertheless nonetheless whereas otherwise suppose supposing what when where how who whom whose which somehow someday somewhere\n' +
    'almost nearly barely hardly scarcely between edge brink verge cliff tightrope suspense pending unresolved unanswered unknown unsaid');

  var WARM_ZH = words('家 妈妈 母亲 父亲 爸爸 你 我们 拥抱 手 怀 亲 温 暖 灯 炉 汤 茶 饭 信 陪 伴 老友 兄弟 姐妹 孩子 童年 爷爷 奶奶 外婆\n' +
    '外公 姥姥 姥爷 家人 亲人 爱人 恋人 朋友 伙伴 同伴 邻居 故乡 老家 屋 房 门 窗 床 被 毯 火炉 灶 厨房 饭桌 餐桌 饭菜 面 粥 酒 酒杯\n' +
    '杯 碗 筷 围巾 毛衣 棉 绒 手心 掌心 怀抱 肩 背 膝 笑声 谈笑 闲聊 叙旧 重逢 团圆 归来 归家 回家 回来 等你 想你 念你 你好 晚安');
  var COLD_ZH = words('冰 霜 雪 铁 钢 石 墙 玻璃 远方 陌生 机器 荒野 孤岛 深海 太空 荒漠 雾 水泥 混凝土 钢筋 铁轨 铁门 铁窗 铁链 锁 锈 金属\n' +
    '金属感 塑料 屏幕 显示器 键盘 电缆 电线 天线 信号塔 高楼 大厦 摩天 玻璃幕墙 荒原 荒凉 荒芜 冷清 冷寂 空旷 空荡 空无 无人 陌生人\n' +
    '异乡 他乡 远行 远去 远离 边缘 边界 荒岛 冰川 冰山 冰河 极地 极夜 真空 黑洞 星际 宇宙 深空 虚空 空洞 麻木 冷眼 冷笑 冷漠 疏离');
  var COLD_EN = words('ice icy frost frozen snow iron steel stone stones wall walls glass distant stranger strangers machine machines wasteland\n' +
    'island ocean space desert deserts fog concrete asphalt metal metallic chrome plastic screen screens keyboard cable cables wire wires\n' +
    'antenna tower towers skyscraper skyscrapers vacant empty hollow barren bleak desolate stark remote faraway exile exiled alien foreign\n' +
    'border edge frontier glacier tundra arctic void vacuum orbit satellite static numb detached indifferent clinical sterile blank');
  var WARM_EN = words('home mother mom mama father dad papa you we us embrace hands hand hold holding arms kiss warm lamp hearth fireplace soup tea\n' +
    'bread letter letters company friend friends brother sister child children childhood hug hugs grandmother grandfather grandma grandpa\n' +
    'family beloved lover neighbor neighbour kitchen table supper dinner breakfast blanket blankets wool sweater scarf mitten mittens pillow\n' +
    'bed window door porch garden yard laughter chatter stories story voice voices together reunion return returning homecoming welcome');

  var CLASSICAL_ZH = words('月 花 酒 江 山 风 雪 古 琴 诗 词 楼 舟 桥 柳 燕 雁 松 竹 梅 菊 亭 帘 烛 墨 笔 砚 卷 客 故人 明月 长亭 千里 万里 天涯\n' +
    '春秋 苍 悠 兮 之 乎 者 也 焉 矣 君 吾 汝 尔 兰 荷 莲 桂 枫 桐 杏 李 桃花 落花 飞花 残花 芳 芳草 青山 绿水 碧 苍茫 苍穹 云海 烟雨\n' +
    '烟波 江南 塞北 关山 玉 珠 簪 绣 锦 罗 纱 绢 帛 笛 箫 筝 瑟 鼓角 钟 磬 寺 庙 塔 阁 台 榭 廊 庭 院 阶 檐 瓦 篱 井 陌 驿 渡 舫 棹\n' +
    '帆 樯 归雁 孤鸿 杜鹃 鹧鸪 鸥 鹤 鹿 蝉 蛩 萤 霞 岚 霭 晖 曦 汀 洲 屿 涧 壑 岫 峦 崖 岭 潭 溪 泉 瀑 烟 霜 露 霁 岁 朝暮 晨昏');
  var CLASSICAL_EN = words('thee thou thy thine hath doth ere o\'er whilst sonnet muse verse lyre nightingale meadow moonlight lament yonder\n' +
    'hither fair maiden knight harp chapel candle quill parchment art wert shalt canst dost hast tis twas nay yea forsooth alas oft ne\'er\n' +
    'e\'er \'tis \'twas ballad ode elegy psalm hymn minstrel bard troubadour lute viol organ choir cathedral abbey cloister castle tower\n' +
    'throne crown sword shield banner steed chariot laurel garland wreath rose lily violet ivy oak willow yew orchard vineyard shepherd\n' +
    'shepherdess nymph faun sprite fairy fae elfin dryad naiad muse muses grecian roman gothic baroque sonata nocturne prelude fugue');
  var ELECTRONIC_ZH = words('霓虹 城市 电 屏幕 机器 信号 数据 像素 未来 太空 星际 赛博 网络 代码 电流 频率 光纤 芯片 合成 键盘 引擎 高速 地铁 车站\n' +
    '夜店 灯光 闪烁 电台 电子 电脑 手机 程序 算法 系统 服务器 云端 虚拟 数字 比特 字节 二进制 模拟 电波 无线 蓝牙 雷达 激光 全息 投影\n' +
    '机械 机甲 机器人 仿生 义体 芯 电路 电池 电压 电磁 磁场 脉冲 波形 振荡 调制 滤波 混音 采样 循环 节拍 鼓机 贝斯 低音 合成器 音序\n' +
    '夜晚 夜色 夜幕 深夜 午夜 霓虹灯 街灯 路灯 车灯 尾灯 高架 立交 隧道 公路 街道 街头 楼群 天际线 摩天楼 玻璃 反光 倒影 雨夜 雨街');
  var ELECTRONIC_EN = words('neon city electric screen screens machine signal signals data pixel pixels future space synth synthesizer synthesizers\n' +
    'code wire wires glow static cyber network circuit circuits frequency chip engine highway subway station club strobe radio digital laser\n' +
    'chrome computer computers phone program programs algorithm system server cloud virtual bit bits byte bytes binary analog analogue wave\n' +
    'waves wireless bluetooth radar hologram holographic projection mechanical mech robot robots android cyborg bionic circuitry battery\n' +
    'voltage magnetic pulse pulses waveform oscillator modulate modulation filter mixer sample sampler loop loops beat beats drum machine\n' +
    'bassline sequencer arpeggio midnight nightlife streetlight streetlights headlights taillights overpass tunnel asphalt skyline glass\n' +
    'reflection reflections rain rainy grid matrix terminal console monitor cursor glitch glitches interface upload download stream');

  var NEGATION_ZH = ['不', '没', '无', '非', '未', '莫', '勿', '别'];
  var NEGATION_EN = ['not', 'no', 'never', 'without', 'nor', 'neither', 'n\'t', 'cannot', 'hardly'];
  var INTENSIFIER_ZH = ['很', '非常', '太', '最', '极', '特别', '十分', '格外', '更', '好', '真'];
  var INTENSIFIER_EN = ['very', 'so', 'deeply', 'truly', 'really', 'utterly', 'extremely', 'terribly', 'absolutely', 'completely'];

  var LEXICONS = {
    POSITIVE_ZH: POSITIVE_ZH, NEGATIVE_ZH: NEGATIVE_ZH, POSITIVE_EN: POSITIVE_EN, NEGATIVE_EN: NEGATIVE_EN,
    HIGH_AROUSAL_ZH: HIGH_AROUSAL_ZH, LOW_AROUSAL_ZH: LOW_AROUSAL_ZH, HIGH_AROUSAL_EN: HIGH_AROUSAL_EN,
    LOW_AROUSAL_EN: LOW_AROUSAL_EN, TENSION_ZH: TENSION_ZH, TENSION_EN: TENSION_EN, WARM_ZH: WARM_ZH, COLD_ZH: COLD_ZH,
    COLD_EN: COLD_EN, WARM_EN: WARM_EN, CLASSICAL_ZH: CLASSICAL_ZH, CLASSICAL_EN: CLASSICAL_EN,
    ELECTRONIC_ZH: ELECTRONIC_ZH, ELECTRONIC_EN: ELECTRONIC_EN
  };

  function textSeed(text) { return seedOf(text.trim()); }
  function tokenSeed(token) { return seedOf(token); }

  function countMatches(text, re) { var m = text.match(re); return m ? m.length : 0; }

  function detectLanguage(text) {
    var cjk = countMatches(text, new RegExp(CJK_CLASS, 'g'));
    var latin = countMatches(text, /[A-Za-z]/g);
    if (cjk === 0 && latin === 0) return 'en';
    var ratio = cjk / (cjk + latin);
    if (ratio > 0.7) return 'zh';
    if (ratio < 0.3) return 'en';
    return 'mixed';
  }

  function endsWithAny(w, suffixes) {
    for (var i = 0; i < suffixes.length; i++) if (w.length >= suffixes[i].length && w.slice(w.length - suffixes[i].length) === suffixes[i]) return true;
    return false;
  }

  function englishSyllables(word) {
    var w = word.toLowerCase().replace(/[^a-z']/g, '');
    if (!w) return [];
    var groups = [], re = /[aeiouy]+/g, m;
    while ((m = re.exec(w)) !== null) groups.push({ start: m.index, end: m.index + m[0].length });
    var count = groups.length;
    if (endsWithAny(w, ['e']) && !endsWithAny(w, ['le', 'ee', 'ye']) && count > 1) count -= 1;
    if (endsWithAny(w, ['ed']) && count > 1 && !endsWithAny(w, ['ted', 'ded'])) count -= 1;
    count = Math.max(1, count);
    if (count === 1) return [w];
    var cuts = [], last = 0;
    var boundaries = groups.map(function (g) { return g.end; }).slice(0, count - 1);
    for (var i = 0; i < boundaries.length; i++) {
      var b = boundaries[i];
      var nxt = (b < w.length && 'aeiouy'.indexOf(w[b]) < 0 && b + 1 < w.length) ? b + 1 : b;
      cuts.push(w.slice(last, nxt));
      last = nxt;
    }
    cuts.push(w.slice(last));
    return cuts.filter(function (c) { return c.length; });
  }

  var SYLLABLE_TOKEN_RE = new RegExp(CJK_CLASS + '|[A-Za-z\']+|[0-9]+', 'g');
  function splitSyllables(line) {
    var out = [], m;
    SYLLABLE_TOKEN_RE.lastIndex = 0;
    while ((m = SYLLABLE_TOKEN_RE.exec(line)) !== null) {
      var token = m[0];
      if (CJK_START_RE.test(token)) out.push(token);
      else if (/^[0-9]+$/.test(token)) out.push.apply(out, token.split(''));
      else out.push.apply(out, englishSyllables(token));
    }
    return out;
  }

  // Weighted lexicon hits -> [weight, matched words].
  function countHits(textLower, wordsZh, wordsEn, enTokens, negation) {
    if (negation === undefined) negation = true;
    var weight = 0.0, hits = [];
    var masked = textLower;
    // Longest entries first (stable, so ties keep lexicon order; Python uses set order there).
    var zh = uniq(wordsZh).map(function (w, i) { return [w, i]; })
      .sort(function (a, b) { return (b[0].length - a[0].length) || (a[1] - b[1]); })
      .map(function (x) { return x[0]; });
    for (var wi = 0; wi < zh.length; wi++) {
      var w = zh[wi], start = 0;
      while (true) {
        var i = masked.indexOf(w, start);
        if (i < 0) break;
        start = i + w.length;
        masked = masked.slice(0, i) + new Array(w.length + 1).join('\u0000') + masked.slice(start);
        var factor = 1.0;
        var before = textLower.slice(Math.max(0, i - 2), i);
        var b1 = before.length ? before[before.length - 1] : '';
        var b2 = before.length > 1 ? before[before.length - 2] : '';
        if (negation && before && (includes(NEGATION_ZH, b1) ||
            (before.length > 1 && includes(NEGATION_ZH, b2) && includes(['是', '会', '再', '曾'], b1)))) {
          factor = -0.8;
        } else if (INTENSIFIER_ZH.some(function (x) { return endsWithAny(before, [x]); })) {
          factor = 1.5;
        }
        weight += factor;
        hits.push((factor < 0 ? '~' : '') + w);
      }
    }
    for (var k = 0; k < enTokens.length; k++) {
      var t = enTokens[k];
      if (includes(wordsEn, t)) {
        var f2 = 1.0;
        var prev = k > 0 ? enTokens[k - 1] : '';
        var prev2 = k > 1 ? enTokens[k - 2] : '';
        if (negation && (includes(NEGATION_EN, prev) || endsWithAny(prev, ['n\'t']) ||
            (includes(NEGATION_EN, prev2) && includes(['so', 'very', 'really'], prev)))) {
          f2 = -0.8;
        } else if (includes(INTENSIFIER_EN, prev)) {
          f2 = 1.5;
        }
        weight += f2;
        hits.push((f2 < 0 ? '~' : '') + t);
      }
    }
    return [weight, hits];
  }

  function sigmoidScale(x, k) { return k > 0 ? 1.0 - Math.exp(-x / k) : 0.0; }

  var SENTENCE_SPLIT_CHARS = '。！？!?；;';
  function splitSentences(raw) {
    // Equivalent of re.split(r"(?<=[。！？!?；;])\s*", raw) without lookbehind.
    var pieces = [], last = 0, i = 0;
    while (i < raw.length) {
      if (SENTENCE_SPLIT_CHARS.indexOf(raw[i]) >= 0) {
        pieces.push(raw.slice(last, i + 1));
        var j = i + 1;
        while (j < raw.length && /\s/.test(raw[j])) j++;
        last = j;
        i = j;
      } else {
        i++;
      }
    }
    pieces.push(raw.slice(last));
    return pieces.filter(function (p) { return p.trim().length; });
  }

  function parseStructure(text) {
    var stanzas = [];
    var blocks = text.trim().split(/\n\s*\n/);
    for (var bi = 0; bi < blocks.length; bi++) {
      var lines = [];
      var rawLines = blocks[bi].split(/\r\n|\r|\n|\v|\f|\x1c|\x1d|\x1e|\x85|\u2028|\u2029/);
      for (var ri = 0; ri < rawLines.length; ri++) {
        var raw = rawLines[ri].trim();
        if (!raw) continue;
        var pieces = splitSentences(raw);
        for (var pi = 0; pi < pieces.length; pi++) {
          var piece = pieces[pi];
          var syl = splitSyllables(piece);
          if (!syl.length) continue;
          lines.push({
            text: piece.trim(),
            syllables: syl,
            ends_with_question: /[?？]\s*$/.test(piece),
            ends_with_exclamation: /[!！]\s*$/.test(piece),
            ends_with_ellipsis: /(…|\.\.\.)\s*$/.test(piece)
          });
        }
      }
      if (lines.length) stanzas.push({ lines: lines });
    }
    var out = [];
    for (var si = 0; si < stanzas.length; si++) {
      var st = stanzas[si];
      if (st.lines.length > 8) {
        for (var i = 0; i < st.lines.length; i += 4) out.push({ lines: st.lines.slice(i, i + 4) });
      } else {
        out.push(st);
      }
    }
    return out;
  }

  var AFFECT_KEYS = ['valence', 'arousal', 'tension', 'warmth', 'classical', 'electronic'];

  function pole(posW, negW) {
    var p = Math.max(0, posW) + Math.max(0, -negW);
    var n = Math.max(0, negW) + Math.max(0, -posW);
    return [p, n];
  }

  function affectOf(text) {
    var out = {};
    if (!text.trim()) {
      for (var i = 0; i < AFFECT_KEYS.length; i++) out[AFFECT_KEYS[i]] = 0.0;
      return out;
    }
    var f = analyzeFull(text);
    for (var k = 0; k < AFFECT_KEYS.length; k++) out[AFFECT_KEYS[k]] = f[AFFECT_KEYS[k]];
    return out;
  }

  // Full analysis: unrounded values + stanzas (TextFeatures).
  function analyzeFull(text, affect) {
    text = text.replace(/\r\n/g, '\n');
    var stanzas = parseStructure(text);
    var lower = text.toLowerCase();
    var enTokens = lower.match(/[a-z']+/g) || [];
    var language = detectLanguage(text);

    var pos = countHits(lower, POSITIVE_ZH, POSITIVE_EN, enTokens);
    var neg = countHits(lower, NEGATIVE_ZH, NEGATIVE_EN, enTokens);
    var hi = countHits(lower, HIGH_AROUSAL_ZH, HIGH_AROUSAL_EN, enTokens, false);
    var lo = countHits(lower, LOW_AROUSAL_ZH, LOW_AROUSAL_EN, enTokens, false);
    var ten = countHits(lower, TENSION_ZH, TENSION_EN, enTokens, false);
    var warm = countHits(lower, WARM_ZH, WARM_EN, enTokens, false);
    var cold = countHits(lower, COLD_ZH, COLD_EN, enTokens, false);
    var cla = countHits(lower, CLASSICAL_ZH, CLASSICAL_EN, enTokens, false);
    var ele = countHits(lower, ELECTRONIC_ZH, ELECTRONIC_EN, enTokens, false);
    var pw = pole(pos[0], neg[0]);
    var posW = pw[0], negW = pw[1];
    var hiW = hi[0], loW = lo[0], tenW = ten[0], warmW = warm[0], coldW = cold[0], claW = cla[0], eleW = ele[0];

    var nSyl = 0, nLines = 0, lineLengths = [];
    for (var si = 0; si < stanzas.length; si++) {
      for (var li = 0; li < stanzas[si].lines.length; li++) {
        var n = stanzas[si].lines[li].syllables.length;
        nSyl += n; nLines += 1; lineLengths.push(n);
      }
    }
    var per100 = 100.0 / Math.max(nSyl, 20);
    var valence = (posW - negW) / (posW + negW + 2.0);

    var nExcl = countMatches(text, /[!！]/g);
    var nQ = countMatches(text, /[?？]/g);
    var nEll = countMatches(text, /…|\.\.\./g);
    var caps = countMatches(text, /[A-Z]/g);
    var capsRatio = caps / Math.max(1, countMatches(text, /[A-Za-z]/g));
    if (!lineLengths.length) lineLengths = [0];
    var meanLen = sum(lineLengths) / lineLengths.length;

    var arousal = 0.35;
    arousal += 0.35 * sigmoidScale((hiW + 1.5 * nExcl) * per100, 4.0);
    arousal -= 0.30 * sigmoidScale((loW + 0.7 * nEll) * per100, 4.0);
    arousal += 0.10 * Math.min(1.0, capsRatio * 4);
    arousal += 0.10 * (1.0 - Math.min(1.0, meanLen / 14.0));
    arousal = clamp(arousal, 0.0, 1.0);

    var tension = 0.15;
    tension += 0.45 * sigmoidScale((tenW + 2.0 * nQ) * per100, 4.0);
    tension += 0.15 * sigmoidScale(nEll * per100, 2.0);
    tension += 0.15 * (1 - Math.abs(valence));
    tension = clamp(tension, 0.0, 1.0);

    var warmth = 0.5 + 0.5 * (warmW - coldW) / (warmW + coldW + 2.0);
    warmth = 0.7 * warmth + 0.3 * (0.5 + 0.5 * valence);
    var classical = sigmoidScale(claW * per100, 5.0);
    var electronic = sigmoidScale(eleW * per100, 4.0);

    var density = Math.min(1.0, meanLen / 16.0);
    var variance = 0;
    for (var i = 0; i < lineLengths.length; i++) variance += Math.pow(lineLengths[i] - meanLen, 2);
    variance /= lineLengths.length;
    var irregularity = Math.min(1.0, Math.sqrt(variance) / Math.max(meanLen, 1.0));

    var values = { valence: valence, arousal: arousal, tension: tension, warmth: clamp(warmth, 0.0, 1.0),
      classical: classical, electronic: electronic };
    if (affect) {
      for (var k in affect) {
        if (Object.prototype.hasOwnProperty.call(affect, k) && Object.prototype.hasOwnProperty.call(values, k) &&
            affect[k] !== null && affect[k] !== undefined) {
          var lo_ = k === 'valence' ? -1.0 : 0.0, hi_ = 1.0;
          values[k] = clamp(Number(affect[k]), lo_, hi_);
        }
      }
    }
    return {
      language: language,
      n_chars: chars(text).length,
      n_syllables: nSyl,
      n_lines: nLines,
      n_stanzas: stanzas.length,
      valence: values.valence,
      arousal: values.arousal,
      tension: values.tension,
      warmth: values.warmth,
      classical: values.classical,
      electronic: values.electronic,
      density: density,
      irregularity: irregularity,
      question_ratio: nQ / Math.max(1, nLines),
      exclamation_ratio: nExcl / Math.max(1, nLines),
      seed: textSeed(text),
      keyword_hits: { positive: pos[1], negative: neg[1], high_arousal: hi[1], low_arousal: lo[1],
        tension: ten[1], warm: warm[1], cold: cold[1], classical: cla[1], electronic: ele[1] },
      stanzas: stanzas
    };
  }

  // TextFeatures.to_dict(): rounded dials, no stanzas.
  function featuresToDict(f) {
    var d = {};
    var keys = ['language', 'n_chars', 'n_syllables', 'n_lines', 'n_stanzas', 'valence', 'arousal', 'tension',
      'warmth', 'classical', 'electronic', 'density', 'irregularity', 'question_ratio', 'exclamation_ratio',
      'seed', 'keyword_hits'];
    for (var i = 0; i < keys.length; i++) d[keys[i]] = f[keys[i]];
    var r = ['valence', 'arousal', 'tension', 'warmth', 'classical', 'electronic', 'density', 'irregularity',
      'question_ratio', 'exclamation_ratio'];
    for (var j = 0; j < r.length; j++) d[r[j]] = roundN(d[r[j]], 3);
    d.keyword_hits = deepCopy(d.keyword_hits);
    return d;
  }

  // Public analyze(): TextFeatures.to_dict() plus stanzas.
  function analyze(text, affect) {
    var f = analyzeFull(text, affect);
    var d = featuresToDict(f);
    d.stanzas = deepCopy(f.stanzas);
    return d;
  }

  // =========================================================================
  // tones.py
  // =========================================================================
  var TONE_START = 0x4E00, TONE_END = 0x9FFF;
  var TONE_SHAPE = { 1: [0.85, 0.85], 2: [0.45, 0.85], 3: [0.30, 0.15], 4: [0.90, 0.30], 5: [0.50, 0.50] };
  var TONE_NAMES = { 0: '?', 1: '阴平', 2: '阳平', 3: '上声', 4: '去声', 5: '轻声' };
  var TONE_LEVEL = { 1: 0.85, 2: 0.62, 3: 0.22, 4: 0.60, 5: 0.50 };

  function toneTable() { return (root && typeof root.POET_TONES === 'string') ? root.POET_TONES : ''; }

  function toneOf(ch) {
    if (typeof ch !== 'string' || chars(ch).length !== 1) return 0;
    var cp = ch.codePointAt(0);
    if (!(TONE_START <= cp && cp <= TONE_END)) return 0;
    var table = toneTable();
    var idx = cp - TONE_START;
    if (idx >= table.length) return 0;
    return parseInt(table[idx], 10) || 0;
  }
  function tonesOf(syllables) {
    return syllables.map(function (s) { return chars(s).length === 1 ? toneOf(s) : 0; });
  }
  function toneHeight(tone) { return TONE_SHAPE[tone] || null; }
  function toneDirection(prevTone, nextTone) {
    var a = TONE_LEVEL[prevTone], b = TONE_LEVEL[nextTone];
    if (a === undefined || b === undefined) return 0;
    var diff = b - a;
    if (diff > 0.2) return 1;
    if (diff < -0.2) return -1;
    return 0;
  }
  function phraseOpenness(finalTone) {
    if (finalTone === 1 || finalTone === 2) return true;
    if (finalTone === 3 || finalTone === 4) return false;
    return null;
  }
  function describeTones(syllables) {
    var t = tonesOf(syllables);
    return syllables.map(function (s, i) { return s + (t[i] ? t[i] : ''); }).join(' ');
  }

  // =========================================================================
  // progressions.py
  // =========================================================================
  function P(name, style, mode, numerals, tags, weight) {
    return { name: name, style: style, mode: mode, numerals: numerals.split(' '), tags: tags || [],
      weight: weight === undefined ? 1.0 : weight };
  }
  var LIBRARY = [
    // ---- Classical / common practice
    P('authentic cadence', 'classical', 'ionian', 'I IV V I', ['bright', 'resolved', 'cadence']),
    P('I vi IV V (50s)', 'classical', 'ionian', 'I vi IV V', ['bright']),
    P('Pachelbel canon', 'classical', 'ionian', 'I V vi iii IV I IV V', ['bright', 'flowing'], 1.4),
    P('ii V I', 'classical', 'ionian', 'I ii V7 I', ['bright', 'resolved']),
    P('plagal', 'classical', 'ionian', 'I IV I V', ['bright', 'hymn']),
    P('circle of fifths (major)', 'classical', 'ionian', 'I IV vii° iii vi ii V I', ['flowing', 'baroque'], 1.2),
    P('deceptive', 'classical', 'ionian', 'I IV V vi', ['tense', 'bittersweet']),
    P('half cadence', 'classical', 'ionian', 'I vi ii V', ['tense', 'open']),
    P('minor authentic', 'classical', 'aeolian', 'i iv V i', ['dark', 'resolved', 'cadence']),
    P('Andalusian', 'classical', 'aeolian', 'i VII VI V', ['dark', 'tense', 'spanish'], 1.2),
    P('lament bass', 'classical', 'aeolian', 'i V VI V', ['dark', 'grief']),
    P('circle of fifths (minor)', 'classical', 'aeolian', 'i iv VII III VI ii° V i', ['dark', 'flowing', 'baroque'], 1.2),
    P('minor i VI III VII', 'classical', 'aeolian', 'i VI III VII', ['dark', 'epic']),
    P('Picardy', 'classical', 'aeolian', 'i iv V I', ['dark', 'resolved', 'hope']),
    // ---- Romantic / chromatic
    P('chromatic mediant', 'romantic', 'ionian', 'I III IV iv', ['bittersweet', 'colour'], 1.2),
    P('borrowed bVI bVII', 'romantic', 'ionian', 'I bVI bVII I', ['epic', 'colour']),
    P('minor iv', 'romantic', 'ionian', 'I IV iv I', ['bittersweet']),
    P('Neapolitan', 'romantic', 'aeolian', 'i bII V i', ['dark', 'tense', 'colour']),
    P('romantic minor', 'romantic', 'aeolian', 'i VI iv V', ['dark', 'longing']),
    P('major to relative minor', 'romantic', 'ionian', 'I V vi IV iv I', ['bittersweet']),
    // ---- Jazz
    P('ii V I', 'jazz', 'ionian', 'ii7 V7 Imaj7 Imaj7', ['resolved'], 1.3),
    P('I vi ii V', 'jazz', 'ionian', 'Imaj7 vi7 ii7 V7', ['flowing'], 1.2),
    P('iii VI ii V', 'jazz', 'ionian', 'iii7 VI7 ii7 V7', ['flowing', 'colour']),
    P('tritone sub', 'jazz', 'ionian', 'ii7 bII7 Imaj7 Imaj7', ['colour', 'tense']),
    P('backdoor', 'jazz', 'ionian', 'Imaj7 iv7 bVII7 Imaj7', ['bittersweet', 'colour']),
    P('minor ii V i', 'jazz', 'aeolian', 'iiø7 V7 i7 i7', ['dark', 'resolved'], 1.2),
    P('minor blues turn', 'jazz', 'aeolian', 'i7 iv7 VII7 IIImaj7', ['dark', 'flowing']),
    P('Coltrane-ish mediants', 'jazz', 'ionian', 'Imaj7 bIII7 bVImaj7 bII7', ['colour', 'tense']),
    // ---- Neo-soul / R&B
    P('neo I iii vi ii', 'neo_soul', 'ionian', 'Imaj9 iii7 vi9 ii9', ['bright', 'smooth'], 1.2),
    P('neo ii V I bIII', 'neo_soul', 'ionian', 'ii9 V13 Imaj9 bIIImaj7', ['smooth', 'colour']),
    P('neo iv bVII', 'neo_soul', 'ionian', 'iv9 bVIImaj7 Imaj9 Imaj9', ['bittersweet', 'smooth']),
    P('neo IV iii', 'neo_soul', 'ionian', 'IVmaj9 iii7 vi9 V9', ['bright', 'smooth']),
    P('neo minor', 'neo_soul', 'aeolian', 'i9 iv9 VImaj7 V7', ['dark', 'smooth']),
    // ---- Pop
    P('axis I V vi IV', 'pop', 'ionian', 'I V vi IV', ['bright'], 1.4),
    P('vi IV I V', 'pop', 'ionian', 'vi IV I V', ['bittersweet'], 1.2),
    P('I vi IV V', 'pop', 'ionian', 'I vi IV V', ['bright']),
    P('I IV vi V', 'pop', 'ionian', 'I IV vi V', ['bright']),
    P('IV I V vi', 'pop', 'ionian', 'IV I V vi', ['bittersweet']),
    P('pop minor', 'pop', 'aeolian', 'i VI III VII', ['dark'], 1.2),
    P('pop minor VI VII', 'pop', 'aeolian', 'VI VII i i', ['dark', 'epic']),
    // ---- Lo-fi
    P('lofi ii V I vi', 'lofi', 'ionian', 'ii7 V7 Imaj7 vi7', ['smooth'], 1.3),
    P('lofi I IV iii vi', 'lofi', 'ionian', 'Imaj9 IVmaj9 iii7 vi9', ['bright', 'smooth'], 1.2),
    P('lofi iv bVII', 'lofi', 'ionian', 'iv7 bVII7 Imaj7 Imaj7', ['bittersweet']),
    P('lofi vi ii I V', 'lofi', 'ionian', 'vi9 ii9 Imaj9 V9', ['smooth']),
    P('lofi minor', 'lofi', 'aeolian', 'i7 iv7 VImaj7 V7', ['dark', 'smooth']),
    P('lofi dorian', 'lofi', 'dorian', 'i7 IV7 i7 IV7', ['modal', 'smooth']),
    // ---- Synthwave
    P('synthwave i VI III VII', 'synthwave', 'aeolian', 'i VI III VII', ['dark', 'epic'], 1.4),
    P('synthwave VI VII i', 'synthwave', 'aeolian', 'VI VII i i', ['dark', 'epic'], 1.2),
    P('synthwave i VII VI VII', 'synthwave', 'aeolian', 'i VII VI VII', ['dark', 'driving'], 1.2),
    P('synthwave i III VII VI', 'synthwave', 'aeolian', 'i III VII VI', ['dark']),
    P('synthwave VI IV i V', 'synthwave', 'aeolian', 'VI iv i V', ['dark', 'tense']),
    P('synthwave major', 'synthwave', 'ionian', 'I V vi IV', ['bright', 'nostalgic']),
    P('synthwave sus', 'synthwave', 'aeolian', 'i VIsus2 III VIIsus2', ['dark', 'airy']),
    // ---- House / techno
    P('house i VII VI VII', 'house', 'aeolian', 'i VII VI VII', ['driving'], 1.3),
    P('house i VI VII', 'house', 'aeolian', 'i i VI VII', ['driving']),
    P('house dorian', 'house', 'dorian', 'i IV i IV', ['modal', 'driving'], 1.2),
    P('house dorian 7ths', 'house', 'dorian', 'i7 IV7 i7 VII', ['modal', 'smooth']),
    P('house deep', 'house', 'aeolian', 'i7 iv7 i7 VImaj7', ['smooth', 'deep']),
    P('house major', 'house', 'ionian', 'Imaj7 vi7 IVmaj7 V7', ['bright', 'smooth']),
    // ---- Trance
    P('trance i VI VII', 'trance', 'aeolian', 'i VI VII VII', ['epic', 'driving'], 1.3),
    P('trance i VI III VII', 'trance', 'aeolian', 'i VI III VII', ['epic'], 1.2),
    P('trance VI VII i III', 'trance', 'aeolian', 'VI VII i III', ['epic', 'uplifting']),
    P('trance i VII VI', 'trance', 'aeolian', 'i VII VI VI', ['driving']),
    P('trance i iv VI V', 'trance', 'aeolian', 'i iv VI V', ['tense', 'epic']),
    // ---- Ambient
    P('ambient I IV', 'ambient', 'ionian', 'Imaj7 IVmaj7 Imaj7 IVmaj7', ['bright', 'still'], 1.3),
    P('ambient sus', 'ambient', 'ionian', 'Isus2 Isus4 Iadd9 Isus2', ['still', 'airy']),
    P('ambient lydian', 'ambient', 'lydian', 'Imaj7#11 II Imaj7#11 II', ['wonder', 'airy'], 1.2),
    P('ambient I iii IV', 'ambient', 'ionian', 'Imaj7 iii7 IVmaj7 Imaj7', ['bright', 'still']),
    P('ambient minor', 'ambient', 'aeolian', 'i9 VImaj7 i9 iv9', ['dark', 'still'], 1.2),
    P('ambient dorian', 'ambient', 'dorian', 'i7 IV i7 IV', ['modal', 'still']),
    // ---- Cinematic
    P('cinematic phrygian', 'cinematic', 'aeolian', 'i bII i VII', ['dark', 'tense'], 1.2),
    P('cinematic i VI iv V', 'cinematic', 'aeolian', 'i VI iv V', ['dark', 'epic']),
    P('cinematic VI VII i', 'cinematic', 'aeolian', 'VI VII i i', ['epic'], 1.2),
    P('cinematic i III iv VII', 'cinematic', 'aeolian', 'i III iv VII', ['dark']),
    P('cinematic major', 'cinematic', 'ionian', 'I bVI IV I', ['epic', 'colour']),
    P('cinematic lydian', 'cinematic', 'lydian', 'I II I II', ['wonder', 'bright']),
    // ---- Folk / pentatonic
    P('folk I vi IV I', 'folk', 'ionian', 'I vi IV I', ['bright', 'simple'], 1.2),
    P('folk I IV I V', 'folk', 'ionian', 'I IV I V', ['bright', 'simple']),
    P('folk vi I IV vi', 'folk', 'ionian', 'vi I IV vi', ['bittersweet', 'simple']),
    P('folk I ii vi V', 'folk', 'ionian', 'I ii vi V', ['bright']),
    P('folk minor i VII', 'folk', 'aeolian', 'i VII i VI', ['dark', 'simple'], 1.2),
    P('folk minor i III VII i', 'folk', 'aeolian', 'i III VII i', ['dark', 'simple']),
    P('folk sus', 'folk', 'ionian', 'Isus2 I IVadd9 Isus2', ['airy', 'simple'])
  ];

  function progressionChords(p, tonic, mode) {
    return p.numerals.map(function (n) { return parseRoman(n, tonic, mode || p.mode); });
  }

  function libraryFor(style, mode) {
    var out = LIBRARY.filter(function (p) { return p.style === style; });
    if (mode !== undefined && mode !== null) {
      var wantMajor = isMajorLike(mode);
      out = out.filter(function (p) { return isMajorLike(p.mode) === wantMajor; });
    }
    return out;
  }
  function allStyles() {
    var seen = [];
    for (var i = 0; i < LIBRARY.length; i++) if (!includes(seen, LIBRARY[i].style)) seen.push(LIBRARY[i].style);
    return seen;
  }

  function pickProgression(style, mode, rng, tags, exclude) {
    tags = tags || []; exclude = exclude || [];
    var pool = libraryFor(style, mode).filter(function (p) { return !includes(exclude, p.name); });
    if (!pool.length) pool = libraryFor(style);
    if (!pool.length) pool = LIBRARY;
    var weights = pool.map(function (p) {
      var w = p.weight;
      for (var i = 0; i < tags.length; i++) if (includes(p.tags, tags[i])) w *= 1.8;
      return w;
    });
    return rng.choices(pool, weights, 1)[0];
  }

  var FUNCTIONS = {
    major: { T: ['I', 'I', 'vi', 'iii'], S: ['IV', 'ii', 'IV', 'ii'], D: ['V', 'V7', 'vii°'] },
    minor: { T: ['i', 'i', 'III', 'VI'], S: ['iv', 'ii°', 'VI', 'iv'], D: ['V', 'V7', 'VII'] }
  };
  var MIXTURE = { major: { S: ['iv', 'bVI', 'bVII', 'ii°'], T: ['bIII', 'bVI'] },
    minor: { S: ['IV', 'ii'], T: ['I'], D: ['v'] } };
  var MEDIANTS = { major: ['III', 'bIII', 'bVI', 'VI'], minor: ['III', 'VI', 'I', 'bII'] };
  var TRANSITIONS = {
    T: [['S', 0.5], ['D', 0.3], ['T', 0.2]],
    S: [['D', 0.6], ['T', 0.25], ['S', 0.15]],
    D: [['T', 0.75], ['S', 0.1], ['D', 0.15]]
  };

  function HarmonyOptions(o) {
    var d = { length: 4, sevenths: 0.0, extensions: 0.0, mixture: 0.0, mediants: 0.0, secondary: 0.0,
      tritone: 0.0, cadence: 'authentic', sus: 0.0, diminished: true };
    return assign(d, o || {});
  }

  function addSeventh(numeral, family, rng, opts) {
    if (/[7°ø+]/.test(numeral) || numeral.indexOf('sus') >= 0) return numeral;
    if (rng.random() >= opts.sevenths) return numeral;
    var deg = numeral.replace(/^[b#]+/, '');
    var upper = deg[0] === deg[0].toUpperCase();
    var ext = rng.random() < opts.extensions;
    if (numeral === 'V') return ext ? 'V9' : 'V7';
    if (upper) {
      if ((numeral === 'VII' || numeral === 'bVII') && family === 'major') return numeral + '7';
      return numeral + (ext ? 'maj9' : 'maj7');
    }
    return numeral + (ext ? '9' : '7');
  }

  function generateFunctional(mode, rng, opts) {
    opts = HarmonyOptions(opts || {});
    var family = isMajorLike(mode) ? 'major' : 'minor';
    var funcs = FUNCTIONS[family];
    var n = Math.max(2, opts.length);
    var states = ['T'];
    while (states.length < n) {
      var cur = states[states.length - 1];
      var tr = TRANSITIONS[cur];
      var nxt = rng.choices(tr.map(function (x) { return x[0]; }), tr.map(function (x) { return x[1]; }))[0];
      states.push(nxt);
    }
    if (n >= 2) {
      var tail = null;
      if (opts.cadence === 'authentic') tail = ['D', 'T'];
      else if (opts.cadence === 'plagal') tail = ['S', 'T'];
      else if (opts.cadence === 'deceptive') tail = ['D', 'T'];
      else if (opts.cadence === 'half') tail = n >= 3 ? ['S', 'D'] : ['T', 'D'];
      else if (opts.cadence === 'picardy') tail = ['D', 'T'];
      if (tail) states.splice(states.length - 2, 2, tail[0], tail[1]);
    }
    var numerals = [];
    var mixtureUsed = false;
    for (var i = 0; i < states.length; i++) {
      var st = states[i];
      var choicesArr = funcs[st].slice();
      var prevState = i > 0 ? states[i - 1] : null;
      // Modal mixture: borrowed subdominants anywhere; a borrowed *tonic* (bIII / bVI)
      // only once and only after a subdominant, never as the resolution of a dominant.
      if (rng.random() < opts.mixture && MIXTURE[family][st]) {
        if (st !== 'T' || (prevState === 'S' && !mixtureUsed)) {
          choicesArr = MIXTURE[family][st];
          if (st === 'T') mixtureUsed = true;
        }
      }
      if (!opts.diminished) {
        choicesArr = choicesArr.filter(function (c) { return c.indexOf('°') < 0; });
        if (!choicesArr.length) choicesArr = family === 'minor' ? ['iv'] : ['IV'];
      }
      var numeral = rng.choice(choicesArr);
      if (numerals.length && uniq(choicesArr).length > 1) {
        var tries = 0;
        while (numeral === numerals[numerals.length - 1] && tries < 6) {
          numeral = rng.choice(choicesArr);
          tries++;
        }
      }
      if (i === 0) numeral = family === 'major' ? 'I' : 'i';
      if (st === 'T' && i !== 0 && rng.random() < opts.mediants) numeral = rng.choice(MEDIANTS[family]);
      numerals.push(numeral);
    }
    var tonic = family === 'major' ? 'I' : 'i';
    if (opts.cadence === 'deceptive') numerals[numerals.length - 1] = family === 'major' ? 'vi' : 'VI';
    else if (opts.cadence === 'picardy') numerals[numerals.length - 1] = 'I';
    else if (opts.cadence === 'authentic' || opts.cadence === 'plagal') numerals[numerals.length - 1] = tonic;
    if (includes(['authentic', 'deceptive', 'picardy', 'half'], opts.cadence)) {
      var domIndex = numerals.length + (opts.cadence === 'half' ? -1 : -2);
      if (includes(['VII', 'vii°', 'v', 'bVII'], numerals[domIndex])) numerals[domIndex] = 'V';
    }
    if (opts.secondary > 0 && n >= 4) {
      var out = [];
      for (i = 0; i < numerals.length; i++) {
        var num = numerals[i];
        if (i > 1 && includes(['ii', 'IV', 'vi', 'iii', 'iv', 'VI', 'III'], num) &&
            rng.random() < opts.secondary && out.length && out[out.length - 1] !== 'V7/' + num) {
          out[out.length - 1] = 'V7/' + num;
        }
        out.push(num);
      }
      numerals = out;
    }
    numerals = numerals.map(function (x, idx) {
      return (opts.cadence === 'picardy' && idx === numerals.length - 1) ? x : addSeventh(x, family, rng, opts);
    });
    if (opts.tritone > 0) {
      for (i = 0; i < numerals.length - 1; i++) {
        if ((numerals[i] === 'V7' || numerals[i] === 'V9') && /^[Ii]/.test(numerals[i + 1]) && rng.random() < opts.tritone) {
          numerals[i] = 'bII7';
        }
      }
    }
    if (opts.sus > 0) {
      for (i = 0; i < numerals.length - 1; i++) {
        if ((numerals[i] === 'I' || numerals[i] === 'i') && rng.random() < opts.sus) {
          numerals[i] = family === 'major' ? 'Isus2' : 'isus2';
        }
      }
    }
    return numerals;
  }

  // =========================================================================
  // styles.py
  // =========================================================================
  function Style(o) {
    var d = { name: '', family: 'classical', tempo_range: [60, 120], major_modes: ['ionian'], minor_modes: ['aeolian'],
      melody_scale: 'mode', time_signatures: [[4, 4]], swing: 0.5, bars_per_chord: 1, harmony: HarmonyOptions(),
      library_ratio: 0.6, pad: 'sustain', keys: 'none', bass: 'root_whole', drums: 'none', sidechain: 0.0,
      lead_octave_shift: 0, ritardando: false, humanize: 0.0, description: '' };
    return assign(d, o);
  }
  var STYLES = {
    classical: Style({ name: 'classical', family: 'classical', tempo_range: [66, 100], major_modes: ['ionian', 'lydian'],
      minor_modes: ['aeolian', 'harmonic_minor'], time_signatures: [[4, 4], [3, 4]],
      harmony: HarmonyOptions({ sevenths: 0.15, secondary: 0.25, mixture: 0.1, cadence: 'authentic' }),
      library_ratio: 0.65, pad: 'swell', keys: 'alberti', bass: 'root_fifth', drums: 'none', ritardando: true, humanize: 0.02,
      description: 'Common-practice harmony, Alberti / broken-chord piano figures, string swells, ritardando at the end.' }),
    romantic: Style({ name: 'romantic', family: 'classical', tempo_range: [56, 88], major_modes: ['ionian', 'lydian'],
      minor_modes: ['aeolian', 'harmonic_minor'], time_signatures: [[4, 4], [3, 4]],
      harmony: HarmonyOptions({ sevenths: 0.35, mixture: 0.45, mediants: 0.35, secondary: 0.3, cadence: 'deceptive' }),
      library_ratio: 0.55, pad: 'swell', keys: 'broken', bass: 'root_fifth', drums: 'none', ritardando: true, humanize: 0.03,
      description: 'Chromatic mediants, modal mixture, deceptive cadences, rubato feel.' }),
    folk: Style({ name: 'folk', family: 'classical', tempo_range: [72, 104], major_modes: ['ionian', 'mixolydian'],
      minor_modes: ['aeolian', 'dorian'], melody_scale: 'pentatonic', time_signatures: [[4, 4], [3, 4]],
      harmony: HarmonyOptions({ diminished: false, sevenths: 0.0, sus: 0.3, cadence: 'plagal' }),
      library_ratio: 0.8, pad: 'sustain', keys: 'broken', bass: 'root_fifth', drums: 'none', ritardando: true, humanize: 0.02,
      description: 'Pentatonic (宫/羽) melodies over simple triads and sus chords; plagal cadences.' }),
    jazz: Style({ name: 'jazz', family: 'hybrid', tempo_range: [88, 150], major_modes: ['ionian', 'lydian'],
      minor_modes: ['dorian', 'aeolian'], melody_scale: 'mode', swing: 0.64,
      harmony: HarmonyOptions({ sevenths: 0.95, extensions: 0.5, secondary: 0.35, tritone: 0.35, cadence: 'authentic' }),
      library_ratio: 0.5, pad: 'none', keys: 'comp', bass: 'walking', drums: 'none', humanize: 0.03,
      description: 'ii-V-I, extended chords, tritone substitutions, walking bass, swung eighths.' }),
    neo_soul: Style({ name: 'neo_soul', family: 'hybrid', tempo_range: [68, 92], major_modes: ['ionian', 'lydian'],
      minor_modes: ['dorian', 'aeolian'], swing: 0.58,
      harmony: HarmonyOptions({ diminished: false, sevenths: 1.0, extensions: 0.8, mixture: 0.3, cadence: 'plagal' }),
      library_ratio: 0.7, pad: 'sustain', keys: 'comp', bass: 'root_13', drums: 'lofi', humanize: 0.04,
      description: 'Lush 9th/13th voicings, borrowed iv and bVII, laid-back drums.' }),
    lofi: Style({ name: 'lofi', family: 'electronic', tempo_range: [68, 86], major_modes: ['ionian', 'lydian'],
      minor_modes: ['dorian', 'aeolian'], swing: 0.6,
      harmony: HarmonyOptions({ diminished: false, sevenths: 0.95, extensions: 0.6, mixture: 0.25, cadence: 'plagal' }),
      library_ratio: 0.7, pad: 'sustain', keys: 'stab_offbeat', bass: 'root_13', drums: 'lofi', humanize: 0.05,
      description: 'Warm detuned keys, seventh chords, swung lo-fi drums, tape wobble.' }),
    pop: Style({ name: 'pop', family: 'hybrid', tempo_range: [92, 128], major_modes: ['ionian', 'mixolydian'],
      minor_modes: ['aeolian'], harmony: HarmonyOptions({ diminished: false, sevenths: 0.1, cadence: 'none' }), library_ratio: 0.85,
      pad: 'sustain', keys: 'broken', bass: 'octaves8', drums: 'four_floor', sidechain: 0.25,
      description: 'Four-chord loops (I-V-vi-IV and friends), steady pulse.' }),
    synthwave: Style({ name: 'synthwave', family: 'electronic', tempo_range: [84, 118], major_modes: ['ionian'],
      minor_modes: ['aeolian'], harmony: HarmonyOptions({ diminished: false, sevenths: 0.05, sus: 0.25, cadence: 'none' }), library_ratio: 0.85,
      pad: 'sustain', keys: 'arpeggio_up', bass: 'octaves8', drums: 'backbeat', sidechain: 0.5,
      description: 'Aeolian i-VI-III-VII loops, supersaw pads, octave bass, gated-reverb drums.' }),
    house: Style({ name: 'house', family: 'electronic', tempo_range: [118, 126], major_modes: ['ionian'],
      minor_modes: ['aeolian', 'dorian'], swing: 0.54,
      harmony: HarmonyOptions({ diminished: false, sevenths: 0.5, extensions: 0.2, cadence: 'none' }), library_ratio: 0.8,
      pad: 'stab', keys: 'stab_offbeat', bass: 'offbeat8', drums: 'four_floor', sidechain: 0.6,
      description: 'Dorian / aeolian two-chord vamps, off-beat bass, four-on-the-floor.' }),
    trance: Style({ name: 'trance', family: 'electronic', tempo_range: [132, 140], major_modes: ['ionian'],
      minor_modes: ['aeolian'], harmony: HarmonyOptions({ diminished: false, sevenths: 0.0, cadence: 'none' }), library_ratio: 0.85,
      pad: 'sustain', keys: 'pluck16', bass: 'rolling16', drums: 'trance', sidechain: 0.7, lead_octave_shift: 0,
      description: 'Uplifting aeolian loops, rolling 16th bass, supersaw leads.' }),
    ambient: Style({ name: 'ambient', family: 'electronic', tempo_range: [56, 72], major_modes: ['lydian', 'ionian'],
      minor_modes: ['dorian', 'aeolian'], bars_per_chord: 2,
      harmony: HarmonyOptions({ diminished: false, sevenths: 0.9, extensions: 0.5, sus: 0.4, cadence: 'plagal' }), library_ratio: 0.7,
      pad: 'swell', keys: 'arpeggio_updown', bass: 'drone', drums: 'none', ritardando: true,
      description: 'Slow lydian / dorian colour, long swells, drones, lots of reverb.' }),
    cinematic: Style({ name: 'cinematic', family: 'hybrid', tempo_range: [60, 96], major_modes: ['lydian', 'ionian'],
      minor_modes: ['aeolian', 'phrygian'],
      harmony: HarmonyOptions({ sevenths: 0.2, mixture: 0.4, mediants: 0.3, cadence: 'half' }), library_ratio: 0.6,
      pad: 'swell', keys: 'arpeggio_up', bass: 'octaves8', drums: 'none', ritardando: true,
      description: 'Phrygian bII, chromatic mediants, ostinato arpeggios, half cadences.' })
  };
  function styleNames() { return Object.keys(STYLES); }

  function chooseStyle(f) {
    var e = f.electronic, c = f.classical;
    var scores = {};
    scores.classical = 1.0 * c + 0.3 * (1 - f.arousal) + (f.language === 'en' ? 0.3 : 0.0) - 0.8 * e;
    scores.folk = 1.1 * c + 0.2 * (1 - f.arousal) + (f.language === 'zh' ? 0.4 : 0.0) - 0.8 * e + 0.2 * f.valence;
    scores.romantic = 0.7 * c + 0.5 * f.tension + 0.3 * (1 - Math.abs(f.valence)) - 0.6 * e;
    scores.jazz = 0.3 + 0.5 * f.irregularity + 0.3 * f.arousal + 0.2 * f.tension - 0.3 * c;
    scores.neo_soul = 0.35 + 0.5 * f.warmth + 0.2 * (1 - f.arousal) - 0.4 * c;
    scores.lofi = 0.45 + 0.5 * f.warmth + 0.4 * (1 - f.arousal) + 0.3 * e - 0.4 * c;
    scores.pop = 0.3 + 0.5 * f.valence + 0.3 * f.arousal;
    scores.synthwave = 0.2 + 1.0 * e + 0.3 * f.arousal - 0.3 * f.valence;
    scores.house = 0.9 * e + 0.8 * f.arousal - 0.3;
    scores.trance = 0.8 * e + 1.0 * f.arousal - 0.5;
    scores.ambient = 0.3 + 0.9 * (1 - f.arousal) + 0.3 * f.tension - 0.2 * e;
    scores.cinematic = 0.2 + 0.6 * f.tension + 0.4 * Math.abs(f.valence) - 0.2 * f.valence + 0.3 * f.arousal;
    var best = null, bestV = -Infinity;
    for (var k in scores) if (scores[k] > bestV) { bestV = scores[k]; best = k; }
    return best;
  }

  // =========================================================================
  // interpret.py
  // =========================================================================
  var PAINTING = {
    rise: ['上 高 飞 升 天 空 云 顶 望 攀 翔 举 起 冲 sky fly flies flying high higher climb climbs soar soars up upward rise rises rising mountain mountains ascend heaven heavens', 'contour up'],
    fall: ['下 落 沉 低 坠 泪 雨 埋 垂 降 跌 fall falls falling down downward sink sinks low lower drop drops tears rain bury descend descending plunge', 'contour down'],
    still: ['静 停 眠 睡 止 定 凝 息 still stillness silence silent stop stops sleep sleeps freeze frozen pause quiet hush', 'longer notes, fewer ornaments'],
    flow: ['河 流 水 风 江 海 波 溪 涌 淌 river rivers flow flows flowing stream streams wind winds sea waves wave breeze current tide', 'stepwise legato motion'],
    far: ['远 天涯 千里 万里 遥 隔 far distant distance away miles horizon faraway beyond remote', 'wide leaps'],
    home: ['家 归 回 故乡 返 home return returns returning back homeward homecoming', 'line ends on the tonic'],
    night: ['月 夜 星 梦 暗 黑 影 moon moonlight night nights star stars dream dreams dark shadow shadows midnight', 'lower register, softer'],
    light: ['火 光 燃 日 阳 亮 晨 曦 fire light lights burn burning sun sunlight dawn bright neon blaze glow shine', 'higher register, louder']
  };
  var PAINT_SETS = {};
  for (var pk in PAINTING) PAINT_SETS[pk] = uniq(words(PAINTING[pk][0]));
  var PAINT_KEYS = Object.keys(PAINTING);

  function detectPoemForm(stanzas, language) {
    var lengths = [];
    for (var si = 0; si < stanzas.length; si++) for (var li = 0; li < stanzas[si].lines.length; li++) lengths.push(stanzas[si].lines[li].syllables.length);
    var n = lengths.length;
    if (!n) return 'empty';
    var distinct = uniq(lengths).length;
    if (language === 'zh' && (n === 4 || n === 8) && distinct === 1 && (lengths[0] === 5 || lengths[0] === 7)) {
      return (lengths[0] === 5 ? '五言' : '七言') + (n === 4 ? '绝句' : '律诗');
    }
    if (language === 'zh' && distinct <= 2 && n >= 4 && maxOf(lengths) <= 7) return '古体/齐言诗';
    var first = (stanzas.length && stanzas[0].lines.length) ? stanzas[0].lines[0].text : '';
    if (/^(亲爱的|敬爱的|尊敬的|dear|hi|hello|to )/.test(first.trim().toLowerCase())) return 'letter';
    if (n === 14 && language === 'en') return 'sonnet';
    if (stanzas.every(function (st) { return st.lines.length === 4; })) return 'quatrains';
    if (stanzas.length === 1 && n <= 2) return n === 2 ? 'couplet' : 'single line';
    return 'free verse';
  }

  function planForm(n, poemForm, rngChoice) {
    if (n === 1) return 'A';
    if (n === 2) return 'AB';
    if (n === 3) return 'ABA';
    if (n === 4) return rngChoice(['AABA', 'ABAB']);
    var letters = [];
    for (var i = 0; i < n; i++) {
      if (i % 2 === 0) letters.push('A');
      else letters.push((Math.floor(i / 2) % 2 === 0) ? 'B' : 'C');
    }
    if (poemForm === 'letter') letters[letters.length - 1] = 'A';
    return letters.join('');
  }

  function paintLine(line) {
    var text = line.text.toLowerCase();
    var tokens = text.match(/[a-z']+/g) || [];
    var found = [];
    for (var ki = 0; ki < PAINT_KEYS.length; ki++) {
      var key = PAINT_KEYS[ki], ws = PAINT_SETS[key];
      for (var wi = 0; wi < ws.length; wi++) {
        var w = ws[wi];
        if ((/[一-鿿]/.test(w) && text.indexOf(w) >= 0) || includes(tokens, w)) { found.push(key); break; }
      }
    }
    return found;
  }

  function interpret(f, rngChoice, form) {
    form = form || 'auto';
    var stanzas = f.stanzas, n = stanzas.length;
    var poemForm = detectPoemForm(stanzas, f.language);
    var formStr = form !== 'auto' ? form : planForm(n, poemForm, rngChoice);
    if (formStr.length < n) {
      var reps = Math.floor(n / formStr.length) + 1, s = '';
      for (var r = 0; r < reps; r++) s += formStr;
      formStr = s.slice(0, n);
    }
    formStr = formStr.slice(0, n);

    var readings = [], intensities = [];
    for (var i = 0; i < n; i++) {
      var st = stanzas[i];
      var text = st.lines.map(function (l) { return l.text; }).join('\n');
      var a = affectOf(text);
      var syl = 0;
      for (var li = 0; li < st.lines.length; li++) syl += st.lines[li].syllables.length;
      var w = Math.min(1.0, syl / 24.0);
      var val = w * a.valence + (1 - w) * f.valence;
      var aro = w * a.arousal + (1 - w) * f.arousal;
      var ten = w * a.tension + (1 - w) * f.tension;
      var pos = i / Math.max(1, n - 1);
      intensities.push(aro + 0.4 * Math.abs(val) + 0.3 * ten - 0.35 * Math.abs(pos - 0.62));
      var lines = [];
      for (li = 0; li < st.lines.length; li++) {
        var role = '';
        if (st.lines.length === 4) role = '起承转合'[li];
        lines.push({ index: li, text: st.lines[li].text, devices: paintLine(st.lines[li]), role: role, open_ending: null });
      }
      readings.push({ index: i, label: formStr[i], valence: val, arousal: aro, tension: ten, role: '', dynamic: 0.5, lines: lines });
    }

    var climax = 0;
    if (n > 1) { for (i = 1; i < n; i++) if (intensities[i] > intensities[climax]) climax = i; }
    for (i = 0; i < n; i++) {
      var rd = readings[i];
      if (n === 1) { rd.role = 'single'; rd.dynamic = 0.6 + 0.3 * rd.arousal; }
      else if (i === climax) { rd.role = 'climax'; rd.dynamic = 1.0; }
      else if (i === n - 1) { rd.role = 'resolution'; rd.dynamic = 0.45 + 0.3 * rd.arousal; }
      else if (i === 0) { rd.role = 'exposition'; rd.dynamic = 0.5 + 0.3 * rd.arousal; }
      else if (i < climax) { rd.role = 'development'; rd.dynamic = 0.55 + 0.35 * rd.arousal + 0.15 * (i / Math.max(1, climax)); }
      else { rd.role = 'release'; rd.dynamic = 0.5 + 0.3 * rd.arousal; }
      if (poemForm === 'letter') {
        if (i === 0 && stanzas[0].lines.length === 1) { rd.role = 'salutation'; rd.dynamic = 0.4; }
        var lastSyl = 0;
        for (li = 0; li < stanzas[n - 1].lines.length; li++) lastSyl += stanzas[n - 1].lines[li].syllables.length;
        if (i === n - 1 && n > 2 && lastSyl <= 14) { rd.role = 'farewell'; rd.dynamic = 0.4; }
      }
      rd.dynamic = Math.min(1.0, Math.max(0.25, rd.dynamic));
    }

    var notes = ['Poem form: ' + poemForm + '; musical form ' + formStr + ' (sections sharing a letter share harmony and the head motif).'];
    if (n > 1) {
      notes.push('Emotional arc: climax at stanza ' + (climax + 1) + ' (' +
        readings.map(function (rd) { return rd.role + ' ' + fixed(rd.dynamic, 2); }).join(', ') + ').');
    }
    var painted = [];
    for (i = 0; i < readings.length; i++) {
      for (li = 0; li < readings[i].lines.length; li++) {
        var lr = readings[i].lines[li];
        if (lr.devices.length) painted.push([readings[i].index + 1, lr.index + 1, lr.devices]);
      }
    }
    if (painted.length) {
      notes.push('Word painting: ' + painted.slice(0, 8).map(function (p) {
        return 'stanza ' + p[0] + ' line ' + p[1] + ': ' + p[2].map(function (d) { return PAINTING[d][1]; }).join(', ');
      }).join('; '));
    }
    if (stanzas.some(function (st) { return st.lines.length === 4; })) {
      notes.push('Four-line stanzas follow 起承转合: line 3 turns (colour chord, higher register), line 4 concludes with the strongest cadence.');
    }
    return { poem_form: poemForm, form: formStr, climax_index: climax, stanzas: readings, notes: notes };
  }

  function interpretationToDict(interp) {
    var d = deepCopy(interp);
    for (var i = 0; i < d.stanzas.length; i++) {
      var st = d.stanzas[i];
      st.valence = roundN(st.valence, 3); st.arousal = roundN(st.arousal, 3);
      st.tension = roundN(st.tension, 3); st.dynamic = roundN(st.dynamic, 3);
    }
    return d;
  }

  // =========================================================================
  // score.py (data model + Timeline)
  // =========================================================================
  function Note(start, duration, pitch, velocity, lyric, tone) {
    return { start: start, duration: duration, pitch: pitch, velocity: velocity === undefined ? 90 : velocity,
      lyric: lyric || '', tone: tone || 0 };
  }

  function Timeline(bpm, beatsPerBar, swing) {
    this.bpm = bpm;
    this.beats_per_bar = beatsPerBar === undefined ? 4 : beatsPerBar;
    this.swing = swing === undefined ? 0.5 : swing;
    this.rit_start = null;
    this.rit_end = null;
    this.rit_factor = 0.65;
  }
  Timeline.prototype.swung = function (beat) {
    if (Math.abs(this.swing - 0.5) < 1e-6) return beat;
    var whole = Math.floor(beat), frac = beat - whole, s = this.swing;
    if (frac < 0.5) frac = frac * 2 * s;
    else frac = s + (frac - 0.5) * 2 * (1 - s);
    return whole + frac;
  };
  Timeline.prototype.seconds = function (beat) {
    var b = this.swung(beat);
    var spb = 60.0 / this.bpm;
    if (this.rit_start === null || this.rit_end === null || b <= this.rit_start) return b * spb;
    var L = this.rit_end - this.rit_start;
    var k = L > 0 ? (1 - this.rit_factor) / L : 0.0;
    var base = this.rit_start * spb;
    function integ(x) {
      if (k <= 0) return spb * x;
      x = Math.min(x, (1 - 1e-6) / k);
      return -spb / k * Math.log(1 - k * x);
    }
    if (b <= this.rit_end) return base + integ(b - this.rit_start);
    return base + integ(L) + (b - this.rit_end) * spb / this.rit_factor;
  };
  Timeline.prototype.toDict = function () {
    return { bpm: this.bpm, beats_per_bar: this.beats_per_bar, swing: this.swing, rit_start: this.rit_start,
      rit_end: this.rit_end, rit_factor: this.rit_factor };
  };
  function timelineFromDict(d) {
    var tl = new Timeline(d.bpm, d.beats_per_bar, d.swing);
    tl.rit_start = d.rit_start === undefined ? null : d.rit_start;
    tl.rit_end = d.rit_end === undefined ? null : d.rit_end;
    tl.rit_factor = d.rit_factor === undefined ? 0.65 : d.rit_factor;
    return tl;
  }

  // =========================================================================
  // melody.py
  // =========================================================================
  var CAESURA_PUNCT = '，、；：—…,;:';
  function isCjkRange(ch) { var cp = ch.codePointAt(0); return cp >= 0x3400 && cp <= 0x9FFF; }

  // Indices of syllables after which the line breathes (顿 / caesura). Punctuation inside
  // the line always breaks it; classical Chinese metres break where the reader does
  // (五言 2+3, 七言 4+3); English lines break only at punctuation.
  function caesuraPoints(line) {
    var syls = line.syllables, n = syls.length;
    var points = [], count = 0, i;
    var zh = n ? syls.every(function (x) { return chars(x).length === 1 && isCjkRange(x); }) : false;
    if (zh) {
      var cs = chars(line.text);
      for (i = 0; i < cs.length; i++) {
        var ch = cs[i];
        if (isCjkRange(ch)) count += 1;
        else if (CAESURA_PUNCT.indexOf(ch) >= 0 && 0 < count && count < n) points.push(count - 1);
      }
    } else {
      var re = /[A-Za-z']+|[0-9]|[，、；：—…,;:]/g, m;
      while ((m = re.exec(line.text)) !== null) {
        var tok = m[0];
        if (CAESURA_PUNCT.indexOf(tok) >= 0) { if (0 < count && count < n) points.push(count - 1); }
        else if (/^[0-9]$/.test(tok)) count += 1;
        else count += englishSyllables(tok).length;
      }
    }
    if (!points.length && zh) {
      if (n === 5) points = [1];
      else if (n === 7) points = [3];
      else if (n === 4) points = [1];
      else if (n === 6) points = [1, 3];
      else if (n >= 8 && n % 2 === 0) points = [n / 2 - 1];
    }
    return uniq(points.filter(function (p) { return 0 <= p && p < n - 1; })).sort(function (x, y) { return x - y; });
  }

  // Rhythm follows the text's prosody: syllables before a caesura are lengthened and followed
  // by a breath; for Chinese, level tones (平) are long and oblique tones (仄) short (平长仄短).
  // `stretch` > 1 slows the line (word painting for stillness); `regular` (0..1) reduces syncopation.
  function planRhythm(line, beatsPerBar, arousal, irregularity, rng, minBars, stretch, tones, regular) {
    if (minBars === undefined) minBars = 1;
    if (stretch === undefined) stretch = 1.0;
    if (regular === undefined) regular = 0.5;
    var n = line.syllables.length;
    tones = (tones && tones.length) ? tones.slice() : tonesOf(line.syllables);
    var breaks = caesuraPoints(line);
    var inBreaks = function (i) { return includes(breaks, i); };
    var weights = [], i;
    for (i = 0; i < n; i++) {
      var w = 1.0;
      var t = i < tones.length ? tones[i] : 0;
      if (t === 1 || t === 2) w *= 1.2;
      else if (t === 3 || t === 4) w *= 0.85;
      if (inBreaks(i)) w *= 1.6;
      if (i === n - 1) w *= 1.5;
      weights.push(w);
    }
    var wsum = sum(weights);
    var base = (1.05 - 0.6 * arousal) * stretch;
    var tail = arousal < 0.5 ? 1.0 : 0.5;          // breath at the end of the phrase
    var breath = arousal < 0.6 ? 0.5 : 0.25;       // breath after a caesura
    var need = wsum * base + tail + breath * breaks.length;
    var bars = Math.max(minBars, Math.ceil(need / beatsPerBar));
    var grid = arousal < 0.6 ? 0.5 : 0.25;
    var total = bars * beatsPerBar;
    var avail = total - tail;
    while ((n + breaks.length) * grid > avail) {
      if (grid > 0.25) grid = 0.25;
      else { bars += 1; total = bars * beatsPerBar; avail = total - tail; }
    }
    // Allocate beats proportionally, breaths included, and snap to the grid.
    var sing = avail - breath * breaks.length;
    var onsets = [], cursor = 0.0;
    for (i = 0; i < n; i++) {
      onsets.push(pyRound(cursor / grid) * grid);
      cursor += weights[i] / wsum * sing;
      if (inBreaks(i)) cursor += breath;
    }
    // Repair collisions after rounding.
    for (i = 1; i < n; i++) if (onsets[i] <= onsets[i - 1]) onsets[i] = onsets[i - 1] + grid;
    while (onsets.length && onsets[onsets.length - 1] > avail - grid) {
      var prevOnsets = onsets;
      onsets = prevOnsets.map(function (o, k) {
        return (k > 0 && prevOnsets[k] > prevOnsets[k - 1] + grid) ? o - grid : o;
      });
      if (onsets[onsets.length - 1] > avail - grid) {
        bars += 1; total = bars * beatsPerBar; avail = total - tail;
        break;
      }
    }
    // Light syncopation for irregular / energetic texts, never at a caesura.
    var jitter = (0.05 + 0.3 * irregularity + 0.2 * arousal) * (1.0 - regular);
    for (i = 1; i < n; i++) {
      if (inBreaks(i - 1) || inBreaks(i)) continue;
      if (rng.random() < jitter) {
        var cand = onsets[i] + rng.choice([-grid, grid]);
        var lo = onsets[i - 1] + grid;
        var hi = i + 1 < n ? onsets[i + 1] - grid : avail - grid;
        if (lo <= cand && cand <= hi) onsets[i] = cand;
      }
    }
    onsets[0] = 0.0;
    var durations = [];
    for (i = 0; i < onsets.length; i++) {
      var nxt = i + 1 < n ? onsets[i + 1] : avail;
      var dur = nxt - onsets[i];
      if (inBreaks(i)) dur = Math.max(grid, dur - breath);   // the breath after the caesura
      if (i + 1 < n) dur = Math.min(dur, 2.0);
      else dur = Math.min(Math.max(dur, 1.0), 3.0);
      durations.push(dur);
    }
    return { line: line, bars: bars, onsets: onsets, durations: durations, breaks: breaks.slice() };
  }

  function phraseArc(x, line, ending) {
    if (line.ends_with_question) return 0.25 + 0.75 * Math.pow(x, 1.5);
    if (line.ends_with_exclamation) return 1.0 - 0.7 * x;
    if (line.ends_with_ellipsis) return 0.4 - 0.3 * x + 0.15 * Math.sin(6.0 * x);
    var peak = ending === 'open' ? 0.5 : 0.62;
    var y = 1.0 - Math.pow((x - peak) / Math.max(peak, 1e-6), 2);
    return Math.max(0.0, y);
  }

  var signatureCache = {};
  function signature(token) {
    if (Object.prototype.hasOwnProperty.call(signatureCache, token)) return signatureCache[token];
    var r = new Random(tokenSeed(token));
    var v = r.choice([-3, -2, -2, -1, -1, 0, 0, 0, 1, 1, 2, 2, 3]);
    signatureCache[token] = v;
    return v;
  }

  function MelodyConfig(o) {
    var d = { center: 67, span: 12, melody_scale: 'mode', arousal: 0.4, valence: 0.0, tension: 0.3, temperature: 0.6,
      repeat_penalty: 0.8, tone_weight: 3.0, ornament_prob: 0.5 };
    return assign(d, o || {});
  }

  function melodyPcs(tonic, mode, melodyScale) {
    var base;
    if (melodyScale === 'pentatonic') base = isMajorLike(mode) ? SCALES.major_pentatonic : SCALES.minor_pentatonic;
    else if (melodyScale === 'blues') base = SCALES.blues;
    else base = SCALES[mode];
    return base.map(function (i) { return mod(tonic + i, 12); });
  }

  function chordAt(chords, beat) {
    for (var i = 0; i < chords.length; i++) {
      var c = chords[i];
      if (c.start <= beat && beat < c.start + c.duration) return c;
    }
    return chords.length ? chords[chords.length - 1] : null;
  }

  // Nearest allowed pitch below `pitch` that is not a semitone above a chord tone
  // (grace notes land on the beat, so they must not clash).
  function scaleStepBelow(pitch, allowed, chordPcs) {
    chordPcs = chordPcs || [];
    for (var d = 1; d < 5; d++) {
      var cand = pitch - d, cpc = mod(cand, 12);
      if (!includes(allowed, cpc)) continue;
      var clash = false;
      if (!includes(chordPcs, cpc)) {
        for (var k = 0; k < chordPcs.length; k++) if (mod(cand - chordPcs[k], 12) === 1) { clash = true; break; }
      }
      if (!clash) return cand;
    }
    return pitch - 2;
  }

  function MelodyState() {
    this.prev_pitch = null;
    this.prev_interval = 0;
    this.prev_sign = 1;
    this.repeats = 0;
    this.prev_nonchord = false;      // the previous note was a non-chord tone (must resolve by step)
  }

  // Scale tones a semitone away from a chord tone that is *not* in the scale (the b7 against a
  // major V in minor, the natural 6 against a borrowed iv ...): the classic wrong-note clash.
  function avoidNotes(scale, chordPcs) {
    var out = [];
    for (var i = 0; i < chordPcs.length; i++) {
      var ct = chordPcs[i];
      if (includes(scale, ct)) continue;
      var nb = [mod(ct - 1, 12), mod(ct + 1, 12)];
      for (var k = 0; k < 2; k++) if (includes(scale, nb[k]) && !includes(out, nb[k])) out.push(nb[k]);
    }
    return out;
  }

  // How restful a chord tone is: root/fifth > third > seventh > extensions.
  var STABILITY = [1.0, 0.85, 1.0, 0.55, 0.35, 0.3];
  function stability(pc, chordPcs) {
    var idx = chordPcs.indexOf(pc);
    if (idx < 0) return 0.0;
    return idx < 6 ? STABILITY[idx] : 0.3;
  }

  function singLine(phrase, chords, beatsPerBar, cfg, rng, state) {
    var plan = phrase.plan, line = plan.line;
    var tonic = phrase.tonic, mode = phrase.mode;
    var scale = melodyPcs(tonic, mode, cfg.melody_scale);
    var devices = phrase.devices || [];
    var has = function (d) { return includes(devices, d); };
    var center = cfg.center + phrase.register_shift + (has('night') ? -3 : 0) + (has('light') ? 2 : 0);
    var lo = center - cfg.span, hi = center + cfg.span;
    var amplitude = 4.0 + 5.0 * cfg.arousal;
    var strongBeats = beatsPerBar === 4 ? [0, 2] : [0];
    var tones = (phrase.tones && phrase.tones.length) ? phrase.tones.slice() : tonesOf(line.syllables);
    var zh = tones.some(function (t) { return t; });
    var n = plan.onsets.length;
    var lineRng = subRandom(rng);
    var baseOffset = lineRng.choice([-2, -1, 0, 0, 1, 2]);
    var notes = [];
    var prevTone = 0;

    for (var i = 0; i < n; i++) {
      var rel = plan.onsets[i], dur = plan.durations[i];
      var beat = phrase.start + rel;
      var chord = chordAt(chords, beat);
      var chordPcs = chord ? chord.pcs : [tonic];
      var x = n > 1 ? i / Math.max(1, n - 1) : 0.5;
      var arc = phraseArc(x, line, phrase.ending);
      if (has('rise')) arc = 0.6 * arc + 0.4 * x;
      if (has('fall')) arc = 0.6 * arc + 0.4 * (1 - x);
      var token = line.syllables[i];
      var tone = i < tones.length ? tones[i] : 0;
      var target = center + baseOffset + (arc - 0.4) * amplitude + signature(token) * 0.4;
      if (tone) target += (TONE_LEVEL[tone] - 0.55) * 4.0;
      var posInBar = mod(beat, beatsPerBar);
      var strong = includes(strongBeats, pyRound(posInBar * 4) / 4);
      var chordEnd = chordAt(chords, beat + dur - 0.01);
      var nextChord = (chordEnd !== chord && chord !== null && beat + dur - (chord.start + chord.duration) >= 0.5) ? chordEnd : null;
      var atBreak = includes(plan.breaks || [], i);
      var last = i === n - 1;
      var first = i === 0;
      var wantDir = (zh && cfg.tone_weight > 0 && !first) ? toneDirection(prevTone, tone) : 0;
      var motifIv = null;
      if (phrase.motif && phrase.motif.length && i < phrase.motif.length + 1 && i > 0 && state.prev_pitch !== null) {
        motifIv = phrase.motif[i - 1];
      }
      var avoid = avoidNotes(scale, chordPcs);
      var scaleOk = scale.filter(function (pc) { return !includes(avoid, pc); });
      var allowed = (strong || last) ? uniq(scaleOk.concat(chordPcs)) : scaleOk;
      var best = null;
      for (var p = lo; p <= hi; p++) {
        if (!includes(allowed, mod(p, 12))) continue;
        var score = -Math.abs(p - target);
        var inChord = includes(chordPcs, mod(p, 12));
        var stab = stability(mod(p, 12), chordPcs);
        if (strong) score += inChord ? 3.2 * stab : -1.0;
        else score += inChord ? 0.9 * stab : 0.0;
        if (!inChord) {
          // A scale tone a semitone *above* a chord tone (the jazz "avoid note": 4 over a major
          // triad, b9 over a dominant) is harsh unless it passes quickly.
          var semiAbove = false;
          for (var ci = 0; ci < chordPcs.length; ci++) if (mod(p - chordPcs[ci], 12) === 1) { semiAbove = true; break; }
          if (semiAbove) score -= 1.5 + (dur >= 1.0 ? 1.5 : 0.0);
        }
        if (state.prev_pitch !== null) {
          var d = Math.abs(p - state.prev_pitch);
          var sgn = p > state.prev_pitch ? 1 : (p < state.prev_pitch ? -1 : 0);
          if (d > (has('far') ? 12 : 9)) continue;
          if (d > 7) score -= has('far') ? 1.0 : 5.0;
          else if (d > 4) score -= has('far') ? -0.5 : 1.5;
          if (d > 4 && state.prev_interval > 4 && sgn * state.prev_sign > 0) score -= 3.0;   // two leaps in the same direction
          if (state.prev_nonchord) score += d <= 2 ? 1.5 : -2.0;   // a non-chord tone resolves by step
          if (has('flow') && d > 2) score -= 1.5;
          if (d === 6 || d === 10 || d === 11) score -= 2.5;
          if (d === 0) score -= cfg.repeat_penalty * (1 + state.repeats);
          if (!inChord && d > 2) score -= 2.0;
          if (state.prev_interval > 4 && d <= 2 && sgn * state.prev_sign < 0) score += 2.0;
          if (first && d <= 4) score += 0.5;
          if (wantDir) {
            if (sgn === wantDir) score += cfg.tone_weight;
            else if (sgn === -wantDir) score -= cfg.tone_weight * 1.5;
            else score -= cfg.tone_weight * 0.4;
          }
          if (motifIv !== null) score += (p - state.prev_pitch) === motifIv ? 4.0 : 0.0;
        } else {
          if (!inChord) score -= 2.0;
        }
        if (atBreak) score += inChord ? 1.2 : -1.2;   // the lengthened syllable before a caesura rests on a chord tone
        // Phrase endings rest on triad tones, not on sevenths or extensions.
        if (last) {
          var deg = mod(p - tonic, 12);
          var rootPc = chord ? chord.root : tonic;
          var third = (chord && chord.pcs.length > 1) ? chord.pcs[1] : rootPc;
          var ppc = mod(p, 12);
          if (inChord && chordPcs.indexOf(ppc) >= 3) score -= 2.0;
          if (phrase.ending === 'open') {
            if (deg === 7 || deg === 2) score += 2.5;
            if (ppc === tonic) score -= 1.0;
          } else if (phrase.ending === 'semi') {
            if (inChord && ppc !== rootPc) score += 2.0;
            if (ppc === tonic) score -= 1.5;
          } else if (phrase.ending === 'closed') {
            if (ppc === rootPc) score += 1.5;
            else if (ppc === third) score += 1.0;
          } else {
            if (ppc === rootPc) score += 2.5;
            if (ppc === tonic) score += 3.0;
          }
          if (has('home') && ppc === tonic) score += 2.0;
        }
        if (nextChord !== null) {
          // The note is held into the next chord: it must belong there too.
          var npcs = nextChord.pcs, pp = mod(p, 12);
          if (!includes(npcs, pp)) {
            score -= 2.5;
            for (var ni2 = 0; ni2 < npcs.length; ni2++) if (mod(p - npcs[ni2], 12) === 1) { score -= 3.0; break; }
          }
        }
        if (p > center + 10 || p < center - 9) score -= 3.0;
        score += lineRng.random() * cfg.temperature;
        if (best === null || score > best[0]) best = [score, p];
      }
      if (best === null) throw new Error('no melodic candidate');
      var pitch = best[1];
      if (state.prev_pitch !== null) {
        var iv = pitch - state.prev_pitch;
        state.repeats = iv === 0 ? state.repeats + 1 : 0;
        state.prev_interval = Math.abs(iv);
        state.prev_sign = iv > 0 ? 1 : (iv < 0 ? -1 : state.prev_sign);
      }
      state.prev_pitch = pitch;
      state.prev_nonchord = !includes(chordPcs, mod(pitch, 12));
      var vel = 62 + Math.trunc(34 * cfg.arousal) + (strong ? 8 : 0) + Math.trunc(8 * arc) + phrase.velocity_shift +
        (has('night') ? -8 : 0) + (has('light') ? 6 : 0) + lineRng.randint(-4, 4);
      vel = Math.max(30, Math.min(127, vel));

      var ornamentOk = zh && (tone === 2 || tone === 3 || tone === 4) && dur >= 0.75 && !has('still') &&
        lineRng.random() < cfg.ornament_prob;
      if (ornamentOk && (tone === 2 || tone === 3)) {
        var grace = Math.min(0.25, dur / 3);
        var below = scaleStepBelow(pitch, allowed, chordPcs);
        if (tone === 3) below = scaleStepBelow(below, allowed, chordPcs);
        notes.push(Note(beat, grace, below, Math.max(30, vel - 14), '', tone));
        notes.push(Note(beat + grace, dur - grace, pitch, vel, token, tone));
      } else if (ornamentOk && tone === 4) {
        var tail = Math.min(0.25, dur / 3);
        notes.push(Note(beat, dur - tail, pitch, vel, token, tone));
        notes.push(Note(beat + dur - tail, tail, scaleStepBelow(pitch, allowed, chordPcs), Math.max(30, vel - 18), '', tone));
      } else {
        notes.push(Note(beat, dur, pitch, vel, token, tone));
      }
      prevTone = tone;
    }
    state.prev_interval = 0;
    return notes;
  }

  function headMotif(notes, length) {
    if (length === undefined) length = 4;
    var sung = notes.filter(function (n) { return n.lyric; }).slice(0, length);
    var out = [];
    for (var i = 1; i < sung.length; i++) out.push(sung[i].pitch - sung[i - 1].pitch);
    return out;
  }

  function generateMelody(phrases, chords, beatsPerBar, cfg, rng, state) {
    state = state || new MelodyState();
    var out = [];
    for (var i = 0; i < phrases.length; i++) out = out.concat(singLine(phrases[i], chords, beatsPerBar, cfg, rng, state));
    return out;
  }

  // =========================================================================
  // synth.py
  // =========================================================================
  function Osc(wave, octave, detune, level, pulseWidth) {
    return { wave: wave || 'saw', octave: octave || 0, detune: detune || 0.0, level: level === undefined ? 1.0 : level,
      pulse_width: pulseWidth === undefined ? 0.5 : pulseWidth };
  }
  function Env(attack, decay, sustain, release) {
    return { attack: attack === undefined ? 0.01 : attack, decay: decay === undefined ? 0.2 : decay,
      sustain: sustain === undefined ? 0.8 : sustain, release: release === undefined ? 0.3 : release };
  }
  function Patch(name, role, o) {
    var d = { name: name, role: role, oscs: [Osc()], unison: 1, unison_detune: 0.0, cutoff: 2000.0, resonance: 0.1,
      filter_env_amount: 0.0, filter_env: Env(0.01, 0.3, 0.0, 0.3), amp_env: Env(), key_tracking: 0.3, lfo_rate: 0.0,
      lfo_depth: 0.0, lfo_target: 'pitch', lfo_delay: 0.0, drive: 0.0, noise: 0.0, glide: 0.0, reverb_mix: 0.2,
      reverb_size: 2.0, delay_time: 0.0, delay_feedback: 0.3, delay_mix: 0.0, chorus: 0.0, pan: 0.0, level: 0.8, recipe: '' };
    return assign(d, o || {});
  }

  function lerp(a, b, t) { return a + (b - a) * Math.max(0.0, Math.min(1.0, t)); }

  function recipe(p) {
    var osc = p.oscs.map(function (o) {
      return o.wave + (o.octave === 0 ? '' : ' ' + fmtSigned(o.octave) + 'oct') +
        (!o.detune ? '' : ' ' + (o.detune >= 0 ? '+' : '') + fixed(o.detune, 0) + 'c');
    }).join(' + ');
    var uni = p.unison > 1 ? ', unison x' + p.unison + ' (' + fixed(p.unison_detune, 0) + 'c)' : '';
    var lfo = p.lfo_rate ? '; LFO ' + fixed(p.lfo_rate, 2) + 'Hz -> ' + p.lfo_target + ' (' + fmtG(p.lfo_depth) + ')' : '';
    var fx = '; reverb ' + pct0(p.reverb_mix) + ' (' + fixed(p.reverb_size, 1) + 's)';
    if (p.delay_mix) fx += ', delay ' + fmtG(p.delay_time) + ' beat fb ' + pct0(p.delay_feedback) + ' mix ' + pct0(p.delay_mix);
    if (p.chorus) fx += ', chorus ' + pct0(p.chorus);
    var fe = p.filter_env, ae = p.amp_env;
    return osc + uni + '; LPF ' + fixed(p.cutoff, 0) + 'Hz Q ' + fixed(p.resonance, 2) + ' env +' + fixed(p.filter_env_amount, 1) + 'oct ' +
      '(A' + fixed(fe.attack, 2) + ' D' + fixed(fe.decay, 2) + ' S' + fixed(fe.sustain, 2) + ' R' + fixed(fe.release, 2) + '); ' +
      'amp A' + fixed(ae.attack, 2) + ' D' + fixed(ae.decay, 2) + ' S' + fixed(ae.sustain, 2) + ' R' + fixed(ae.release, 2) +
      lfo + fx;
  }

  function designPatches(f, style, rng) {
    var warm = f.warmth, ar = f.arousal, ten = f.tension, val = f.valence;
    var bright = 0.5 + 0.5 * val;
    var padCut = lerp(900, 4200, 0.6 * bright + 0.4 * (1 - warm));
    var leadCut = lerp(1500, 6500, 0.5 * bright + 0.5 * ar);
    var reverbSize = lerp(1.4, 5.0, 0.5 * (1 - ar) + 0.5 * (1 - bright));
    var detune = lerp(4, 22, ten);
    var res = lerp(0.05, 0.45, 0.5 * ten + 0.5 * ar);
    var attPad = lerp(1.2, 0.15, ar);
    var relPad = lerp(2.5, 0.6, ar);
    var fam = style.family, name = style.name;
    var patches = {};
    var pad, keys, bass, lead;

    // ---- PAD
    if (includes(['classical', 'romantic', 'cinematic', 'folk'], name)) {
      pad = Patch(warm > 0.5 ? 'Chamber Strings' : 'Glass Strings', 'pad', {
        oscs: [Osc('saw', 0, -detune * 0.5, 0.6), Osc('saw', 0, detune * 0.5, 0.6), Osc('triangle', -1, 0, 0.35)],
        cutoff: lerp(1400, 3200, bright), resonance: 0.05,
        amp_env: Env(attPad * 0.8, 0.5, 0.85, relPad), filter_env_amount: 0.4,
        filter_env: Env(attPad, 1.0, 0.6, relPad),
        lfo_rate: 5.2, lfo_depth: 5, lfo_target: 'pitch', lfo_delay: 0.6,
        reverb_mix: 0.35, reverb_size: reverbSize, chorus: 0.3, level: 0.55 });
    } else if (name === 'ambient') {
      pad = Patch('Slow Aurora', 'pad', {
        oscs: [Osc('sine', 0, 0, 0.7), Osc('triangle', 0, detune, 0.5), Osc('saw', 1, -detune, 0.2)],
        cutoff: lerp(700, 2400, bright), resonance: 0.15,
        amp_env: Env(lerp(3.0, 1.2, ar), 1.0, 0.9, 4.0), filter_env_amount: 0.8,
        filter_env: Env(4.0, 2.0, 0.5, 4.0), lfo_rate: 0.08, lfo_depth: 0.6, lfo_target: 'cutoff',
        reverb_mix: 0.55, reverb_size: reverbSize + 2.0, chorus: 0.5, level: 0.55 });
    } else if (name === 'synthwave' || name === 'trance') {
      pad = Patch(name === 'synthwave' ? 'Neon Supersaw' : 'Uplift Supersaw', 'pad', {
        oscs: [Osc('supersaw', 0, 0, 0.8), Osc('square', -1, 0, 0.25, 0.4)], unison: 7,
        unison_detune: lerp(12, 28, ten), cutoff: lerp(1800, 5000, bright), resonance: 0.12,
        amp_env: Env(lerp(0.6, 0.05, ar), 0.4, 0.8, lerp(1.4, 0.5, ar)),
        filter_env_amount: 0.5, filter_env: Env(0.4, 1.2, 0.5, 1.0),
        reverb_mix: 0.3, reverb_size: reverbSize, chorus: 0.6, level: 0.5 });
    } else if (name === 'house') {
      pad = Patch('Deep Chord', 'pad', { oscs: [Osc('saw', 0, -8, 0.5), Osc('saw', 0, 8, 0.5), Osc('sine', -1, 0, 0.4)],
        cutoff: lerp(700, 1800, bright), resonance: 0.25,
        amp_env: Env(0.01, 0.35, 0.0, 0.3), filter_env_amount: 1.2, filter_env: Env(0.005, 0.25, 0.0, 0.3),
        reverb_mix: 0.25, reverb_size: 1.6, chorus: 0.4, level: 0.5 });
    } else {
      pad = Patch('Tape Pad', 'pad', { oscs: [Osc('triangle', 0, -detune * 0.4, 0.6), Osc('saw', 0, detune * 0.4, 0.35), Osc('sine', -1, 0, 0.3)],
        cutoff: padCut * 0.6, resonance: 0.08, amp_env: Env(attPad, 0.5, 0.8, relPad),
        lfo_rate: 0.35, lfo_depth: 7, lfo_target: 'pitch', reverb_mix: 0.3, reverb_size: reverbSize, chorus: 0.35, level: 0.45 });
    }
    patches.pad = pad;

    // ---- KEYS
    if (name === 'classical' || name === 'romantic') {
      keys = Patch('Felt Piano', 'keys', { oscs: [Osc('triangle', 0, 0, 0.7), Osc('saw', 0, 0, 0.3), Osc('sine', 1, 0, 0.25)],
        cutoff: lerp(1800, 4200, bright), resonance: 0.05, filter_env_amount: 1.8,
        filter_env: Env(0.002, 0.35, 0.1, 0.4), amp_env: Env(0.003, 1.4, 0.15, 0.6), key_tracking: 0.6,
        reverb_mix: 0.25, reverb_size: reverbSize * 0.8, level: 0.6 });
    } else if (name === 'folk') {
      keys = Patch('Zither Pluck', 'keys', { oscs: [Osc('triangle', 0, 0, 0.6), Osc('saw', 1, 3, 0.3), Osc('sine', 0, 0, 0.3)],
        cutoff: lerp(2500, 5500, bright), resonance: 0.1, filter_env_amount: 2.0,
        filter_env: Env(0.001, 0.25, 0.0, 0.3), amp_env: Env(0.002, 1.1, 0.0, 0.5), key_tracking: 0.7,
        reverb_mix: 0.3, reverb_size: reverbSize, delay_time: 0.75, delay_feedback: 0.2, delay_mix: 0.12, level: 0.55 });
    } else if (name === 'lofi' || name === 'jazz' || name === 'neo_soul') {
      keys = Patch('Dusty Rhodes', 'keys', { oscs: [Osc('sine', 0, 0, 0.8), Osc('triangle', 1, 0, 0.35), Osc('sine', 2, 0, 0.12)],
        cutoff: lerp(1200, 2600, bright), resonance: 0.1, filter_env_amount: 1.2,
        filter_env: Env(0.002, 0.5, 0.2, 0.5), amp_env: Env(0.004, 1.8, 0.35, 0.7), key_tracking: 0.5,
        lfo_rate: name !== 'lofi' ? 4.2 : 0.3, lfo_depth: name !== 'lofi' ? 0.25 : 5,
        lfo_target: name !== 'lofi' ? 'amp' : 'pitch', drive: 0.25,
        reverb_mix: 0.28, reverb_size: reverbSize * 0.7, chorus: 0.3, level: 0.6 });
    } else if (name === 'house') {
      keys = Patch('Organ Stab', 'keys', { oscs: [Osc('saw', 0, -6, 0.5), Osc('saw', 0, 6, 0.5), Osc('square', 1, 0, 0.2, 0.3)],
        cutoff: lerp(1400, 3600, bright), resonance: 0.3, filter_env_amount: 1.5,
        filter_env: Env(0.002, 0.18, 0.0, 0.2), amp_env: Env(0.002, 0.25, 0.0, 0.2),
        reverb_mix: 0.2, reverb_size: 1.4, delay_time: 0.75, delay_feedback: 0.3, delay_mix: 0.15, level: 0.55 });
    } else if (name === 'trance') {
      keys = Patch('Crystal Pluck', 'keys', { oscs: [Osc('saw', 0, -7, 0.5), Osc('saw', 0, 7, 0.5), Osc('square', 1, 0, 0.2)],
        cutoff: lerp(1500, 3000, bright), resonance: 0.35, filter_env_amount: 2.5,
        filter_env: Env(0.001, 0.12, 0.0, 0.15), amp_env: Env(0.001, 0.2, 0.0, 0.15),
        reverb_mix: 0.3, reverb_size: 2.4, delay_time: 0.75, delay_feedback: 0.4, delay_mix: 0.3, level: 0.5 });
    } else {
      keys = Patch('Arp Pluck', 'keys', { oscs: [Osc('saw', 0, -5, 0.5), Osc('square', 0, 5, 0.4, 0.35), Osc('sine', 1, 0, 0.15)],
        cutoff: lerp(1200, 3200, bright), resonance: 0.25, filter_env_amount: 2.0,
        filter_env: Env(0.002, 0.22, 0.05, 0.25), amp_env: Env(0.002, 0.45, 0.1, 0.3),
        reverb_mix: 0.3, reverb_size: reverbSize, delay_time: 0.75, delay_feedback: 0.35, delay_mix: 0.25, level: 0.5 });
    }
    patches.keys = keys;

    // ---- BASS
    if (fam === 'classical') {
      bass = Patch('Cello Section', 'bass', { oscs: [Osc('saw', 0, -4, 0.6), Osc('saw', 0, 4, 0.6), Osc('sine', 0, 0, 0.4)],
        cutoff: lerp(500, 1200, bright), resonance: 0.05, amp_env: Env(0.12, 0.3, 0.85, 0.6),
        lfo_rate: 5.0, lfo_depth: 4, lfo_target: 'pitch', lfo_delay: 0.4, reverb_mix: 0.2, reverb_size: reverbSize, level: 0.6 });
    } else if (name === 'lofi' || name === 'neo_soul') {
      bass = Patch('Sub Round', 'bass', { oscs: [Osc('sine', 0, 0, 0.9), Osc('triangle', 0, 0, 0.3)],
        cutoff: 500, resonance: 0.05, amp_env: Env(0.01, 0.4, 0.7, 0.25), drive: 0.2, reverb_mix: 0.0, level: 0.7 });
    } else if (name === 'jazz') {
      bass = Patch('Upright', 'bass', { oscs: [Osc('triangle', 0, 0, 0.8), Osc('sine', 0, 0, 0.5), Osc('saw', 0, 0, 0.15)],
        cutoff: 900, resonance: 0.05, filter_env_amount: 1.0, filter_env: Env(0.002, 0.2, 0.0, 0.2),
        amp_env: Env(0.005, 0.9, 0.2, 0.15), reverb_mix: 0.1, level: 0.65 });
    } else if (name === 'house') {
      bass = Patch('Acid Sub', 'bass', { oscs: [Osc('saw', 0, 0, 0.7), Osc('sine', 0, 0, 0.5)],
        cutoff: lerp(300, 800, ar), resonance: 0.45, filter_env_amount: 2.0, filter_env: Env(0.001, 0.15, 0.0, 0.15),
        amp_env: Env(0.002, 0.2, 0.3, 0.1), drive: 0.3, level: 0.65 });
    } else if (name === 'trance') {
      bass = Patch('Rolling Saw', 'bass', { oscs: [Osc('saw', 0, 0, 0.8), Osc('square', 0, 0, 0.3, 0.4), Osc('sine', -1, 0, 0.3)],
        cutoff: lerp(400, 900, ar), resonance: 0.3, filter_env_amount: 1.6, filter_env: Env(0.001, 0.09, 0.0, 0.1),
        amp_env: Env(0.001, 0.12, 0.4, 0.05), drive: 0.2, level: 0.6 });
    } else if (name === 'ambient') {
      bass = Patch('Drone Sub', 'bass', { oscs: [Osc('sine', 0, 0, 0.8), Osc('triangle', 1, 3, 0.2)],
        cutoff: 400, resonance: 0.0, amp_env: Env(2.0, 1.0, 0.9, 3.0), reverb_mix: 0.2, reverb_size: reverbSize, level: 0.55 });
    } else {
      bass = Patch('Analog Bass', 'bass', { oscs: [Osc('square', 0, 0, 0.6, 0.45), Osc('saw', 0, 0, 0.5), Osc('sine', -1, 0, 0.3)],
        cutoff: lerp(500, 1300, ar), resonance: 0.25, filter_env_amount: 1.4, filter_env: Env(0.002, 0.18, 0.0, 0.2),
        amp_env: Env(0.002, 0.3, 0.6, 0.12), drive: 0.15, level: 0.65 });
    }
    patches.bass = bass;

    // ---- LEAD
    var vibRate = lerp(4.6, 6.2, ar);
    if (fam === 'classical' && name !== 'folk') {
      lead = Patch(warm > 0.5 ? 'Oboe d\'Amore' : 'Silver Flute', 'lead', {
        oscs: [Osc('triangle', 0, 0, 0.6), Osc(warm > 0.5 ? 'saw' : 'sine', 0, 0, 0.45), Osc('sine', 1, 0, 0.15)],
        cutoff: lerp(1800, 3800, bright), resonance: 0.1, noise: 0.03,
        amp_env: Env(lerp(0.12, 0.03, ar), 0.2, 0.85, 0.35), filter_env_amount: 0.3, filter_env: Env(0.1, 0.3, 0.7, 0.3),
        lfo_rate: vibRate, lfo_depth: 12, lfo_target: 'pitch', lfo_delay: 0.35,
        reverb_mix: 0.3, reverb_size: reverbSize, level: 0.7 });
    } else if (name === 'folk') {
      lead = Patch('Bamboo Flute', 'lead', { oscs: [Osc('sine', 0, 0, 0.7), Osc('triangle', 0, 0, 0.35), Osc('sine', 2, 0, 0.06)],
        cutoff: lerp(2200, 4500, bright), resonance: 0.12, noise: 0.06,
        amp_env: Env(0.06, 0.15, 0.85, 0.3), lfo_rate: vibRate, lfo_depth: 18, lfo_target: 'pitch', lfo_delay: 0.3,
        glide: 0.03, reverb_mix: 0.35, reverb_size: reverbSize, level: 0.7 });
    } else if (name === 'synthwave' || name === 'trance') {
      lead = Patch(name === 'synthwave' ? 'Retro Lead' : 'Anthem Supersaw', 'lead', {
        oscs: [Osc('saw', 0, 0, 0.6), Osc('square', 0, -7, 0.4, 0.35), Osc('saw', 1, 5, 0.25)],
        unison: name === 'trance' ? 5 : 2, unison_detune: lerp(10, 22, ten),
        cutoff: leadCut, resonance: 0.2, filter_env_amount: 1.0, filter_env: Env(0.01, 0.4, 0.5, 0.3),
        amp_env: Env(0.01, 0.2, 0.8, 0.3), lfo_rate: vibRate, lfo_depth: 10, lfo_target: 'pitch', lfo_delay: 0.25,
        glide: 0.04, drive: 0.2, reverb_mix: 0.3, reverb_size: reverbSize,
        // Echoes of a fast sung line smear against the next chord, so the dotted-eighth
        // delay backs off as the text gets denser.
        delay_time: 0.75, delay_feedback: 0.3, delay_mix: lerp(0.3, 0.12, ar), level: 0.6 });
    } else if (name === 'lofi' || name === 'neo_soul' || name === 'jazz') {
      lead = Patch(name === 'jazz' ? 'Muted Horn' : 'Soft Square', 'lead', {
        oscs: [Osc('square', 0, 0, 0.5, 0.3), Osc('triangle', 0, 0, 0.5), Osc('sine', -1, 0, 0.2)],
        cutoff: lerp(1100, 2600, bright), resonance: 0.15, filter_env_amount: 0.6, filter_env: Env(0.03, 0.3, 0.5, 0.3),
        amp_env: Env(0.03, 0.3, 0.75, 0.35), lfo_rate: vibRate * 0.9, lfo_depth: 9, lfo_target: 'pitch', lfo_delay: 0.3,
        glide: 0.05, drive: 0.2, reverb_mix: 0.25, reverb_size: reverbSize * 0.8, delay_time: name === 'lofi' ? 1.0 : 0,
        delay_feedback: 0.25, delay_mix: name === 'lofi' ? 0.15 : 0, level: 0.65 });
    } else if (name === 'ambient') {
      lead = Patch('Distant Voice', 'lead', { oscs: [Osc('sine', 0, 0, 0.8), Osc('triangle', 0, 4, 0.3), Osc('sine', 1, 0, 0.1)],
        cutoff: lerp(1200, 2600, bright), resonance: 0.1, amp_env: Env(0.4, 0.5, 0.8, 1.5),
        lfo_rate: 4.5, lfo_depth: 8, lfo_target: 'pitch', lfo_delay: 0.6, glide: 0.08,
        reverb_mix: 0.5, reverb_size: reverbSize + 1.5, delay_time: 1.5, delay_feedback: 0.5, delay_mix: 0.35, level: 0.6 });
    } else {
      lead = Patch('Glass Lead', 'lead', { oscs: [Osc('saw', 0, -4, 0.5), Osc('triangle', 0, 4, 0.5), Osc('sine', 1, 0, 0.2)],
        cutoff: leadCut * 0.8, resonance: 0.15, filter_env_amount: 0.8, filter_env: Env(0.02, 0.3, 0.5, 0.3),
        amp_env: Env(0.02, 0.25, 0.8, 0.35), lfo_rate: vibRate, lfo_depth: 9, lfo_target: 'pitch', lfo_delay: 0.3,
        glide: 0.03, reverb_mix: 0.3, reverb_size: reverbSize, delay_time: 0.5, delay_feedback: 0.3, delay_mix: 0.2, level: 0.65 });
    }
    patches.lead = lead;

    var roles = ['pad', 'keys', 'bass', 'lead'];
    for (var ri = 0; ri < roles.length; ri++) {
      var p = patches[roles[ri]];
      var attrs = ['cutoff', 'resonance', 'filter_env_amount', 'unison_detune', 'reverb_size', 'reverb_mix', 'lfo_rate', 'lfo_depth'];
      for (var ai = 0; ai < attrs.length; ai++) p[attrs[ai]] = roundN(p[attrs[ai]], 3);
      var envs = [p.filter_env, p.amp_env];
      for (var ei = 0; ei < 2; ei++) {
        var env = envs[ei];
        env.attack = roundN(env.attack, 3); env.decay = roundN(env.decay, 3);
        env.sustain = roundN(env.sustain, 3); env.release = roundN(env.release, 3);
      }
      for (var oi = 0; oi < p.oscs.length; oi++) p.oscs[oi].detune = roundN(p.oscs[oi].detune, 2);
      p.recipe = recipe(p);
    }
    return patches;
  }

  // =========================================================================
  // compose.py
  // =========================================================================
  var WARM_KEYS = [5, 10, 3, 8, 1];      // F Bb Eb Ab Db
  var BRIGHT_KEYS = [7, 2, 9, 4, 0];     // G D A E C
  var TURN_CHORDS = { major: ['iv', 'bVI', 'vi', 'ii'], minor: ['IV', 'bII', 'VI', 'iv'] };
  var DRUM_NOTES = { kick: 36, snare: 38, clap: 39, hat: 42, ohat: 46, ride: 51 };

  function chooseMode(f, st, rng) {
    var v = f.valence, t = f.tension;
    var pMajor = 0.5 + 0.9 * v - 0.25 * (t - 0.4);
    var major = rng.random() < Math.max(0.05, Math.min(0.95, pMajor));
    var options = (major ? st.major_modes : st.minor_modes).slice();
    if (options.length > 1 && rng.random() < 0.25 + 0.5 * t) return options[1];
    return options[0];
  }

  function chooseTonic(f, rng) {
    return rng.choice(f.warmth >= 0.5 ? WARM_KEYS : BRIGHT_KEYS);
  }

  function moodTags(f) {
    var tags = [];
    if (f.valence > 0.2) tags.push('bright');
    else if (f.valence < -0.2) tags.push('dark');
    else tags.push('bittersweet');
    if (f.tension > 0.5) tags.push('tense');
    if (f.arousal < 0.3) tags.push('still');
    if (f.arousal > 0.65) tags.push('driving', 'epic');
    return tags;
  }

  // -> [name, harmonic mode, numerals]
  function progressionFor(st, mode, f, rng, cadence, exclude, isLast) {
    if (rng.random() < st.library_ratio) {
      var tags = moodTags(f).concat(isLast ? ['cadence'] : []).concat(cadence === 'half' ? ['tense', 'open'] : []);
      var p = pickProgression(st.name, mode, rng, tags, exclude);
      return [p.name, p.mode, p.numerals.slice()];
    }
    var opts = HarmonyOptions(st.harmony);
    opts.length = (f.density < 0.7 || rng.random() < 0.6) ? 4 : 8;
    opts.cadence = cadence;
    var harmMode = isMajorLike(mode) ? 'ionian' : 'aeolian';
    return ['generated (' + cadence + ' cadence)', harmMode, generateFunctional(harmMode, rng, opts)];
  }

  function bassPitch(pc) { return 36 + mod(pc - 36, 12); }

  function Arranger(comp, st, f, rng) {
    this.comp = comp; this.st = st; this.f = f; this.rng = rng;
    this.bpb = comp.time_signature[0];
  }
  Arranger.prototype.chordAt = function (beat) {
    var cs = this.comp.chords;
    for (var i = 0; i < cs.length; i++) if (cs[i].start <= beat && beat < cs[i].start + cs[i].duration) return cs[i];
    return cs[cs.length - 1];
  };
  Arranger.prototype.nextChord = function (c) {
    var cs = this.comp.chords;
    for (var i = 0; i < cs.length; i++) if (cs[i] === c && i + 1 < cs.length) return cs[i + 1];
    return c;
  };
  Arranger.prototype.bars = function (start, end) {
    var out = [], b = start;
    while (b < end - 1e-9) { out.push(b); b += this.bpb; }
    return out;
  };
  Arranger.prototype.pad = function (track) {
    var mode = this.st.pad;
    if (mode === 'none') return;
    var vel = 60 + Math.trunc(30 * this.f.arousal);
    var cs = this.comp.chords;
    for (var ci = 0; ci < cs.length; ci++) {
      var c = cs[ci];
      if (mode === 'sustain' || mode === 'swell') {
        for (var vi = 0; vi < c.voicing.length; vi++) track.notes.push(Note(c.start, c.duration - 0.05, c.voicing[vi], vel));
      } else if (mode === 'stab') {
        var bars = this.bars(c.start, c.start + c.duration);
        for (var bi = 0; bi < bars.length; bi++) {
          for (vi = 0; vi < c.voicing.length; vi++) {
            track.notes.push(Note(bars[bi], 1.5, c.voicing[vi], vel));
            track.notes.push(Note(bars[bi] + 2.5, 1.0, c.voicing[vi], vel - 10));
          }
        }
      }
    }
  };
  Arranger.prototype.keys = function (track, start, end) {
    var mode = this.st.keys;
    if (mode === 'none') return;
    var rng = this.rng, bpb = this.bpb;
    var vel = 58 + Math.trunc(30 * this.f.arousal);
    var bars = this.bars(start, end);
    for (var bi = 0; bi < bars.length; bi++) {
      var bar = bars[bi];
      var c = this.chordAt(bar);
      var v = c.voicing.slice().sort(function (a, b) { return a - b; });
      if (!v.length) continue;
      var i, p, n, seq, hits, h, dur, mid = v[Math.floor(v.length / 2)], top = v[v.length - 1];
      if (mode === 'alberti') {
        var pat = bpb === 4 ? [v[0], top, mid, top, v[0], top, mid, top] : [v[0], mid, top, mid, top, mid];
        for (i = 0; i < pat.length; i++) track.notes.push(Note(bar + 0.5 * i, 0.5, pat[i], vel - (i % 2 === 0 ? 0 : 8)));
      } else if (mode === 'broken') {
        seq = v.length < 5 ? [v[0] - 12].concat(v, [v[0] + 12]) : [v[0] - 12].concat(v);
        n = bpb * 2;
        for (i = 0; i < n; i++) {
          p = (i < seq.length || bpb === 4) ? seq[i % seq.length] : seq[mod(n - 1 - i, seq.length)];
          track.notes.push(Note(bar + 0.5 * i, 0.55, p, vel - (i === 0 ? 0 : 6)));
        }
      } else if (mode === 'arpeggio_up') {
        var step = this.comp.bpm < 112 ? 0.25 : 0.5;
        seq = v.concat(v.map(function (x) { return x + 12; }));
        n = Math.trunc(bpb / step);
        for (i = 0; i < n; i++) track.notes.push(Note(bar + step * i, step * 0.9, seq[i % seq.length], vel - (i % 4 === 0 ? 0 : 10)));
      } else if (mode === 'arpeggio_updown') {
        seq = v.concat([v[0] + 12], v.slice(1).reverse());
        n = bpb * 2;
        for (i = 0; i < n; i++) track.notes.push(Note(bar + 0.5 * i, 0.7, seq[i % seq.length], vel - 8));
      } else if (mode === 'pluck16') {
        seq = [v[0], top, mid, top + 12];
        for (i = 0; i < bpb * 4; i++) track.notes.push(Note(bar + 0.25 * i, 0.22, seq[i % 4], vel - (i % 4 === 0 ? 0 : 12)));
      } else if (mode === 'comp') {
        if (this.st.name === 'jazz') hits = rng.choice([[0.0, 2.5], [1.5, 3.0], [0.5, 2.0, 3.5], [0.0, 1.5, 3.0]]);
        else hits = rng.choice([[0.5, 2.0, 3.5], [0.0, 1.5, 2.5], [0.0, 2.5]]);
        for (h = 0; h < hits.length; h++) {
          if (hits[h] < bpb) for (i = 0; i < v.length; i++) track.notes.push(Note(bar + hits[h], 1.0, v[i], vel - rng.randint(0, 10)));
        }
      } else if (mode === 'stab_offbeat') {
        if (this.st.name === 'house') { hits = [0.5, 1.5, 2.5, 3.5]; dur = 0.35; }
        else { hits = rng.random() < 0.7 ? [0.0, 2.5] : [0.0, 1.5, 2.5]; dur = 1.0; }
        for (h = 0; h < hits.length; h++) {
          if (hits[h] < bpb) for (i = 0; i < v.length; i++) track.notes.push(Note(bar + hits[h], dur, v[i], vel - rng.randint(0, 8)));
        }
      }
    }
  };
  Arranger.prototype.bass = function (track, start, end) {
    var mode = this.st.bass, bpb = this.bpb, rng = this.rng;
    var vel = 70 + Math.trunc(30 * this.f.arousal);
    var cs = this.comp.chords, i;
    if (mode === 'drone') {
      for (i = 0; i < cs.length; i++) if (start <= cs[i].start && cs[i].start < end) track.notes.push(Note(cs[i].start, cs[i].duration, cs[i].bass, vel));
      return;
    }
    var bars = this.bars(start, end);
    for (var bi = 0; bi < bars.length; bi++) {
      var bar = bars[bi];
      var c = this.chordAt(bar);
      var rootP = c.bass, fifth = rootP + 7;
      if (mode === 'root_whole') {
        track.notes.push(Note(bar, bpb, rootP, vel));
      } else if (mode === 'root_fifth') {
        if (bpb === 4) {
          track.notes.push(Note(bar, 2.0, rootP, vel));
          track.notes.push(Note(bar + 2, 2.0, rng.random() < 0.7 ? fifth : rootP, vel - 8));
        } else {
          track.notes.push(Note(bar, 1.5, rootP, vel));
          track.notes.push(Note(bar + 2, 1.0, fifth, vel - 10));
        }
      } else if (mode === 'octaves8') {
        for (i = 0; i < bpb * 2; i++) track.notes.push(Note(bar + 0.5 * i, 0.45, rootP + (i % 2 ? 12 : 0), vel - (i % 2 === 0 ? 0 : 10)));
      } else if (mode === 'offbeat8') {
        for (i = 0; i < bpb; i++) track.notes.push(Note(bar + i + 0.5, 0.4, rootP, vel));
      } else if (mode === 'rolling16') {
        for (i = 0; i < bpb * 4; i++) track.notes.push(Note(bar + 0.25 * i, 0.2, rootP + (i % 4 === 2 ? 12 : 0), vel - (i % 4 === 0 ? 0 : 8)));
      } else if (mode === 'walking') {
        var nxt = (bar + bpb >= c.start + c.duration) ? this.nextChord(c) : c;
        var minorish = c.quality.indexOf('min') === 0 || includes(['dim', 'm7b5', 'dim7'], c.quality);
        var third = rootP + (minorish ? 3 : 4);
        var target = nxt.bass;
        var approach = rng.random() < 0.5 ? target - 1 : target + 1;
        var seq = bpb === 4 ? [rootP, third, fifth, approach] : [rootP, third, fifth];
        for (i = 0; i < seq.length; i++) {
          var p = seq[i];
          p = (34 <= p && p <= 55) ? p : (p > 55 ? p - 12 : p + 12);
          track.notes.push(Note(bar + i, 0.95, p, vel - rng.randint(0, 8)));
        }
      } else if (mode === 'root_13') {
        track.notes.push(Note(bar, 1.5, rootP, vel));
        track.notes.push(Note(bar + 2.5, 1.0, rng.random() < 0.7 ? rootP : fifth, vel - 8));
        if (rng.random() < 0.3 && bpb === 4) track.notes.push(Note(bar + 3.5, 0.5, fifth, vel - 16));
      }
    }
  };
  Arranger.prototype.drums = function (track, start, end, finalHit) {
    var mode = this.st.drums;
    if (mode === 'none') return;
    var K = DRUM_NOTES.kick, S = DRUM_NOTES.snare, C = DRUM_NOTES.clap, H = DRUM_NOTES.hat, OH = DRUM_NOTES.ohat;
    var rng = this.rng, bpb = this.bpb;
    var vel = 90 + Math.trunc(25 * this.f.arousal);
    var bars = this.bars(start, end);
    for (var bi = 0; bi < bars.length; bi++) {
      var bar = bars[bi], lastBar = bi === bars.length - 1, i, q, k, s, kicks;
      if (mode === 'four_floor') {
        for (i = 0; i < bpb; i++) {
          track.notes.push(Note(bar + i, 0.25, K, vel));
          track.notes.push(Note(bar + i + 0.5, 0.15, (i === bpb - 1 && rng.random() < 0.5) ? OH : H, vel - 30));
          if (i === 1 || i === 3) track.notes.push(Note(bar + i, 0.25, C, vel - 10));
        }
      } else if (mode === 'trance') {
        for (i = 0; i < bpb; i++) {
          track.notes.push(Note(bar + i, 0.25, K, vel));
          track.notes.push(Note(bar + i + 0.5, 0.15, OH, vel - 25));
          if (i === 1 || i === 3) track.notes.push(Note(bar + i, 0.25, C, vel - 5));
          track.notes.push(Note(bar + i + 0.25, 0.1, H, vel - 45));
          track.notes.push(Note(bar + i + 0.75, 0.1, H, vel - 45));
        }
        if (lastBar && bpb === 4) {
          for (q = 0; q < 8; q++) track.notes.push(Note(bar + 2 + q * 0.25, 0.1, S, vel - 40 + q * 5));
        }
      } else if (mode === 'lofi') {
        kicks = rng.random() < 0.6 ? [0.0, 2.5] : [0.0, 1.75, 2.5];
        for (k = 0; k < kicks.length; k++) track.notes.push(Note(bar + kicks[k], 0.25, K, vel - 10));
        var snares = [1.0, 3.0];
        for (s = 0; s < 2; s++) if (snares[s] < bpb) track.notes.push(Note(bar + snares[s], 0.25, S, vel - 15));
        for (i = 0; i < bpb * 2; i++) {
          if (rng.random() < 0.9) track.notes.push(Note(bar + 0.5 * i, 0.12, H, vel - 45 - (i % 2 === 0 ? 0 : 12) + rng.randint(-5, 5)));
        }
      } else if (mode === 'backbeat') {
        kicks = rng.random() < 0.7 ? [0.0, 2.5] : [0.0, 2.0, 2.5];
        for (k = 0; k < kicks.length; k++) track.notes.push(Note(bar + kicks[k], 0.25, K, vel));
        var sn = [1.0, 3.0];
        for (s = 0; s < 2; s++) if (sn[s] < bpb) track.notes.push(Note(bar + sn[s], 0.3, S, vel));
        for (i = 0; i < bpb * 2; i++) track.notes.push(Note(bar + 0.5 * i, 0.12, H, vel - 35 - (i % 2 === 0 ? 0 : 10)));
      }
    }
    if (finalHit) {
      track.notes.push(Note(end, 0.5, K, vel));
      track.notes.push(Note(end, 0.5, DRUM_NOTES.ride, vel - 10));
    }
  };

  function Track(name, role, patch, midiChannel, level, pan) {
    return { name: name, role: role, patch: patch, notes: [], midi_program: 0, midi_channel: midiChannel || 0,
      level: level === undefined ? 0.8 : level, pan: pan || 0.0 };
  }

  function generate(text, opts) {
    opts = opts || {};
    var style = opts.style || 'auto';
    var form = opts.form || 'auto';
    var f = analyzeFull(text, opts.affect);
    if (!f.stanzas.length) throw new Error('the text contains no singable syllables');
    var seed = (opts.seed === undefined || opts.seed === null) ? f.seed : Math.trunc(Number(opts.seed));
    if (!Number.isFinite(seed)) throw new Error('seed must be a number');
    // The PRNG takes 32 bits; fold larger / negative seeds so every distinct integer still gets its own stream.
    var rng = new Random((seed ^ Math.floor(Math.abs(seed) / 4294967296)) >>> 0);
    var rngChoice = function (seq) { return rng.choice(seq); };
    var interp = interpret(f, rngChoice, form);

    var styleName = style === 'auto' ? chooseStyle(f) : style;
    if (!Object.prototype.hasOwnProperty.call(STYLES, styleName)) {
      throw new Error('unknown style ' + JSON.stringify(styleName) + '; choose from ' + Object.keys(STYLES).join(', '));
    }
    var st = STYLES[styleName];
    if (opts.drums !== undefined && opts.drums !== null && !opts.drums) st = Style(assign(copy(st), { drums: 'none' }));

    var colourMode = opts.mode || chooseMode(f, st, rng);
    if (!SCALES[colourMode]) throw new Error('unknown mode ' + JSON.stringify(colourMode));
    // A style whose library only knows one mode family (trance is minor music) keeps the whole
    // piece in that family instead of mixing parallel keys.
    var notesFamily = null;
    if (!opts.mode && !libraryFor(st.name, colourMode).length && libraryFor(st.name).length) {
      colourMode = (isMajorLike(colourMode) ? st.minor_modes : st.major_modes)[0];
      notesFamily = isMajorLike(colourMode) ? 'major' : 'minor';
    }
    var tonic;
    if (opts.key) {
      if (!Object.prototype.hasOwnProperty.call(NOTE_TO_PC, opts.key)) throw new Error('unknown key ' + JSON.stringify(opts.key));
      tonic = NOTE_TO_PC[opts.key];
    } else {
      tonic = chooseTonic(f, rng);
    }
    var preferFlats = includes(FLAT_KEYS, isMajorLike(colourMode) ? tonic : mod(tonic + 3, 12));
    var bpm = opts.tempo ? Number(opts.tempo)
      : pyRound(st.tempo_range[0] + (st.tempo_range[1] - st.tempo_range[0]) * f.arousal + rng.uniform(-3, 3));
    var ts = [4, 4];
    if (st.time_signatures.length > 1 && f.arousal < 0.45 && rng.random() < 0.35) ts = st.time_signatures[1].slice();
    var bpb = ts[0];

    var timeline = new Timeline(bpm, bpb, bpb === 4 ? st.swing : 0.5);
    var comp = {
      title: opts.title || chars(f.stanzas[0].lines[0].text).slice(0, 24).join(''),
      style: styleName, key: pcName(tonic, preferFlats), tonic: tonic, mode: colourMode,
      scale: scalePcs(tonic, colourMode).map(function (p) { return pcName(p, preferFlats); }),
      bpm: bpm, time_signature: ts.slice(), timeline: timeline, seed: seed, features: featuresToDict(f),
      form: interp.form, interpretation: interpretationToDict(interp),
      sections: [], chords: [], tracks: [], patches: {}, notes_on_theory: []
    };
    var notesOnTheory = interp.notes.slice();
    if (notesFamily) notesOnTheory.push('The ' + styleName + ' progression library is ' + notesFamily + '-only, so the piece stays in ' + colourMode + '.');

    // ---- Harmony per form letter
    var nSections = f.stanzas.length;
    var labelProg = {};        // label -> [name, mode, numerals, tonic]
    var chordSlots = [];       // [start, dur, Chord, numeral, name]
    var phrases = [];
    var sectionSpans = [];     // [start, end, reading]
    var cursor = 0.0;
    var usedNames = [];

    function emitCycle(start, mode_, tonic_, nums, name, nBars, alignEnd) {
      if (alignEnd === undefined) alignEnd = true;
      var bpc = st.bars_per_chord;
      var cycle = nums.length * bpc;
      var b = start;
      var remaining = Math.trunc(nBars);
      while (remaining > 0) {
        var seq;
        if (remaining >= cycle) seq = nums.slice();
        else {
          var k = Math.max(1, Math.floor(remaining / bpc));
          seq = alignEnd ? nums.slice(nums.length - k) : nums.slice(0, k);
        }
        for (var i = 0; i < seq.length; i++) {
          if (remaining <= 0) break;
          var barsHere = Math.min(bpc, remaining);
          chordSlots.push([b, barsHere * bpb, parseRoman(seq[i], tonic_, mode_), seq[i], name]);
          b += barsHere * bpb;
          remaining -= barsHere;
        }
      }
      return b;
    }

    var introStart = cursor;
    var motif = null;
    for (var si = 0; si < f.stanzas.length; si++) {
      var stanza = f.stanzas[si];
      var reading = interp.stanzas[si];
      var label = reading.label;
      var isLast = si === nSections - 1;
      var lastLine = stanza.lines[stanza.lines.length - 1];
      var finalTone = lastLine.syllables.length ? tonesOf(lastLine.syllables)[lastLine.syllables.length - 1] : 0;
      var openness = phraseOpenness(finalTone);
      var hasQ = stanza.lines.some(function (l) { return l.ends_with_question; });
      var cadence;
      if (hasQ || (openness === true && !isLast)) cadence = 'half';
      else if (isLast) {
        cadence = (!isMajorLike(colourMode) && f.valence > 0.25) ? 'picardy'
          : (includes(['none', 'half', 'deceptive'], st.harmony.cadence) ? 'authentic' : st.harmony.cadence);
      } else {
        cadence = st.harmony.cadence !== 'none' ? st.harmony.cadence : rng.choice(['none', 'deceptive', 'plagal']);
      }

      if (!Object.prototype.hasOwnProperty.call(labelProg, label)) {
        var secTonic = tonic, secColour = colourMode, modulated = false;
        if (label === 'B') {
          var pMod = (st.family === 'classical' || st.name === 'cinematic') ? 0.75 : 0.35;
          if (rng.random() < pMod) {
            var candTonic, candColour;
            if (isMajorLike(colourMode)) { candTonic = mod(tonic + 9, 12); candColour = st.minor_modes[0]; }
            else { candTonic = mod(tonic + 3, 12); candColour = st.major_modes[0]; }
            // Only modulate when the style can actually play in the relative key.
            if (libraryFor(st.name, candColour).length || !libraryFor(st.name).length) {
              secTonic = candTonic; secColour = candColour; modulated = true;
            }
          }
        }
        var pr = progressionFor(st, secColour, f, rng, cadence, usedNames, isLast);
        usedNames.push(pr[0]);
        labelProg[label] = [pr[0], pr[1], pr[2], secTonic];
        if (modulated) notesOnTheory.push('Section ' + label + ' modulates to the relative key ' + pcName(secTonic, preferFlats) + ' ' + pr[1] + '.');
      }
      var lp = labelProg[label];
      var name = lp[0], harmMode = lp[1], nums = lp[2];
      secTonic = lp[3];

      if (si === 0) {
        var introBars = st.family !== 'classical' ? nums.length * st.bars_per_chord : Math.min(2, nums.length);
        cursor = emitCycle(cursor, harmMode, secTonic, nums, name + ' (intro)', introBars, false);
        comp.sections.push({ name: 'intro', start: introStart, duration: cursor - introStart, kind: 'intro', mode: harmMode,
          progression: name, numerals: nums.slice(), text: '', label: label, key: pcName(secTonic, preferFlats),
          role: 'intro', dynamic: 0.5 });
      }

      // Lines -> bars.
      var secStart = cursor;
      var linePlans = [];
      for (var li = 0; li < stanza.lines.length; li++) {
        var devices = li < reading.lines.length ? reading.lines[li].devices : [];
        var stretch = includes(devices, 'still') ? 1.35 : 1.0;
        var regular = st.family === 'classical' ? 0.8 : (includes(['trance', 'house', 'pop'], st.name) ? 0.6 : 0.3);
        linePlans.push(planRhythm(stanza.lines[li], bpb, f.arousal, f.irregularity, rng, 1, stretch,
          tonesOf(stanza.lines[li].syllables), regular));
      }
      var totalBars = sum(linePlans.map(function (p) { return p.bars; }));
      var cycle = nums.length * st.bars_per_chord;
      var secBars;
      if (totalBars <= cycle) secBars = cycle <= 4 ? cycle : Math.max(4, Math.ceil(totalBars / 4) * 4);
      else if (totalBars <= cycle * 1.5) secBars = Math.ceil(totalBars / cycle) * cycle;
      else secBars = totalBars;
      var slotIndex = chordSlots.length;
      var secEnd = emitCycle(secStart, harmMode, secTonic, nums, name, secBars);

      // Phrase plans with endings from 起承转合 roles, tones or parity.
      var b = secStart;
      var nLines = linePlans.length;
      for (li = 0; li < linePlans.length; li++) {
        var plan = linePlans[li];
        var lr = reading.lines[li];
        var lastLineFlag = li === nLines - 1;
        var isFinal = isLast && lastLineFlag;
        var role = lr.role;
        var lineTones = tonesOf(plan.line.syllables);
        var lineOpen = lineTones.length ? phraseOpenness(lineTones[lineTones.length - 1]) : null;
        var ending;
        if (isFinal) ending = 'final';
        else if (role === '起') ending = 'open';
        else if (role === '承') ending = 'semi';
        else if (role === '转') ending = 'open';
        else if (role === '合') ending = 'closed';
        else if (lastLineFlag || includes(lr.devices, 'home')) ending = 'closed';
        else if (lineOpen !== null) ending = lineOpen ? 'open' : 'closed';
        else ending = li % 2 === 0 ? 'open' : 'closed';
        lr.open_ending = ending === 'open';
        var reg = 0;
        if (role === '转') reg += 3;
        if (reading.role === 'climax') reg += f.arousal > 0.5 ? 3 : 2;
        else if (includes(['resolution', 'salutation', 'farewell'], reading.role)) reg -= 2;
        phrases.push({ plan: plan, start: b, ending: ending, tonic: secTonic, mode: harmMode, devices: lr.devices,
          register_shift: reg, velocity_shift: pyRound((reading.dynamic - 0.6) * 30), motif: null, tones: lineTones });
        if (role === '转') {
          for (var k = slotIndex; k < chordSlots.length; k++) {
            var slot = chordSlots[k];
            if (slot[0] <= b && b < slot[0] + slot[1]) {
              var fam = isMajorLike(harmMode) ? 'major' : 'minor';
              var choice = rng.choice(TURN_CHORDS[fam].filter(function (c) { return c !== slot[3]; }));
              chordSlots[k] = [slot[0], slot[1], parseRoman(choice, secTonic, harmMode), choice + '*', slot[4]];
              notesOnTheory.push('Stanza ' + (si + 1) + ' line 3 (转) turns on a colour chord ' + choice + ' (' +
                chordSlots[k][2].symbol(preferFlats) + ').');
              break;
            }
          }
        }
        b += plan.bars * bpb;
      }
      cursor = secEnd;
      comp.sections.push({ name: 'stanza ' + (si + 1), start: secStart, duration: secEnd - secStart, kind: 'verse', mode: harmMode,
        progression: name, numerals: nums.slice(), text: stanza.lines.map(function (l) { return l.text; }).join('\n'),
        label: label, key: pcName(secTonic, preferFlats), role: reading.role, dynamic: reading.dynamic });
      sectionSpans.push([secStart, secEnd, reading]);
      notesOnTheory.push('Stanza ' + (si + 1) + ' [' + label + ', ' + reading.role + ', dyn ' + fixed(reading.dynamic, 2) + ']: ' + name + ' in ' +
        pcName(secTonic, preferFlats) + ' ' + harmMode + ' -> ' + nums.join(' ') + '; cadence ' + cadence +
        (openness !== null ? '; final tone ' + finalTone + ' (' + (openness ? 'open' : 'closed') + ')' : '') + '.');
    }

    // Outro: tonic chord held for two bars (home key).
    var outroStart = cursor;
    var lastMode = isMajorLike(colourMode) ? 'ionian' : 'aeolian';
    var tonicNumeral = isMajorLike(lastMode) ? 'I' : 'i';
    if (st.harmony.sevenths > 0.6) tonicNumeral += isMajorLike(lastMode) ? 'maj7' : '7';
    if (st.name === 'ambient') tonicNumeral = isMajorLike(lastMode) ? 'Isus2' : 'isus2';
    chordSlots.push([cursor, 2 * bpb, parseRoman(tonicNumeral, tonic, lastMode), tonicNumeral, 'outro']);
    cursor += 2 * bpb;
    comp.sections.push({ name: 'outro', start: outroStart, duration: cursor - outroStart, kind: 'outro', mode: lastMode,
      progression: 'outro', numerals: [tonicNumeral], text: '', label: 'A', key: comp.key, role: 'outro', dynamic: 0.4 });
    if (st.ritardando) { timeline.rit_start = outroStart - bpb; timeline.rit_end = cursor; }

    // ---- Chord events with voice leading
    var prevVoicing = null;
    for (var ci = 0; ci < chordSlots.length; ci++) {
      var cs = chordSlots[ci];
      var cStart = cs[0], cDur = cs[1], chord = cs[2], numeral = cs[3];
      var lastC = comp.chords.length ? comp.chords[comp.chords.length - 1] : null;
      if (lastC && st.name === 'ambient' && lastC.symbol === chord.symbol(preferFlats) && lastC.numeral === numeral &&
          Math.abs(lastC.start + lastC.duration - cStart) < 1e-6) {
        lastC.duration += cDur;
        continue;
      }
      var maxVoices = st.family === 'classical' ? 4 : 5;
      var voicing = voiceLead(prevVoicing, chord, 52, 76, maxVoices);
      prevVoicing = voicing;
      comp.chords.push({ start: cStart, duration: cDur, symbol: chord.symbol(preferFlats), numeral: numeral, root: chord.root,
        quality: chord.quality, pcs: chord.pcs(), voicing: voicing,
        bass: bassPitch(chord.bass !== null ? chord.bass : chord.root) });
    }

    // ---- Tracks
    var arr = new Arranger(comp, st, f, rng);
    var patches = designPatches(f, st, rng);
    comp.patches = { pad: patches.pad, keys: patches.keys, bass: patches.bass, lead: patches.lead };
    var totalEnd = cursor;
    var verseStart = comp.sections.length > 1 ? comp.sections[1].start : 0.0;

    var padTr = Track('Pad', 'pad', patches.pad.name, 0, patches.pad.level, 0.0);
    arr.pad(padTr);
    var keysTr = Track('Keys', 'keys', patches.keys.name, 1, patches.keys.level, -0.25);
    arr.keys(keysTr, st.family !== 'classical' ? introStart : verseStart, outroStart);
    var bassTr = Track('Bass', 'bass', patches.bass.name, 2, patches.bass.level, 0.0);
    arr.bass(bassTr, introStart, st.bass === 'drone' ? totalEnd : outroStart);
    if (st.bass !== 'drone') {
      var oc = arr.chordAt(outroStart);
      bassTr.notes.push(Note(outroStart, 2 * bpb, oc.bass, 80));
    }

    // Lead: sung text with tones, motifs and endings.
    var center = 67 + pyRound(3 * f.valence) + 12 * st.lead_octave_shift;
    if (includes(['folk', 'classical', 'romantic'], st.name)) center += 2;
    var tw = (opts.toneWeight === undefined || opts.toneWeight === null) ? 3.0 : Number(opts.toneWeight);
    var cfg = MelodyConfig({ center: center, span: 12, melody_scale: st.melody_scale, arousal: f.arousal,
      valence: f.valence, tension: f.tension, temperature: 0.4 + 0.5 * f.irregularity,
      tone_weight: tw, ornament_prob: st.family === 'classical' ? 0.65 : 0.35 });
    var leadTr = Track('Lead (text)', 'lead', patches.lead.name, 3, patches.lead.level, 0.1);
    var state = new MelodyState();
    var leadNotes = [];
    var phraseIdx = 0;
    var firstLabel = interp.stanzas.length ? interp.stanzas[0].label : 'A';
    for (si = 0; si < f.stanzas.length; si++) {
      reading = interp.stanzas[si];
      var secNotes = [];
      for (li = 0; li < f.stanzas[si].lines.length; li++) {
        var ph = phrases[phraseIdx++];
        if (li === 0 && motif && motif.length && reading.label === firstLabel && si > 0) ph.motif = motif;
        secNotes = secNotes.concat(singLine(ph, comp.chords, bpb, cfg, rng, state));
      }
      if (si === 0) {
        motif = headMotif(secNotes);
        if (motif.length) {
          notesOnTheory.push('Head motif of section A: intervals ' + motif.map(fmtSigned).join(', ') +
            ' (recalled at the start of every later A section).');
        }
      }
      leadNotes = leadNotes.concat(secNotes);
    }
    leadTr.notes = leadNotes;

    var drumTr = Track('Drums', 'drums', 'drums', 9, 0.8, 0.0);
    arr.drums(drumTr, introStart, outroStart, true);

    // ---- Emotional arc -> dynamics and texture
    function inSpan(n, a, b_) { return a - 1e-6 <= n.start && n.start < b_ - 1e-6; }
    var doubled = [];
    for (var spi = 0; spi < sectionSpans.length; spi++) {
      var a = sectionSpans[spi][0], b_ = sectionSpans[spi][1], rd = sectionSpans[spi][2];
      var gain = 0.7 + 0.35 * rd.dynamic;
      var trs = [padTr, keysTr, bassTr, drumTr];
      for (var ti = 0; ti < trs.length; ti++) {
        for (var ni = 0; ni < trs[ti].notes.length; ni++) {
          var nn = trs[ti].notes[ni];
          if (inSpan(nn, a, b_)) nn.velocity = Math.max(20, Math.min(127, Math.trunc(nn.velocity * gain)));
        }
      }
      if (rd.role === 'salutation' || rd.role === 'farewell' || (rd.dynamic < 0.45 && nSections >= 3)) {
        drumTr.notes = drumTr.notes.filter(function (n) { return !inSpan(n, a, b_); });
        keysTr.notes = keysTr.notes.filter(function (n) { return !inSpan(n, a, b_); });
      }
      if (rd.role === 'climax' && nSections > 1 && st.keys !== 'none') {
        // Brighten the climax by doubling only the top voice an octave up.
        var byStart = new Map();
        for (ni = 0; ni < keysTr.notes.length; ni++) {
          nn = keysTr.notes[ni];
          if (inSpan(nn, a, b_) && (!byStart.has(nn.start) || nn.pitch > byStart.get(nn.start).pitch)) byStart.set(nn.start, nn);
        }
        byStart.forEach(function (top) {
          doubled.push(Note(top.start, top.duration, top.pitch + 12, Math.max(20, top.velocity - 14)));
        });
      }
    }
    keysTr.notes = keysTr.notes.concat(doubled);

    if (st.humanize > 0) {
      var hts = [keysTr, bassTr, leadTr];
      for (ti = 0; ti < hts.length; ti++) {
        for (ni = 0; ni < hts[ti].notes.length; ni++) {
          nn = hts[ti].notes[ni];
          nn.start = Math.max(0.0, nn.start + rng.gauss(0, st.humanize));
        }
      }
    }

    comp.tracks = [padTr, keysTr, bassTr, leadTr, drumTr].filter(function (t) { return t.notes.length; });

    // ---- Explain
    var top = [['valence', f.valence], ['arousal', f.arousal], ['tension', f.tension], ['warmth', f.warmth],
      ['classical', f.classical], ['electronic', f.electronic]]
      .map(function (kv, i) { return [kv, i]; })
      .sort(function (x, y) { return (Math.abs(y[0][1] - 0.5) - Math.abs(x[0][1] - 0.5)) || (x[1] - y[1]); })
      .map(function (x) { return x[0]; });
    notesOnTheory.splice(0, 0, 'Style \'' + styleName + '\' chosen from affect: ' +
      top.slice(0, 4).map(function (kv) { return kv[0] + '=' + fixed(kv[1], 2); }).join(', ') + '.');
    notesOnTheory.splice(1, 0, 'Key ' + comp.key + ' ' + colourMode + ' (' + (isMajorLike(colourMode) ? 'major-like' : 'minor-like') + '), ' +
      Math.trunc(bpm) + ' bpm, ' + ts[0] + '/' + ts[1] + ', swing ' + fixed(st.swing, 2) + '; ' +
      (f.warmth >= 0.5 ? 'warm (flat) key' : 'bright (sharp) key') + ' from warmth ' + fixed(f.warmth, 2) + '.');
    notesOnTheory.push('Melody: one note per syllable (' + f.n_syllables + ' syllables), chord tones on strong beats, ' +
      st.melody_scale + ' scale, phrase endings open/semi/closed/final, leitmotif signatures per syllable' +
      ((f.language !== 'en' && tw > 0) ? ', 依字行腔 tone constraint weight ' + fmtG(tw) + ' with tone ornaments' : '') +
      '; range centred on MIDI ' + center + '.');
    notesOnTheory.push('Timbre from warmth ' + fixed(f.warmth, 2) + ' / arousal ' + fixed(f.arousal, 2) + ' / tension ' + fixed(f.tension, 2) + ': ' +
      ['pad', 'keys', 'bass', 'lead'].map(function (r) { return r + ' = ' + patches[r].name; }).join(', ') + ' (full recipes under \'patches\').');
    comp.notes_on_theory = notesOnTheory;
    return compositionToDict(comp);
  }

  // Composition.to_dict()
  function compositionToDict(comp) {
    var tl = comp.timeline;
    var ends = [];
    for (var ti = 0; ti < comp.tracks.length; ti++) for (var ni = 0; ni < comp.tracks[ti].notes.length; ni++) {
      var n = comp.tracks[ti].notes[ni]; ends.push(n.start + n.duration);
    }
    for (var ci = 0; ci < comp.chords.length; ci++) ends.push(comp.chords[ci].start + comp.chords[ci].duration);
    var totalBeats = ends.length ? maxOf(ends) : 0.0;
    var totalSeconds = tl.seconds(totalBeats);
    return {
      title: comp.title,
      style: comp.style,
      key: comp.key,
      tonic: comp.tonic,
      mode: comp.mode,
      scale: comp.scale.slice(),
      bpm: comp.bpm,
      time_signature: comp.time_signature.slice(),
      swing: tl.swing,
      timeline: tl.toDict(),
      seed: comp.seed,
      duration_beats: roundN(totalBeats, 3),
      duration_seconds: roundN(totalSeconds, 3),
      features: comp.features,
      form: comp.form,
      interpretation: comp.interpretation,
      notes_on_theory: comp.notes_on_theory.slice(),
      sections: comp.sections.map(function (s) {
        return { name: s.name, start: s.start, duration: s.duration, kind: s.kind, mode: s.mode, progression: s.progression,
          numerals: s.numerals.slice(), text: s.text, label: s.label, key: s.key, role: s.role, dynamic: s.dynamic };
      }),
      chords: comp.chords.map(function (c) {
        return { start: c.start, duration: c.duration, symbol: c.symbol, numeral: c.numeral, root: c.root, quality: c.quality,
          pcs: c.pcs.slice(), voicing: c.voicing.slice(), bass: c.bass,
          start_sec: roundN(tl.seconds(c.start), 4), end_sec: roundN(tl.seconds(c.start + c.duration), 4) };
      }),
      patches: deepCopy(comp.patches),
      tracks: comp.tracks.map(function (t) {
        return { name: t.name, role: t.role, patch: t.patch, midi_program: t.midi_program, midi_channel: t.midi_channel,
          level: t.level, pan: t.pan,
          notes: t.notes.map(function (n) {
            return { start: roundN(n.start, 4), duration: roundN(n.duration, 4), pitch: n.pitch, velocity: n.velocity,
              lyric: n.lyric, tone: n.tone, start_sec: roundN(tl.seconds(n.start), 4),
              end_sec: roundN(tl.seconds(n.start + n.duration), 4) };
          }) };
      })
    };
  }

  // =========================================================================
  // midi.py
  // =========================================================================
  var PPQ = 480;
  var GM_PROGRAMS = { pad: 89, keys: 4, bass: 38, lead: 80, drums: 0 };
  var GM_PROGRAMS_CLASSICAL = { pad: 48, keys: 0, bass: 42, lead: 73 };

  function vlq(n) {
    var out = [n & 0x7F];
    n = Math.floor(n / 128);
    while (n) { out.push(0x80 | (n & 0x7F)); n = Math.floor(n / 128); }
    out.reverse();
    return out;
  }
  function be32(n) { return [(n >>> 24) & 0xFF, (n >>> 16) & 0xFF, (n >>> 8) & 0xFF, n & 0xFF]; }
  function be16(n) { return [(n >>> 8) & 0xFF, n & 0xFF]; }
  function meta(kind, payload) {
    return [0xFF, kind].concat(vlq(payload.length), Array.prototype.slice.call(payload));
  }
  function trackChunk(events) {
    events = events.slice().sort(function (a, b) { return a[0] - b[0]; });
    var data = [], last = 0;
    for (var i = 0; i < events.length; i++) {
      data = data.concat(vlq(events[i][0] - last), events[i][1]);
      last = events[i][0];
    }
    data = data.concat(vlq(0), [0xFF, 0x2F, 0x00]);
    return [0x4D, 0x54, 0x72, 0x6B].concat(be32(data.length), data);
  }

  function compositionToMidi(comp) {
    var tl = timelineFromDict(comp.timeline);
    var bpm = comp.bpm, spb = 60.0 / bpm;
    function tick(beat) { return pyRound(tl.seconds(beat) / spb * PPQ); }
    var tracks = [];
    var tempo = Math.trunc(60000000 / bpm);
    var denomMap = { 2: 1, 4: 2, 8: 3 };
    var metaEvents = [
      [0, meta(0x03, utf8(comp.title))],
      [0, meta(0x51, be32(tempo).slice(1))],
      [0, meta(0x58, [comp.time_signature[0], denomMap[comp.time_signature[1]], 24, 8])],
      [0, meta(0x01, utf8('key ' + comp.key + ' ' + comp.mode + '; style ' + comp.style))]
    ];
    tracks.push(trackChunk(metaEvents));
    var classical = includes(['classical', 'romantic', 'folk', 'cinematic'], comp.style);
    for (var ti = 0; ti < comp.tracks.length; ti++) {
      var t = comp.tracks[ti];
      var ch = t.role === 'drums' ? 9 : t.midi_channel;
      var ev = [[0, meta(0x03, utf8(t.name))]];
      if (t.role !== 'drums') {
        var table = classical ? GM_PROGRAMS_CLASSICAL : GM_PROGRAMS;
        var prog = Object.prototype.hasOwnProperty.call(table, t.role) ? table[t.role] : t.midi_program;
        ev.push([0, [0xC0 | ch, prog]]);
      }
      for (var ni = 0; ni < t.notes.length; ni++) {
        var n = t.notes[ni];
        var on = tick(n.start), off = tick(n.start + n.duration);
        if (off <= on) off = on + 1;
        if (n.lyric) ev.push([on, meta(0x05, utf8(n.lyric))]);
        ev.push([on, [0x90 | ch, n.pitch & 0x7F, Math.max(1, Math.min(127, n.velocity))]]);
        ev.push([off, [0x80 | ch, n.pitch & 0x7F, 0]]);
      }
      tracks.push(trackChunk(ev));
    }
    var header = [0x4D, 0x54, 0x68, 0x64].concat(be32(6), be16(1), be16(tracks.length), be16(PPQ));
    var total = header.length;
    for (ti = 0; ti < tracks.length; ti++) total += tracks[ti].length;
    var out = new Uint8Array(total), pos = 0;
    out.set(header, 0); pos += header.length;
    for (ti = 0; ti < tracks.length; ti++) { out.set(tracks[ti], pos); pos += tracks[ti].length; }
    return out;
  }

  // =========================================================================
  // Public API
  // =========================================================================
  var PoetMelody = {
    version: VERSION,
    analyze: analyze,
    generate: generate,
    midi: compositionToMidi,
    textSeed: textSeed,
    tokenSeed: tokenSeed,
    STYLES: STYLES,
    styleNames: styleNames,
    chooseStyle: chooseStyle,
    LIBRARY: LIBRARY,
    libraryFor: libraryFor,
    allStyles: allStyles,
    pickProgression: pickProgression,
    generateFunctional: generateFunctional,
    HarmonyOptions: HarmonyOptions,
    parseRoman: parseRoman,
    chordFromSymbol: chordFromSymbol,
    progressionChords: progressionChords,
    toneOf: toneOf,
    tonesOf: tonesOf,
    toneDirection: toneDirection,
    phraseOpenness: phraseOpenness,
    describeTones: describeTones,
    TONE_NAMES: TONE_NAMES,
    TONE_LEVEL: TONE_LEVEL,
    SCALES: SCALES,
    CHORD_QUALITIES: CHORD_QUALITIES,
    NOTE_TO_PC: NOTE_TO_PC,
    pcName: pcName,
    midiName: midiName,
    scalePcs: scalePcs,
    scalePitches: scalePitches,
    isMajorLike: isMajorLike,
    voiceLead: voiceLead,
    closeVoicing: closeVoicing,
    spreadVoicing: spreadVoicing,
    transpose: transpose,
    nearestScalePitch: nearestScalePitch,
    intervalName: intervalName,
    interpret: interpret,
    detectPoemForm: detectPoemForm,
    planForm: planForm,
    caesuraPoints: caesuraPoints,
    planRhythm: planRhythm,
    PAINTING: PAINTING,
    englishSyllables: englishSyllables,
    splitSyllables: splitSyllables,
    detectLanguage: detectLanguage,
    parseStructure: parseStructure,
    LEXICONS: LEXICONS,
    designPatches: designPatches,
    Timeline: Timeline,
    Random: Random,
    DRUM_NOTES: DRUM_NOTES,
    GM_PROGRAMS: GM_PROGRAMS
  };

  root.PoetMelody = PoetMelody;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this));
