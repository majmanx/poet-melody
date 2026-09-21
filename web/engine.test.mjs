// Node test for web/engine.js (run: node web/engine.test.mjs).
//
// Loads tones.js + engine.js into a sandbox with a fake `window`, generates
// every example text in every style (auto form plus forced ABA / AABA),
// and checks determinism, JSON shape parity with the Python reference,
// chord tiling, lyric/syllable counts, pitch ranges and MIDI output.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..');

// ---------------------------------------------------------------- load engine
const sandbox = { console, TextEncoder, TextDecoder };
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
for (const f of ['tones.js', 'engine.js']) {
  vm.runInContext(fs.readFileSync(path.join(here, f), 'utf8'), sandbox, { filename: f });
}
const PM = sandbox.window.PoetMelody;
if (!PM) throw new Error('window.PoetMelody not defined');
if (typeof sandbox.window.POET_TONES !== 'string' || sandbox.window.POET_TONES.length !== 20992) {
  throw new Error('window.POET_TONES missing or wrong length');
}

// ---------------------------------------------------------------- helpers
let checks = 0, failures = 0;
const problems = [];
function check(cond, msg) {
  checks++;
  if (!cond) { failures++; problems.push(msg); if (problems.length <= 40) console.error('FAIL: ' + msg); }
}
const keysOf = (o) => Object.keys(o).sort();
const sameKeys = (a, b) => JSON.stringify(keysOf(a)) === JSON.stringify(keysOf(b));

// ---------------------------------------------------------------- reference JSON
// Prefer a fresh reference from the Python package (the committed examples/out
// files predate `form`, `interpretation` and note `tone`); fall back to the
// committed file plus the known additions when Python is unavailable.
function pythonReference() {
  try {
    const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'poet-melody-')), 'ref_moon');
    execFileSync('python3', ['-m', 'poet_melody', 'generate', 'examples/moon.txt', '--format', 'json', '--out', out, '--quiet'],
      { cwd: repo, stdio: ['ignore', 'ignore', 'ignore'], timeout: 60000 });
    return { ref: JSON.parse(fs.readFileSync(out + '.json', 'utf8')), fresh: true };
  } catch (e) {
    const ref = JSON.parse(fs.readFileSync(path.join(repo, 'examples/out/moon.json'), 'utf8'));
    if (!('form' in ref)) ref.form = '';
    if (!('interpretation' in ref)) ref.interpretation = null;
    for (const t of ref.tracks) for (const n of t.notes) if (!('tone' in n)) n.tone = 0;
    return { ref, fresh: false };
  }
}
const { ref, fresh } = pythonReference();
console.log('reference JSON: ' + (fresh ? 'fresh from python3 -m poet_melody' : 'examples/out/moon.json (+ known new keys)'));

// ---------------------------------------------------------------- example texts
const exampleDir = path.join(repo, 'examples');
const examples = fs.readdirSync(exampleDir).filter((f) => f.endsWith('.txt')).sort()
  .map((f) => ({ name: f.replace(/\.txt$/, ''), text: fs.readFileSync(path.join(exampleDir, f), 'utf8') }));
check(examples.length >= 4, 'found example texts');

// ---------------------------------------------------------------- per-composition checks
function syllablesOf(text) {
  const feats = PM.analyze(text);
  const out = [];
  for (const st of feats.stanzas) for (const l of st.lines) out.push(...l.syllables);
  return out;
}

function checkComposition(c, label, text) {
  // Shape parity with the Python reference.
  check(sameKeys(c, ref), `${label}: top-level keys differ: ${keysOf(c)} vs ${keysOf(ref)}`);
  check(sameKeys(c.timeline, ref.timeline), `${label}: timeline keys differ`);
  check(sameKeys(c.features, ref.features), `${label}: features keys differ`);
  check(sameKeys(c.features.keyword_hits, ref.features.keyword_hits), `${label}: keyword_hits keys differ`);
  check(sameKeys(c.chords[0], ref.chords[0]), `${label}: chord keys differ: ${keysOf(c.chords[0])}`);
  check(sameKeys(c.sections[0], ref.sections[0]), `${label}: section keys differ: ${keysOf(c.sections[0])}`);
  check(sameKeys(c.tracks[0], ref.tracks[0]), `${label}: track keys differ: ${keysOf(c.tracks[0])}`);
  check(sameKeys(c.tracks[0].notes[0], ref.tracks[0].notes[0]), `${label}: note keys differ: ${keysOf(c.tracks[0].notes[0])}`);
  check(sameKeys(c.patches, ref.patches), `${label}: patch roles differ`);
  check(sameKeys(c.patches.pad, ref.patches.pad), `${label}: patch keys differ: ${keysOf(c.patches.pad)}`);
  check(sameKeys(c.patches.pad.oscs[0], ref.patches.pad.oscs[0]), `${label}: osc keys differ`);
  check(sameKeys(c.patches.pad.amp_env, ref.patches.pad.amp_env), `${label}: env keys differ`);
  if (ref.interpretation) {
    check(sameKeys(c.interpretation, ref.interpretation), `${label}: interpretation keys differ: ${keysOf(c.interpretation)}`);
    check(sameKeys(c.interpretation.stanzas[0], ref.interpretation.stanzas[0]), `${label}: interpretation stanza keys differ`);
    check(sameKeys(c.interpretation.stanzas[0].lines[0], ref.interpretation.stanzas[0].lines[0]), `${label}: interpretation line keys differ`);
  }
  check(c.form === c.interpretation.form && c.form.length === c.features.n_stanzas, `${label}: form ${c.form} inconsistent`);

  // Chords tile the timeline without gaps or overlaps, from 0 to the outro end.
  const chords = c.chords;
  check(Math.abs(chords[0].start) < 1e-9, `${label}: first chord starts at ${chords[0].start}`);
  for (let i = 1; i < chords.length; i++) {
    const prevEnd = chords[i - 1].start + chords[i - 1].duration;
    check(Math.abs(prevEnd - chords[i].start) < 1e-6, `${label}: gap/overlap between chord ${i - 1} and ${i} (${prevEnd} vs ${chords[i].start})`);
    check(chords[i].duration > 0, `${label}: chord ${i} has non-positive duration`);
  }
  const lastChord = chords[chords.length - 1];
  const outro = c.sections[c.sections.length - 1];
  check(outro.kind === 'outro' && Math.abs(lastChord.start + lastChord.duration - (outro.start + outro.duration)) < 1e-6,
    `${label}: chords do not end with the outro`);
  for (let i = 1; i < c.sections.length; i++) {
    const s0 = c.sections[i - 1], s1 = c.sections[i];
    check(Math.abs(s0.start + s0.duration - s1.start) < 1e-6, `${label}: sections ${i - 1}/${i} do not tile`);
  }
  check(Math.abs(c.duration_beats - (outro.start + outro.duration)) < 0.5 + 1e-6 || c.duration_beats >= outro.start + outro.duration - 1e-6,
    `${label}: duration_beats ${c.duration_beats} vs outro end ${outro.start + outro.duration}`);
  check(c.duration_seconds > 0 && Number.isFinite(c.duration_seconds), `${label}: duration_seconds`);
  for (const ch of chords) {
    check(ch.end_sec > ch.start_sec, `${label}: chord seconds not increasing`);
    check(ch.voicing.length > 0 && ch.pcs.length > 0, `${label}: chord without voicing/pcs`);
    check(ch.voicing.every((p) => p >= 40 && p <= 88), `${label}: voicing out of 40..88: ${ch.voicing}`); // close_voicing may drop a whole octave below 52, as in Python
  }

  // Lead: exactly one lyric-carrying note per syllable, in text order; ornaments carry no lyric.
  const lead = c.tracks.find((t) => t.role === 'lead');
  check(!!lead, `${label}: no lead track`);
  if (lead) {
    const lyrics = lead.notes.filter((n) => n.lyric).map((n) => n.lyric);
    const syl = syllablesOf(text);
    check(lyrics.length === c.features.n_syllables, `${label}: ${lyrics.length} lyric notes vs ${c.features.n_syllables} syllables`);
    check(lyrics.join('\u0001') === syl.join('\u0001'), `${label}: lyric sequence differs from syllables`);
    for (const n of lead.notes) check(n.tone >= 0 && n.tone <= 5, `${label}: bad tone ${n.tone}`);
    if (c.features.language === 'zh') check(lead.notes.some((n) => n.tone > 0), `${label}: no Mandarin tones on a zh text`);
  }

  // All notes: pitches 24..108, velocities 1..127, positive durations, seconds consistent with beats.
  for (const t of c.tracks) {
    check(t.notes.length > 0, `${label}: empty track ${t.name}`);
    for (const n of t.notes) {
      check(n.pitch >= 24 && n.pitch <= 108, `${label}: pitch ${n.pitch} out of range on ${t.name}`);
      check(n.velocity >= 1 && n.velocity <= 127, `${label}: velocity ${n.velocity} on ${t.name}`);
      check(n.duration > 0, `${label}: non-positive duration on ${t.name}`);
      check(n.start >= 0 && n.end_sec >= n.start_sec, `${label}: bad timing on ${t.name}`);
    }
  }
  check(c.patches.lead.recipe.length > 20 && /LPF \d+Hz/.test(c.patches.lead.recipe), `${label}: lead recipe`);
  check(c.notes_on_theory.length >= 5 && c.notes_on_theory[0].startsWith('Style '), `${label}: notes_on_theory`);
  check(c.scale.length === PM.SCALES[c.mode].length, `${label}: scale names`);

  // MIDI.
  const m = PM.midi(c);
  check(ArrayBuffer.isView(m) && m.BYTES_PER_ELEMENT === 1, `${label}: midi() is not a Uint8Array`);
  check(String.fromCharCode(m[0], m[1], m[2], m[3]) === 'MThd', `${label}: MIDI does not start with MThd`);
  const nTracks = (m[10] << 8) | m[11];
  check(nTracks === c.tracks.length + 1, `${label}: MIDI track count ${nTracks} vs ${c.tracks.length + 1}`);
  let mtrk = 0;
  for (let i = 0; i + 3 < m.length; i++) if (m[i] === 0x4D && m[i + 1] === 0x54 && m[i + 2] === 0x72 && m[i + 3] === 0x6B) mtrk++;
  check(mtrk >= nTracks, `${label}: MTrk chunks ${mtrk} < ${nTracks}`);
}

// ---------------------------------------------------------------- main loop
const styles = PM.styleNames();
check(styles.length === 12, `expected 12 styles, got ${styles.length}`);
check(PM.LIBRARY.length === 83, `expected 83 library progressions, got ${PM.LIBRARY.length}`);
for (const p of PM.LIBRARY) {
  for (const n of p.numerals) {
    try { PM.parseRoman(n, 0, p.mode); } catch (e) { check(false, `library ${p.name}: ${e.message}`); }
  }
}
check(PM.parseRoman('V7/V', 0, 'ionian').symbol(false) === 'D7', 'secondary dominant parse');
check(PM.parseRoman('bVImaj7', 0, 'ionian').symbol(true) === 'Abmaj7', 'borrowed bVI parse');
check(PM.parseRoman('iiø7', 0, 'aeolian').quality === 'm7b5', 'half-diminished parse');
check(PM.toneOf('床') === 2 && PM.toneOf('月') === 4 && PM.toneOf('a') === 0, 'toneOf lookups');
check(typeof PM.version === 'string', 'version');
check(PM.textSeed('床前明月光') === PM.analyze('床前明月光').seed, 'textSeed matches analyze().seed');
check(PM.textSeed('  x  ') === PM.textSeed('x'), 'textSeed strips whitespace');

const forms = ['auto', 'ABA', 'AABA'];
let generated = 0;
const summary = [];
const t0 = Date.now();
for (const ex of examples) {
  const styleUsed = {};
  for (const style of ['auto', ...styles]) {
    for (const form of forms) {
      const label = `${ex.name}/${style}/${form}`;
      let c;
      try {
        c = PM.generate(ex.text, { style, form });
      } catch (e) {
        check(false, `${label}: generate threw ${e && e.stack || e}`);
        continue;
      }
      generated++;
      checkComposition(c, label, ex.text);
      if (style !== 'auto') check(c.style === style, `${label}: style ${c.style}`);
      if (form !== 'auto') check(c.form === form.slice(0, c.features.n_stanzas) || c.form.length === c.features.n_stanzas, `${label}: form ${c.form}`);
      // Determinism: a second run produces the identical JSON string.
      const again = PM.generate(ex.text, { style, form });
      check(JSON.stringify(c) === JSON.stringify(again), `${label}: not deterministic`);
      if (form === 'auto') styleUsed[style] = `${c.key} ${c.mode} ${c.bpm}bpm ${c.time_signature.join('/')} ${c.form}`;
    }
  }
  const auto = PM.generate(ex.text, {});
  summary.push(`${ex.name}: auto -> ${auto.style}, ${auto.key} ${auto.mode}, ${auto.bpm} bpm, form ${auto.form}, ` +
    `${auto.chords.length} chords, ${auto.tracks.map((t) => t.role + ':' + t.notes.length).join(' ')}, ${auto.duration_seconds}s`);
}

// Options: seed, key, mode, tempo, drums, title, affect, toneWeight.
{
  const text = examples.find((e) => e.name === 'letter_zh').text;
  const a = PM.generate(text, { seed: 1 });
  const b = PM.generate(text, { seed: 2 });
  check(JSON.stringify(a) !== JSON.stringify(b), 'different seeds give different pieces');
  check(a.seed === 1 && b.seed === 2, 'seed reported');
  const c = PM.generate(text, { seed: PM.textSeed(text) });
  check(JSON.stringify(c) === JSON.stringify(PM.generate(text, {})), 'seed = textSeed(text) reproduces the default piece');
  const d = PM.generate(text, { key: 'F#', mode: 'aeolian', tempo: 104, style: 'synthwave', drums: false, title: 'T' });
  check(d.key === 'F#' && d.mode === 'aeolian' && d.bpm === 104 && d.title === 'T', 'key/mode/tempo/title options');
  check(!d.tracks.some((t) => t.role === 'drums'), 'drums:false removes the drum track');
  checkComposition(d, 'letter_zh/options', text);
  const e = PM.generate(text, { key: 'Bb', mode: 'dorian', style: 'ambient' });
  check(e.key === 'Bb' && e.chords.every((ch) => ch.duration >= 8 || ch.numeral === 'isus2'), 'ambient merges repeated chords');
  const f = PM.generate(text, { affect: { valence: -0.9, arousal: 0.9 } });
  check(f.features.valence === -0.9 && f.features.arousal === 0.9, 'affect override');
  const g = PM.generate(text, { toneWeight: 0 });
  check(!g.notes_on_theory.some((s) => s.includes('依字行腔')), 'toneWeight 0 disables the tone note');
  checkComposition(g, 'letter_zh/toneWeight0', text);
  const h = PM.generate('举头望明月，低头思故乡。', { style: 'folk' });
  checkComposition(h, 'single-line/folk', '举头望明月，低头思故乡。');
  const en = PM.analyze('The winter has been long and quiet here.');
  check(en.language === 'en' && en.n_syllables === 9, `english syllables: ${en.n_syllables}`); // win-ter, quiet (one vowel group), here (silent e) as in Python
  const mixed = PM.analyze('I love 北京 very much!');
  check(mixed.language === 'mixed' || mixed.language === 'en', 'mixed language detection');
  const neg = PM.analyze("I am not happy, not warm, never home.");
  check(neg.keyword_hits.positive.includes('~happy') && neg.valence < 0, 'negation flips polarity');
  let threw = false;
  try { PM.generate('...', {}); } catch (err) { threw = true; }
  check(threw, 'empty text throws');
  threw = false;
  try { PM.generate('hello', { style: 'nope' }); } catch (err) { threw = true; }
  check(threw, 'unknown style throws');
}

const ms = Date.now() - t0;
console.log(summary.join('\n'));
console.log(`\ngenerated ${generated} compositions (${examples.length} texts x ${styles.length + 1} styles x ${forms.length} forms) in ${ms} ms`);
console.log(`${checks} checks, ${failures} failures`);
if (failures) {
  console.error(`\n${failures} FAILED` + (problems.length > 40 ? ` (first 40 shown)` : ''));
  process.exit(1);
}
console.log('OK');
