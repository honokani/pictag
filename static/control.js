// pictag 画面制御
// 表は 画像 × 段落（大kind）の入力欄。入力欄では辞書（使用中の語句）から fzf のように語句を引き出す
'use strict';

const $ = id => document.getElementById(id);

const state = {
    loaded: false,
    projectName: '',
    sections: [],
    rows: [],
    byIndex: new Map(),
    tokenLimit: 507,
    templates: {},        // 確定タグ {picture: [...], subject: [...]}
    fixedSections: [],    // 固定の段落（外せない・改名できない）
    autoKeys: [],         // 自動で作るキー（characters。入力欄には出さない）
    othersSection: '',    // 人物でない物の段落の名前（else。確定タグを持たない）
    candidateGroups: [],  // 語句の候補をまとめる名前の組（女性・男性。ほかの段落は種類ごと）
    hasHints: false,      // 画像フォルダに hint（画像と同じ名前の .txt）があるか
    foldedHints: new Set(),  // hint を畳んだ画像の名前（プロジェクトごとにブラウザに覚える）
    foldedSections: new Set(),  // 畳んだ段落の列（プロジェクトごとにブラウザに覚える）
    sideView: 'hint',     // hint の列に出すもの（hint / preview / hint_by_qwen。出せないものなら先頭。プロジェクトごとにブラウザに覚える）
    thumbZoomed: false,   // サムネイルを 1.5 倍に広げているか（プロジェクトごとにブラウザに覚える）
    qwen: false,          // qwen 版で起動したか（Qwen の列（🤖🔖🔄🎲）と hint_by_qwen を出す）
    qwenSamples: 0,       // Qwen に渡す見本の数（サーバーの qwen.py の SAMPLE_COUNT。表を読んだときに入れる）
    qwenPublic: 0,        // 見本が足りないときに補う、公開の例の数（サーバーの public_samples.SCENES）
    qwenBusy: new Map(),  // Qwen が書いている行の index → 押したボタン（near / mark / overwrite / random）
    thumbBase: null,      // 広げる前のサムネイルの大きさ（px。picture の欄の高さから測る）
    markChoices: {one: [], many: [], auto: []},  // マークの記号（番号の順。排他 A〜H、複数 ★●▲■◆♥♣♠、単語 ①〜⑯）。行のマークは番号で持つ
    autoMarks: [],                     // 単語のマークの設定（番号ごとに {section, key, phrase} か null。プロジェクトごと）
    filter: {one: new Set(), many: new Set(), auto: new Set()},  // 絞り込みで押している印のボタン（番号）
    without: {one: new Set(), many: new Set(), auto: new Set()},  // 押している ☓（番号か、左端の ☓ の 'none'）
    viewChoices: {camera: [], pov: []},  // view のボタン（🎥 の組、👀 の人物ごとの POV）
    phrases: [],          // 辞書の語句 [{section, key, phrase, count, shared}]
    words: [],            // キーなしの文の単語 [{section, word, count, shared}]
    groups: [],           // 「1つだけ」のグループ [{key, phrases}]（共用辞書）
    defaultSections: [],  // 新規プロジェクトの段落（共用辞書の画面で語句を足す段落の候補）
    view: 'images',       // 表示中の画面（images / dictionary）
    selected: new Set(),  // 行の index
    anchor: null,         // Shift 範囲選択の起点（最後にクリックした行）
    dirty: false,
    editor: null,         // {index, section, td, keys, fields}（fields: 欄の textarea。data-key がキー、「その他」は空）
    suggest: null,        // {el, section, ctx, items, active, moved}
    pending: new Set(),   // 送信中の入力（保存の前に待つ）
    verbChanges: [],      // ⇄ の窓に出した、動詞の形をそろえる案（/verb_forms の changes）
};

// ---- 通信 ----

async function getJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    return res.json();
}

async function postJson(url, payload) {
    const res = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload || {}),
    });
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    return res.json();
}

function track(promise) {
    state.pending.add(promise);
    promise.finally(() => state.pending.delete(promise));
    return promise;
}

const settled = () => Promise.allSettled([...state.pending]);

// 例外は画面に出す
const guarded = fn => (...args) => fn(...args).catch(e => setStatus(String(e.message || e), 'error'));

// ---- 表示の小物 ----

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
}

// 時:分:秒（2桁ずつ）
const clock = (d = new Date()) => [d.getHours(), d.getMinutes(), d.getSeconds()].map(n => String(n).padStart(2, '0')).join(':');

// メッセージは出た時刻と並べる（出たままでも、いつのメッセージか分かる）
function setStatus(message, kind = '') {
    $('statusTime').textContent = message ? clock() : '';
    $('status').textContent = message;
    $('status').className = kind;
}

function setDirty(dirty) {
    state.dirty = dirty;
    $('saveButton').textContent = dirty ? '保存 *' : '保存';
    $('saveButton').disabled = !state.loaded;
    $('renameProjectButton').disabled = !state.loaded;
}

function autosize(el) {
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight + 2}px`;
}

// ---- 入力の解釈（caption_format.py / words.py と同じ規則） ----

function splitPhrases(text) {
    return [...new Set(text.split(',').map(p => p.trim()).filter(Boolean))];
}

function parseLine(line) {
    const body = line.trim().replace(/^-+/, '').trim();
    const colon = body.indexOf(':');
    const key = colon >= 0 ? body.slice(0, colon).trim() : '';
    if (colon >= 0 && key && !key.includes(',')) return {key, phrases: splitPhrases(body.slice(colon + 1))};
    return {key: '', phrases: splitPhrases(body)};
}

const renderInputLine = (key, phrases) => (key ? `${key}: ${phrases.join(', ')}` : phrases.join(', '));

function addPhrase(text, key, phrase) {
    const trimmed = text.replace(/\s+$/, '');
    const lines = trimmed ? trimmed.split('\n') : [];
    const parsed = lines.map(parseLine);
    if (parsed.some(p => p.key === key && p.phrases.includes(phrase))) return text;
    const at = key ? parsed.findIndex(p => p.key === key) : -1;
    if (at < 0) return [...lines, renderInputLine(key, [phrase])].join('\n');
    return [...lines.slice(0, at), renderInputLine(key, [...parsed[at].phrases, phrase]), ...lines.slice(at + 1)].join('\n');
}

// 1行を整える: 行頭で重なった同じキー（"looks: looks :"）は1つにまとめる。続いたカンマ（",, " ", ," ",  ,"）は1つにして、
// カンマの後ろは空白1つ（"a,b" "a,  b" "a , b" → "a, b"）。語の間に続いた空白は1つ。値の頭と行末のカンマ・空白（候補の確定で付く ", "）は落とす。
// 「.」の前の空白は消し（"sits ." → "sits."。".5" のような数は残す）、続いた「.」は1つ（".." "..." → "."）
const tidyLine = line => line
    .replace(/^(\s*-*\s*)([^\s,:][^,:]*?)\s*:(?:\s*\2\s*:)+/, '$1$2:')
    .replace(/\s*,[\s,]*/g, ', ')
    .replace(/(?<=\S)\s{2,}(?=\S)/g, ' ')
    .replace(/^(\s*-*\s*[^,:]*:)?\s*,\s*/, (match, head) => (head ? `${head} ` : ''))
    .replace(/(?<=\S)\s+\.(?!\d)/g, '.')
    .replace(/\.{2,}/g, '.')
    .replace(/[\s,]+$/, '');

// action のキーの無い文を「.」で終える: 「, .」は「.」、行末のカンマも「.」（「.」の後ろのカンマは、整えるときに落とすだけ）
const endSentence = line => line
    .replace(/(?<=\S)\s*,[\s,]*\./g, '.')
    .replace(/(?<=[^\s,.])\s*,[\s,]*$/, '.');

// キーのある行では、語の後に続けた2つ以上のスペースは、カンマと同じ語句の区切り（"smile  big eyes" → "smile, big eyes"）
const spacesToCommas = text => text.replace(/(?<=[^\s,:]) {2,}(?=[^\s,])/g, ', ');

// 1行: キーのある行だけ、キーの後ろを直す（キーの無い文は、整えるときに空白1つにまとめる）
function spacesToCommasInLine(line) {
    if (!parseLine(line).key) return line;
    const colon = line.indexOf(':');
    return line.slice(0, colon + 1) + spacesToCommas(line.slice(colon + 1));
}

// 入力欄の値（{key, value}）: キーの欄は全部、「その他」の欄と1つだけの欄はキーのある行だけ
const spacesToCommasInField = f => ({...f, value: f.key ? spacesToCommas(f.value) : f.value.split('\n').map(spacesToCommasInLine).join('\n')});

// 「その他」の欄で、値の無いキーの行（mirror:）の次からのキーの無い行を、空行か次のキーの行まで、そのキーの行に空白でつなぐ
// （else の物ごとの文: mirror: face reflects on mirror. ball reflects on mirror.）
function foldBareKeys(lines) {
    const out = [];
    let open = false;  // 直前が、値の無いキーの行か、その続き
    for (const line of lines) {
        const {key, phrases} = parseLine(line);
        if (open && !key && phrases.length) {
            out[out.length - 1] = `${out[out.length - 1].trimEnd()} ${line.trim().replace(/^-+/, '').trim()}`;
            continue;
        }
        open = Boolean(key) && !phrases.length;
        out.push(line);
    }
    return out;
}

// 保存する形に整える: 各行を整え、空行と値の無いキーの行を落とす
function tidyInput(text, section) {
    const sentence = line => section === 'action' && !parseLine(line).key;
    return text.split('\n')
        .map(line => tidyLine(sentence(line) ? endSentence(line) : line))
        .filter(line => parseLine(line).phrases.length > 0)
        .join('\n');
}

const baseName = section => section.replace(/ [A-Z]$/, '');  // guy A → guy（subjects.py の base_name と同じ）

// 段落の確定タグ（キーの並び）。固定の段落は自分の名前で、人物などの段落は subject を使う。else（人物でない物の段落）には無い
function templateKeys(section) {
    if (state.templates[section]) return state.templates[section];
    const none = state.fixedSections.includes(section) || baseName(section) === state.othersSection;
    return none ? [] : (state.templates.subject || []);
}

// 入力欄に出すキー（自動で作るキーは除く）
const editKeys = section => templateKeys(section).filter(key => !state.autoKeys.includes(key));

// 行のうち、key の行の語句
function phrasesOfKey(text, key) {
    return (text || '').split('\n').map(parseLine).filter(p => p.key === key).flatMap(p => p.phrases);
}

// 確定タグのキーを並びどおりに置いた行（値の無いキーは「key: 」）。ほかの行はその後ろ
function mergeTemplate(text, keys) {
    const lines = text ? text.split('\n') : [];
    const parsed = lines.map(parseLine);
    const used = new Set();
    const keyLines = keys.map(key => {
        const at = parsed.findIndex((p, i) => p.key === key && !used.has(i));
        if (at < 0) return `${key}: `;
        used.add(at);
        return lines[at];
    });
    return [...keyLines, ...lines.filter((line, i) => !used.has(i) && line.trim())];
}

// 入力欄に分ける: 確定タグのキーごとの欄にそのキーの値（同じキーの行はまとめる）。ほかの行（キーの無い文・確定タグに無いキー）は「その他」の欄
function splitText(text, keys) {
    const lines = (text || '').split('\n').filter(line => line.trim());
    const values = Object.fromEntries(keys.map(key => [key, [...new Set(phrasesOfKey(text, key))].join(', ')]));
    return {values, rest: lines.filter(line => !keys.includes(parseLine(line).key))};
}

// 入力欄から入力に戻す（fields: [{key, value}]。「その他」の欄はキーが空）。確定タグのキーは並びどおりに1行ずつで、キーの欄の改行も語句の区切り。
// 「その他」の欄に書いた同じキーの行もまとめる（同じ語句は1つ）。ほかの行はその後ろ
function composeEditor(fields, keys) {
    const rest = foldBareKeys(fields.filter(f => !f.key).flatMap(f => f.value.split('\n')));
    const keyLines = keys.map(key => `${key}: ${splitPhrases([
        ...fields.filter(f => f.key === key).map(f => f.value.replace(/\n/g, ',')),
        ...rest.filter(line => parseLine(line).key === key).map(line => line.slice(line.indexOf(':') + 1)),
    ].join(',')).join(', ')}`);
    return [...keyLines, ...rest.filter(line => !keys.includes(parseLine(line).key))].join('\n');
}

// キーの欄の後ろに語句を足す（もう入っていれば足さない）
function appendPhrase(value, phrase) {
    if (splitPhrases(value.replace(/\n/g, ',')).includes(phrase)) return value;
    const kept = value.replace(/[\s,]+$/, '');
    return kept ? `${kept}, ${phrase}` : phrase;
}

// 入力の キー → 語句（キーのある行だけ）
function phrasesByKey(text) {
    const byKey = {};
    for (const {key, phrases} of (text || '').split('\n').map(parseLine)) {
        if (key) byKey[key] = [...(byKey[key] || []), ...phrases];
    }
    return byKey;
}

// ---- 「1つだけ」のグループ（groups.py と同じ規則。1枚の画像の1段落で、同じキーの語句のうち1つだけ） ----

const groupOf = (key, phrase) => state.groups.find(g => g.key === key && g.phrases.includes(phrase));

// 同じグループの別の語句が、もう入っているか（入っていれば候補に出さない）
function blockedIn(byKey, key, phrase) {
    const group = groupOf(key, phrase);
    return Boolean(group) && group.phrases.some(p => p !== phrase && (byKey[key] || []).includes(p));
}

// 語句のうち2つ以上が入っているグループ（ぶつかっている）
const conflictOf = (key, phrases) => state.groups.find(g => g.key === key && g.phrases.filter(p => phrases.includes(p)).length >= 2);

// ---- あいまい検索（打った文字が順に含まれる語句を拾う。連続・語頭の一致を高く） ----

function fuzzyScore(query, text) {
    const q = query.toLowerCase().replace(/\s+/g, '');
    const t = text.toLowerCase();
    if (!q) return 0;
    let score = t.startsWith(query.toLowerCase()) ? 10 : 0;
    let from = 0;
    let prev = -2;
    for (const ch of q) {
        const at = t.indexOf(ch, from);
        if (at < 0) return null;
        const wordStart = at === 0 || /[\s\-_/:,]/.test(t[at - 1]);
        score += 1 + (at === prev + 1 ? 4 : 0) + (wordStart ? 3 : 0);
        prev = at;
        from = at + 1;
    }
    return score - t.length * 0.02;
}

// 語の後ろ（カーソルの前）に続くスペースの数
const spacesAfterWord = before => (before.match(/\S( *)$/) || ['', ''])[1].length;

// キーなしの文で、語の後にスペースを2つ続けた（打たなくても単語の候補を出す合図。3つ目でしまう）
const calledBySpaces = ctx => !ctx.query && ctx.spaces === 2;

// キーなしの文の途中で、文の候補を探す文字: 行頭（at）から打った所までの text（空白とカンマは区切りの空白1つに。girl, i → girl i）
const sentenceQuery = (text, at) => ({sentence: text.replace(/[\s,]+/g, ' '), sentenceStart: at});

// キーのある行で打っている語句: raw はカンマ（キーのコロン・欄の改行）の後ろからカーソルまで、at は raw の頭の位置
// 語の後に2つ以上続けたスペースはカンマと同じで、その後ろが打っている語句（何も打っていなければ、カンマの後ろと同じ候補を出す。
// 3つ目でもしまわない）。選んだ語句は、そのスペースから置き換える
function phraseQuery(raw, at) {
    const spaced = raw.match(/^(.*[^\s,:])( {2,})(.*)$/);
    if (spaced) return {query: spaced[3], queryStart: at + spaced[1].length};
    const query = raw.trimStart();
    return {query, queryStart: at + raw.length - query.length};
}

// 選んだ単語の後ろに付ける区切り: 行末なら ", "（欄を離れると行末のカンマは消える）。後ろに語が続けば空白、空白かカンマが続けば付けない
const wordSeparator = after => (!after.trim() ? ', ' : /^[\s,]/.test(after) ? '' : ' ');
// キーのある行の語句の前後: カンマ（キーのコロン）のすぐ後ろに入れるときは前に空白、語のすぐ後ろ（スペース2つで出した候補）なら ", "。
// 後ろに語が続けばカンマで区切り、行末は ", "
const phraseBefore = (value, at) => (/[,:]/.test(value[at - 1] || '') ? ' ' : /\S/.test(value[at - 1] || '') ? ', ' : '');
const phraseAfter = after => (!after.trim() ? ', ' : /^\s*,/.test(after) ? '' : /^\s/.test(after) ? ',' : ', ');

// 入力欄のカーソル位置の文脈
// mode: phrase = キーのある行の語句 / word = キーなしの文の途中の単語（spaces は語の後ろに続くスペースの数。sentence は文の候補を探す文字）/
// start = 行頭（キー・語句・文・単語）
// 範囲を選んでいるときは、選んだ文字を候補で置き換えるので、無いものとして見る（end は置き換える範囲の終わり）
function contextOf(el) {
    const caret = el.selectionStart;
    const end = el.selectionEnd;
    const value = el.value.slice(0, caret) + el.value.slice(end);
    const lineStart = value.lastIndexOf('\n', caret - 1) + 1;
    const lineEndAt = value.indexOf('\n', caret);
    const lineEnd = lineEndAt < 0 ? value.length : lineEndAt;
    const before = value.slice(lineStart, caret);
    const after = value.slice(caret, lineEnd);
    const base = {end, after, current: parseLine(spacesToCommasInLine(value.slice(lineStart, lineEnd))).phrases,
        cellPhrases: phrasesByKey(value)};
    const colon = before.indexOf(':');
    const keyPart = colon >= 0 ? before.slice(0, colon).replace(/^\s*-*\s*/, '').trim() : '';
    if (colon >= 0 && keyPart !== '' && !keyPart.includes(',')) {
        const segment = Math.max(before.lastIndexOf(','), colon) + 1;
        return {...base, mode: 'phrase', key: keyPart, ...phraseQuery(before.slice(segment), lineStart + segment)};
    }
    const prefix = before.match(/^\s*-*\s*/)[0].length;
    const rest = before.slice(prefix);
    const lastBreak = Math.max(rest.lastIndexOf(' '), rest.lastIndexOf(','), rest.lastIndexOf('\t'));
    if (lastBreak >= 0) {
        return {...base, mode: 'word', key: null, query: rest.slice(lastBreak + 1), queryStart: lineStart + prefix + lastBreak + 1,
            spaces: spacesAfterWord(rest), ...sentenceQuery(rest, lineStart + prefix)};
    }
    return {...base, mode: 'start', key: null, query: rest, queryStart: lineStart + prefix};
}

// 開いた入力欄の文脈: キーの欄はいつもそのキーの語句（カンマと改行で区切る）。「その他」の欄と1つだけの欄は contextOf と同じ
// その欄にもう入っている語句（cellPhrases）は全部の欄から見る。打っている欄の選んだ範囲は、無いものとして見る
function editorContext(el) {
    const caret = el.selectionStart;
    const end = el.selectionEnd;
    const value = el.value.slice(0, caret) + el.value.slice(end);
    const fields = state.editor.fields.map(f => spacesToCommasInField({key: f.dataset.key, value: f === el ? value : f.value}));
    const cellPhrases = phrasesByKey(composeEditor(fields, state.editor.keys));
    if (!el.dataset.key) return {...contextOf(el), cellPhrases};
    const before = value.slice(0, caret);
    const lineEndAt = value.indexOf('\n', caret);
    const segment = Math.max(before.lastIndexOf(','), before.lastIndexOf('\n')) + 1;
    return {end, after: value.slice(caret, lineEndAt < 0 ? value.length : lineEndAt), current: splitPhrases(spacesToCommas(value).replace(/\n/g, ',')),
        cellPhrases, mode: 'phrase', key: el.dataset.key, ...phraseQuery(before.slice(segment), segment)};
}

function keepBest(items) {
    const best = new Map();
    for (const item of items) {
        const prev = best.get(item.label);
        if (!prev || prev.bonus < item.bonus) best.set(item.label, item);
    }
    return [...best.values()];
}

const wordBonus = (w, section) => (w.section === section ? 3 : 0) + Math.log1p(w.count);

// 語句の候補の種類: 女性（girl・woman）・男性（guy・man・boy）はそれぞれ組でまとめ、ほかは A, B を除いた名前
function kindOf(section) {
    const base = baseName(section);
    return (state.candidateGroups.find(group => group.includes(base)) || [base])[0];
}

const sameKind = (a, b) => kindOf(a) === kindOf(b);

// キーのある行: 同じ種類の段落でそのキーに使われた語句（打っていなくても使用回数の多い順に出す）。同じグループの語句が入っていれば出さない
function phraseCandidates(section, ctx) {
    return keepBest(state.phrases
        .filter(p => p.key === ctx.key && sameKind(p.section, section) && !ctx.current.includes(p.phrase)
            && !blockedIn(ctx.cellPhrases, p.key, p.phrase))
        .map(p => ({kind: 'phrase', label: p.phrase, match: p.phrase, phrase: p.phrase, count: p.count, bonus: wordBonus(p, section)})));
}

// キーなしの文の単語（1文字以上打ったとき。語の後にスペースを2つ続けたときは、打たなくても使用回数の多い順に出す）
function wordCandidates(section, ctx) {
    if (!(ctx.query || calledBySpaces(ctx))) return [];
    return keepBest(state.words.map(w => ({kind: 'word', label: w.word, match: w.word, word: w.word, count: w.count, bonus: wordBonus(w, section)})));
}

// キーなしの文の途中の文: 行頭から打った所まで（sentence）であいまい検索する（単語を1文字以上打ったとき。後ろに語が続く所では出さない）。
// 選ぶと、行の頭から打った所までを置き換える
function sentenceCandidates(section, ctx) {
    if (!ctx.query || ctx.after.trim()) return [];
    return keepBest(state.phrases.filter(p => !p.key).map(p => ({kind: 'line', label: p.phrase, match: p.phrase, phrase: p.phrase,
        count: p.count, bonus: wordBonus(p, section), query: ctx.sentence, from: ctx.sentenceStart})));
}

// キーなしの文の途中: 単語と、行頭から打った所までに合う文（合う度合いの順に混ぜる）
function inSentenceCandidates(section, ctx) {
    return [...wordCandidates(section, ctx), ...sentenceCandidates(section, ctx)];
}

// 行頭: キー、キー付きの語句（同じ種類の段落のもの。その欄の同じキーにもう入っているものは出さない）、キーなしの文、単語（1文字以上打ったときだけ）
function lineStartCandidates(section, ctx) {
    if (!ctx.query) return [];
    return keepBest([
        ...state.phrases.flatMap(p => {
            const bonus = wordBonus(p, section);
            if (!p.key) return [{kind: 'line', label: p.phrase, match: p.phrase, phrase: p.phrase, count: p.count, bonus}];
            const inCell = (ctx.cellPhrases[p.key] || []).includes(p.phrase);
            const keyed = inCell || !sameKind(p.section, section) || blockedIn(ctx.cellPhrases, p.key, p.phrase) ? []
                : [{kind: 'keyed', label: `${p.key}: ${p.phrase}`, match: p.phrase, key: p.key, phrase: p.phrase, count: p.count, bonus}];
            return [{kind: 'key', label: `${p.key}:`, match: p.key, key: p.key, count: 0, bonus: bonus + 1}, ...keyed];
        }),
        ...wordCandidates(section, ctx),
    ]);
}

// 一括入力でキーなしを選んだとき: 文と単語（1文字以上打ったときだけ）
function keylessCandidates(section, ctx) {
    if (!ctx.query) return [];
    return keepBest([
        ...state.phrases.filter(p => !p.key)
            .map(p => ({kind: 'line', label: p.phrase, match: p.phrase, phrase: p.phrase, count: p.count, bonus: wordBonus(p, section)})),
        ...wordCandidates(section, ctx),
    ]);
}

// キーを移す語句の欄: その段落（A, B も。section は A, B を除いた名前）のそのキーで使っている語句
// キーなし（単語のマークの文）は、文末の「.」を外して出す
function movingCandidates(section, ctx) {
    return keepBest(state.phrases
        .filter(p => p.key === ctx.key && baseName(p.section) === section && !ctx.current.includes(p.phrase))
        .map(p => {
            const phrase = ctx.key ? p.phrase : withoutPeriod(p.phrase);
            return {kind: 'phrase', label: phrase, match: phrase, phrase, count: p.count, bonus: Math.log1p(p.count)};
        }));
}

const CANDIDATE_SOURCES = {phrase: phraseCandidates, word: inSentenceCandidates, start: lineStartCandidates, keyless: keylessCandidates,
    moving: movingCandidates};

// 打った文字で探す（文の途中の文の候補は、行頭から打った所までで）
function candidates(section, ctx) {
    return CANDIDATE_SOURCES[ctx.mode](section, ctx)
        .map(item => ({...item, score: fuzzyScore(item.query ?? ctx.query, item.match)}))
        .filter(item => item.score !== null)
        .sort((a, b) => (b.score + b.bonus) - (a.score + a.bonus))
        .slice(0, 20);
}

function showSuggestions(el, section, contextFor = contextOf) {
    const ctx = contextFor(el);
    const items = candidates(section, ctx);
    if (!items.length) {
        hideSuggestions();
        return;
    }
    state.suggest = {el, section, ctx, items, active: 0, moved: false};
    const list = $('suggestions');
    list.innerHTML = items.map((item, i) =>
        `<li role="option" data-i="${i}"${i === 0 ? ' class="active"' : ''}>${escapeHtml(item.label)}` +
        `${item.count ? `<span class="count">${item.count}</span>` : ''}</li>`).join('');
    list.hidden = false;
    const rect = el.getBoundingClientRect();
    const below = rect.bottom + list.offsetHeight <= window.innerHeight;
    list.style.left = `${rect.left}px`;
    list.style.top = `${below ? rect.bottom : Math.max(0, rect.top - list.offsetHeight)}px`;
}

function hideSuggestions() {
    state.suggest = null;
    $('suggestions').hidden = true;
}

function moveActive(step) {
    const s = state.suggest;
    s.active = (s.active + step + s.items.length) % s.items.length;
    s.moved = true;
    [...$('suggestions').children].forEach((li, i) => li.classList.toggle('active', i === s.active));
    $('suggestions').children[s.active].scrollIntoView({block: 'nearest'});
}

// 「その他」の欄で選んだ確定タグのキー: 打ちかけの文字を消し、キー付きの語句はそのキーの欄の後ろに足す。キーだけなら、その欄へ移る
function acceptIntoField(el, ctx, field, item) {
    const without = el.value.slice(0, ctx.queryStart) + el.value.slice(ctx.end);
    el.value = without.split('\n').filter(line => line.trim()).join('\n');
    el.setSelectionRange(el.value.length, el.value.length);
    if (item.kind === 'keyed') {
        field.value = appendPhrase(field.value, item.phrase);
        autosize(field);
        paintWhitespace(field);
        el.dispatchEvent(new Event('input'));
        return;
    }
    autosize(el);
    paintWhitespace(el);
    const kept = field.value.replace(/[\s,]+$/, '');
    field.value = kept ? `${kept}, ` : '';
    field.focus();
    field.setSelectionRange(field.value.length, field.value.length);
    field.dispatchEvent(new Event('input'));  // そのキーの語句の候補を出す
}

function accept(item) {
    const {el, ctx} = state.suggest;
    const field = item.key && el.dataset.key === '' ? state.editor.fields.find(f => f.dataset.key === item.key) : null;
    if (field && (item.kind === 'keyed' || item.kind === 'key')) {
        acceptIntoField(el, ctx, field, item);
        return;
    }
    if (item.kind === 'keyed' && el.tagName === 'TEXTAREA') {
        // 打ちかけの文字を消し、同じキーの行へ足す（無ければ行を足す）
        const without = el.value.slice(0, ctx.queryStart) + el.value.slice(ctx.end);
        el.value = addPhrase(without.split('\n').filter(line => line.trim()).join('\n'), item.key, item.phrase);
        el.setSelectionRange(el.value.length, el.value.length);
    } else if (item.kind === 'keyed') {
        el.value = `${item.key}: ${item.phrase}`;  // 一括入力は1行
    } else {
        const text = {
            key: () => `${item.key}: `,
            phrase: () => phraseBefore(el.value, ctx.queryStart) + item.phrase + phraseAfter(ctx.after),
            word: () => item.word + wordSeparator(ctx.after),
            line: () => item.phrase,
        }[item.kind]();
        // 候補を出すために2つ続けたスペースは、1つにまとめる。範囲を選んでいれば、選んだ文字も置き換える（文の途中で選んだ文は、行の頭から）
        el.setRangeText(text, item.from ?? (calledBySpaces(ctx) ? ctx.queryStart - 1 : ctx.queryStart), ctx.end, 'end');
    }
    el.dispatchEvent(new Event('input'));
}

// 打ちかけがある（「.」で終えた所は、文を書き終えたと見て打ちかけにしない）
const typing = ctx => Boolean(ctx.query) && !ctx.query.endsWith('.');

// 候補が出ているときのキー操作。Enter は打ちかけがあるか ↑↓ で選んだときだけ確定（改行を邪魔しない。「.」の後の Enter は改行）
function handleSuggestKey(event) {
    const s = state.suggest;
    if (!s || s.el !== event.target) return false;
    if (event.key === 'ArrowDown' && s.active === s.items.length - 1) {
        // 一番下で ↓: 候補を閉じ、ふつうの ↓ としてカーソルを下の行へ動かす
        hideSuggestions();
        return false;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        moveActive(event.key === 'ArrowDown' ? 1 : -1);
    } else if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey && (typing(s.ctx) || s.moved))) {
        accept(s.items[s.active]);
    } else if (event.key === 'Escape') {
        hideSuggestions();
    } else {
        return false;
    }
    event.preventDefault();
    return true;
}

function refreshWords() {
    clearTimeout(refreshWords.timer);
    refreshWords.timer = setTimeout(() => {
        getJson('/get_dictionary')
            .then(applyDictionary)
            .catch(e => console.warn('辞書を読めません', e));
    }, 100);
}

// 辞書を受け取る（/get_dictionary と、共用辞書を書き換えた API の応答）。グループが変われば ⚠ を付け直す
function applyDictionary(body) {
    const groupsChanged = JSON.stringify(body.groups) !== JSON.stringify(state.groups);
    state.phrases = body.phrases;
    state.words = body.words;
    state.groups = body.groups;
    state.defaultSections = body.default_sections;
    if (!state.loaded) {
        // プロジェクトを開く前でも、共用辞書の画面で確定タグと固定の段落を使う
        state.templates = body.templates;
        state.fixedSections = body.fixed_sections;
        state.autoKeys = body.auto_keys;
    }
    fillBulkKeys();
    fillMoveKeys();
    if (groupsChanged && state.loaded) rerenderRows();
    document.dispatchEvent(new CustomEvent('pictag:dictionary'));
}

// ---- 表 ----

// 段落の見出し: 名前（固定でない段落はダブルクリックで改名、× で外す）と、右端の ◀（列を細く畳む）。畳んだ列は ▶ だけ。
// action には ⇄（文の動詞の形をそろえる）
function sectionHeadHtml(s) {
    const name = escapeHtml(s);
    if (state.foldedSections.has(s)) {
        return `<th class="folded" data-section="${name}">` +
            `<button type="button" class="fold-section" title="${name} を開く" aria-label="${name} を開く">▶</button></th>`;
    }
    const label = state.fixedSections.includes(s)
        ? `<span class="section-name fixed">${name}</span>`
        : `<span class="section-name" title="ダブルクリックで改名">${name}</span>` +
          `<button type="button" class="remove-section" title="この段落を表から外す" aria-label="${name} を外す">×</button>`;
    const verbs = s === 'action'
        ? '<button type="button" class="verb-forms" title="文の動詞の形（is doing / does）を、動詞ごとに多い方にそろえる（一覧で確かめてから入れる）" ' +
          'aria-label="動詞の形をそろえる">⇄</button>'
        : '';
    return `<th data-section="${name}"><div class="section-head">${label}${verbs}` +
        `<button type="button" class="fold-section" title="この列を畳む" aria-label="${name} を畳む">◀</button></div></th>`;
}

// サムネイルの見出し: 右端の ▶ で 1.5 倍に広げ、◀ で元の大きさに戻す
function thumbHeadHtml() {
    const [mark, title] = state.thumbZoomed ? ['◀', 'サムネイルを元の大きさに戻す'] : ['▶', 'サムネイルを 1.5 倍に広げる'];
    return `<th><div class="section-head">サムネイル<button type="button" class="thumb-zoom" title="${title}" aria-label="${title}">${mark}</button></div></th>`;
}

function headHtml() {
    return [
        thumbHeadHtml(),
        '<th title="キャプションのトークン数 / 上限">token</th>',
        ...(state.qwen ? ['<th class="qwen-head" title="Qwen（ComfyUI）で、その行の空の欄を下書きする。上から ' +
            `🤖: 上の ${state.qwenSamples} 行を見本に / 🔖: 同じマークの行（単語①と複数★の両方 → 単語①だけ・複数★だけを同じ数ずつ → ` +
            `単語① → 複数★ → 排他A）を先に、足りなければランダムに ` +
            `${state.qwenSamples} 行を見本に / 🔄: 🔖 と同じ見本で、入力のある欄も上書き（外れる単語のマークの語句は残す） / ` +
            `🎲: ほかの行からランダムに ${state.qwenSamples} 行を見本に（見本が足りなければ、公開の例（映画の場面）で補う）">🤖</th>`] : []),
        '<th>マーク</th>',
        ...state.sections.map(sectionHeadHtml),
        sideHeadHtml(),
    ].join('');
}

const PREVIEW_TITLE = '書き出すキャプション（保存したときの文面。読むだけ）';
const SIDE_TITLES = {hint: '画像と同じ名前の .txt（読むだけ。保存には影響しない）', preview: PREVIEW_TITLE,
    hint_by_qwen: 'Qwen が返した文面（読むだけ。🤖 で作る）'};

// hint の列に出せるもの: hint（あるとき）・preview・hint_by_qwen（qwen 版のとき）
const sideViews = () => [...(state.hasHints ? ['hint'] : []), 'preview', ...(state.qwen ? ['hint_by_qwen'] : [])];
// 今出しているもの（選んだものが出せなければ先頭: hint があれば hint、無ければ preview）
const sideView = () => (sideViews().includes(state.sideView) ? state.sideView : sideViews()[0]);

// hint の列の見出し: 出せるものが2つ以上なら切り替えボタン（押している方が on）、preview だけなら文字だけ
function sideHeadHtml() {
    const views = sideViews();
    if (views.length === 1) return `<th class="hint-head" title="${PREVIEW_TITLE}">preview</th>`;
    const button = view => `<button type="button" class="side-view${sideView() === view ? ' on' : ''}" ` +
        `data-view="${view}" title="${SIDE_TITLES[view]}">${view}</button>`;
    return `<th class="hint-head">${views.map(button).join('')}</th>`;
}

// 文末の「.」を外す（action の文は確定すると「.」で終わる。単語のマークの語句とは「.」を外して比べる）
const withoutPeriod = text => text.trim().replace(/\.$/, '').trim();

// 単語のマークの語句 pattern が入力の語句 phrase に合うか（* は何文字でも、ほかは文字のまま）。marks.py の matches_pattern と同じ
function matchesPattern(pattern, phrase) {
    const [p, t] = [withoutPeriod(pattern), withoutPeriod(phrase)];
    if (!p.includes('*')) return p === t;
    return new RegExp(`^${p.split('*').map(s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('.*')}$`).test(t);
}

// 行に付く単語のマーク（番号）: 設定した語句が、その段落（A, B も）のそのキーの行（キーなしは文の行）の語句に合う
// marks.py の auto_marks_of と同じ
const autoMarksOf = row => state.autoMarks.flatMap((m, i) => (m && state.sections.some(s => baseName(s) === m.section
    && phrasesOfKey(row.texts[s], m.key).some(p => matchesPattern(m.phrase, p))) ? [i] : []));

const keyLabel = key => key || '（キーなし）';

// 単語のマークの設定（段落 / キー / 語句）
const autoMarkSetting = m => `${m.section} / ${keyLabel(m.key)} / ${m.phrase}`;

// 単語のマークの説明（帯のボタンの title）
function autoMarkTitle(i) {
    const label = state.markChoices.auto[i];
    const m = state.autoMarks[i];
    return m ? `${label} ${autoMarkSetting(m)}（右クリックで変える）` : `${label}（右クリックで、段落・キー・語句を選ぶ）`;
}

// マークの欄: 縦長の 4 列 × 8 行。左から排他（A〜H のどれか1つ）、複数（★●▲■◆♥♣♠）、単語（①〜⑧ と ⑨〜⑯。
// 入力から付く。押すとその語句を入れ、マウスを載せると設定だけ見える。語句を決めていない番号は何も出さない）
// ボタンは番号を持ち、記号を見せる
function marksHtml(row) {
    const button = (kind, mark, label, on) =>
        `<button type="button" class="mark-btn${on ? ' on' : ''}" data-kind="${kind}" data-mark="${mark}">${escapeHtml(label)}</button>`;
    const one = state.markChoices.one.map((label, i) => button('one', i, label, row.mark === i)).join('');
    const many = state.markChoices.many.map((label, i) => button('many', i, label, row.marks.includes(i))).join('');
    const on = autoMarksOf(row);
    const setting = i => (state.autoMarks[i] ? ` title="${escapeHtml(autoMarkSetting(state.autoMarks[i]))}"` : '');
    const auto = state.markChoices.auto.map((label, i) =>
        `<span class="mark-auto${on.includes(i) ? ' on' : ''}" data-mark="${i}"${setting(i)}>${escapeHtml(label)}</span>`).join('');
    return `<td class="marks"><div class="mark-grid">${one}${many}${auto}</div></td>`;
}

// マークの絞り込みに合うか: 何も押していなければ全部。印のボタンを押していれば、押した印のどれかがある行。
// ☓ を押していれば、その印（左端の ☓ はその段の印すべて）が無い行（☓ は全部に掛ける）
function matchesFilter(row) {
    const kinds = ['one', 'many', 'auto'];
    if (kinds.every(kind => !state.filter[kind].size && !state.without[kind].size)) return true;
    const marks = {one: row.mark === null ? [] : [row.mark], many: row.marks, auto: autoMarksOf(row)};
    const pressed = kinds.filter(kind => state.filter[kind].size);
    const any = !pressed.length || pressed.some(kind => [...state.filter[kind]].some(m => marks[kind].includes(m)));
    return any && kinds.every(kind => [...state.without[kind]].every(m => (m === 'none' ? !marks[kind].length : !marks[kind].includes(m))));
}

// hint の欄: 読むだけ（編集できず、保存やキャプションに影響しない）。全文を出し（高さは中身に合わせる）、右上のボタンで畳める
function hintHtml(row) {
    if (!row.hint) return '<td class="hint"></td>';
    if (state.foldedHints.has(row['サムネイル'])) {
        return '<td class="hint folded"><button type="button" class="hint-toggle" title="この画像の hint を開く">＋ hint</button></td>';
    }
    return '<td class="hint"><button type="button" class="hint-toggle" title="この画像の hint を畳む">－</button>' +
        `<textarea readonly rows="1" aria-label="hint">${escapeHtml(row.hint)}</textarea></td>`;
}

// preview の欄: 書き出すキャプションの全文（読むだけ。見た目と動きは hint と同じ）。入力の無い行は空
function previewHtml(row) {
    if (!row.caption) return '<td class="hint preview"></td>';
    return `<td class="hint preview"><textarea readonly rows="1" aria-label="preview">${escapeHtml(row.caption)}</textarea></td>`;
}

// hint_by_qwen の欄: Qwen が返した文面のまま（読むだけ。見た目と動きは preview と同じ）。答えの無い行は空
function qwenHintHtml(row) {
    if (!row.qwen_hint) return '<td class="hint preview"></td>';
    return `<td class="hint preview"><textarea readonly rows="1" aria-label="hint_by_qwen">${escapeHtml(row.qwen_hint)}</textarea></td>`;
}

const SIDE_HTML = {hint: hintHtml, preview: previewHtml, hint_by_qwen: qwenHintHtml};
const sideHtml = row => SIDE_HTML[sideView()](row);

// hint の高さを中身に合わせる（CSS の field-sizing が効かないブラウザ向け。先に全部読んでから書き、描き直しを1回にする）
function fitHints(root) {
    if (!root || CSS.supports('field-sizing', 'content')) return;
    const areas = [...root.querySelectorAll('td.hint textarea')];
    const heights = areas.map(el => el.scrollHeight);
    areas.forEach((el, i) => {
        if (heights[i]) el.style.height = `${heights[i] + 2}px`;  // 見えていない（0）ときは触らない
    });
}

// 畳んだもの（kind: hints は hint の画像の名前、sections は段落の列）を、プロジェクトごとにブラウザに覚える
const foldedKey = (kind, name = state.projectName) => `pictag:folded-${kind}:${name}`;

function loadFolded(kind) {
    try {
        return new Set(JSON.parse(localStorage.getItem(foldedKey(kind)) || '[]'));
    } catch {
        return new Set();
    }
}

function saveFolded(kind, names) {
    try {
        localStorage.setItem(foldedKey(kind), JSON.stringify([...names]));
    } catch {
        // 覚えられなくても、畳む・開くはできる
    }
}

// hint の列に出すもの（hint / preview）も、プロジェクトごとにブラウザに覚える
const sideViewKey = (name = state.projectName) => `pictag:side-view:${name}`;

function loadSideView() {
    try {
        return localStorage.getItem(sideViewKey()) || 'hint';  // 出せないものは sideView() が先頭に置き換える
    } catch {
        return 'hint';
    }
}

function saveSideView() {
    try {
        localStorage.setItem(sideViewKey(), state.sideView);
    } catch {
        // 覚えられなくても、切り替えはできる
    }
}

// サムネイルを広げているかも、プロジェクトごとにブラウザに覚える
const thumbZoomKey = (name = state.projectName) => `pictag:thumb-zoom:${name}`;

function loadThumbZoom() {
    try {
        return localStorage.getItem(thumbZoomKey()) === 'on';
    } catch {
        return false;
    }
}

function saveThumbZoom() {
    try {
        localStorage.setItem(thumbZoomKey(), state.thumbZoomed ? 'on' : 'off');
    } catch {
        // 覚えられなくても、広げる・戻すはできる
    }
}

// プロジェクトごとにブラウザに覚えたもの（畳んだもの・hint の列に出すもの・サムネイルの大きさ）を、改名した名前へ移す
function moveRemembered(from, to) {
    const keys = name => [foldedKey('hints', name), foldedKey('sections', name), sideViewKey(name), thumbZoomKey(name)];
    const targets = keys(to);
    try {
        keys(from).forEach((key, i) => {
            const value = localStorage.getItem(key);
            if (value === null) return;
            localStorage.setItem(targets[i], value);
            localStorage.removeItem(key);
        });
    } catch {
        // 覚えられなくても改名はできる（畳んだものなどは初めの形に戻る）
    }
}

// 読み込みで名前を変えた画像（拡張子だけ違う画像。renamed: [[元の名前, 新しい名前]]）の、畳んだ hint を新しい名前へ移す
function carryFoldedHints(renamed = []) {
    if (!renamed.length) return;
    const names = new Map(renamed);
    state.foldedHints = new Set([...state.foldedHints].map(name => names.get(name) ?? name));
    saveFolded('hints', state.foldedHints);
}

function toggleHint(button) {
    const tr = button.closest('tr');
    const name = tr.dataset.name;
    if (state.foldedHints.has(name)) state.foldedHints.delete(name);
    else state.foldedHints.add(name);
    saveFolded('hints', state.foldedHints);
    tr.querySelector('td.hint').outerHTML = hintHtml(state.byIndex.get(Number(tr.dataset.index)));
    fitHints(tr);
}

// 段落の列を畳む・開く（見出しの ◀ / ▶）。編集中の欄は先に確定し、表を描き直す
// 段落の列を畳む・開く。描き直すとほかの列の幅が変わって行の高さが変わるので、行 index（既定は見えていた最初の行。
// 上が切れていない行）を、押す前と同じ位置に見せ直す
function toggleSection(section, index = null) {
    commitEdit();
    const anchor = index === null ? firstWholeRow() : rowElement(index);
    const gap = anchor ? belowHead(anchor) : 0;
    if (state.foldedSections.has(section)) state.foldedSections.delete(section);
    else state.foldedSections.add(section);
    saveFolded('sections', state.foldedSections);
    renderTable();
    if (anchor) showRowBelowHead(Number(anchor.dataset.index), gap);
}

// 畳んだ列の欄をクリック: 列を開いて、その欄の編集を始める（クリックした行は、押す前と同じ位置に）
function openSection(section, index) {
    toggleSection(section, index);
    startEdit(rowElement(index).querySelector(`td.cell[data-section="${CSS.escape(section)}"]`));
}

// サムネイルを広げる・戻す（見出しの ▶ / ◀）。表は描き直さず、見出しと大きさ・借りる幅だけを変える
function toggleThumbZoom() {
    state.thumbZoomed = !state.thumbZoomed;
    saveThumbZoom();
    $('gridHead').innerHTML = headHtml();
    zoomThumbnails();
}

// 列の見出しの下端（画面上の位置。見出しのセルは表の上に張り付く）
const headBottom = () => $('gridHead').querySelector('th').getBoundingClientRect().bottom;

// 見えている範囲で、上が切れていない最初の行（無ければ、一番上に見えている行）
function firstWholeRow() {
    const top = headBottom();
    const bottom = $('imagesView').getBoundingClientRect().bottom;
    const rows = [...$('gridBody').rows].filter(tr => tr.getBoundingClientRect().height > 0);
    return rows.find(tr => tr.getBoundingClientRect().top >= top - 0.5 && tr.getBoundingClientRect().top < bottom)
        || rows.find(tr => tr.getBoundingClientRect().bottom > top);
}

// 行の上端の、列の見出しの下端からの距離（px）
const belowHead = tr => tr.getBoundingClientRect().top - headBottom();

// 行を、列の見出しの下端から gap だけ下に見せる（表の端で届かないときは、届くところまで）
function showRowBelowHead(index, gap) {
    const tr = rowElement(index);
    if (tr) $('imagesView').scrollTop += belowHead(tr) - gap;
}

// 最後に書き換えた行（書き換えた時刻がいちばん新しい行。記録が無ければ undefined）
const lastEditedRow = () => state.rows.reduce((last, r) => (r.edited_at && (!last || r.edited_at > last.edited_at) ? r : last), undefined);

// 📍（2段目の右端）を描き直す: 書き換えた行が無ければ押せない。説明に行先の画像の名前
function paintResumeButton() {
    const row = lastEditedRow();
    $('resumeButton').disabled = !row;
    $('resumeButton').title = row ? `続きへ: 最後に書き換えた行（${row['サムネイル']}）を見せる`
        : '続きへ: 書き換えた行はまだありません（書き換えると、ここから戻れます）';
}

// 📍: 最後に書き換えた行を、列の見出しのすぐ下に見せる。絞り込みなどで隠れていれば、絞り込みは変えずに知らせるだけ
function resume() {
    commitEdit();
    const row = lastEditedRow();
    if (!row) return;
    const tr = rowElement(row.index);
    if (!tr || tr.getBoundingClientRect().height === 0) {
        setStatus(`${row['サムネイル']}（最後に書き換えた行）は、絞り込みか「削除済み画像を表示」で隠れています`, 'warn');
        return;
    }
    showRowBelowHead(row.index, 0);
}

// hint の列の中身を切り替える（見出しの hint / preview）。編集中の欄は先に確定し、表を描き直す
// hint と preview は行ごとに高さが違うので、見えていた最初の行（上が切れていない行）を、押す前と同じ位置に見せ直す
function switchSideView(view) {
    commitEdit();
    const anchor = firstWholeRow();
    const gap = anchor ? belowHead(anchor) : 0;
    state.sideView = view;
    saveSideView();
    renderTable();
    if (anchor) showRowBelowHead(Number(anchor.dataset.index), gap);
}

// token の欄: トークン数と上限を2行で（ファイル名はサムネイルの title）。クリックで行を選ぶ
function metaHtml(row) {
    const known = row.tokens !== null && row.tokens !== undefined;
    const over = known && row.tokens > state.tokenLimit;
    return `<div class="tokens${over ? ' over' : ''}" title="${escapeHtml(row.caption || '（空）')}">${known ? row.tokens : '—'}\n/ ${state.tokenLimit}</div>`;
}

// 見本になる行か（削除済みでなく、キャプションがある）
const isSample = row => !row.is_dead && Boolean(row.caption);

// 行より上にある見本の数（見本の数（state.qwenSamples）まで数えれば足りる）
function samplesAbove(index) {
    let count = 0;
    for (const row of state.rows) {
        if (row.index === index || count >= state.qwenSamples) break;
        if (isSample(row)) count += 1;
    }
    return count;
}

// Qwen の欄（qwen 版だけ）: 上から 🤖 🔖 🔄 🎲。Qwen でその行の空の欄を下書きする（🔄 は入力のある欄も上書き）。
// 🤖 は上の行、🔖・🔄 は同じマークの行を先に、🎲 はほかの行からランダムに、見本の数（state.qwenSamples）だけ見本に。
// 見本が足りなければ、足りない分は公開の例（映画の場面）で補う（何行補うかは title）。書いている間は、押した方が ⏳ で、どれも押せない
function qwenHtml(row) {
    const busy = state.qwenBusy.get(row.index);
    const n = state.qwenSamples;
    const elsewhere = state.rows.filter(isSample).length - (isSample(row) ? 1 : 0);
    const marked = `同じマークの行（単語①と複数★の両方 → 単語①だけ・複数★だけを同じ数ずつ → 単語① → 複数★ → 排他A）を先に、` +
        `足りなければランダムに ${n} 行`;
    const button = (mode, mark, count, source, does = '空の欄を下書きする') => {
        const ready = !row.is_dead && !busy;
        const added = Math.min(n - count, state.qwenPublic);
        const short = count < n ? `。キャプションのある行が ${count} 行なので、公開の例（映画の場面）を ${added} 行足す` : '';
        const title = busy === mode ? 'Qwen が書いています' : row.is_dead ? '元の画像がありません'
            : `Qwen で、この行の${does}（見本は${source}${short}）`;
        return `<button type="button" class="qwen-btn" data-mode="${mode}" title="${title}"${ready ? '' : ' disabled'}>` +
            `${busy === mode ? '⏳' : mark}</button>`;
    };
    return '<td class="qwen">' +
        button('near', '🤖', samplesAbove(row.index), `上の ${n} 行`) +
        button('mark', '🔖', elsewhere, marked) +
        button('overwrite', '🔄', elsewhere, marked,
            '欄を上書きする。答えにあるキーと文は入力があっても置き換え、外れる単語のマークの語句は残す') +
        button('random', '🎲', elsewhere, `ほかの行からランダムに ${n} 行`) +
        '</td>';
}

// Qwen の欄（🤖🔖🔄🎲）だけを描き直す（キャプションが変わると、下の行の見本の数も変わる）
function paintQwenButtons() {
    if (!state.qwen) return;
    const trs = new Map([...$('gridBody').rows].map(tr => [Number(tr.dataset.index), tr]));
    for (const row of state.rows) {
        const td = trs.get(row.index)?.querySelector('td.qwen');
        if (td) td.outerHTML = qwenHtml(row);
    }
}

// 🤖 / 🔖 / 🔄 / 🎲: Qwen（ComfyUI）に下書きさせ、その行の空の欄に入れる（🔄 は入力のある欄も上書き。数秒。
// ComfyUI が初めて Qwen を読むときは数十秒）
async function qwenFill(index, mode) {
    commitEdit();
    const name = state.byIndex.get(index)['サムネイル'];
    state.qwenBusy.set(index, mode);
    paintQwenButtons();
    setStatus(`${name} を Qwen が書いています…`);
    try {
        const res = await postJson('/qwen_fill', {row_index: index, mode});
        if (!res.success) {
            setStatus(res.message, 'error');
            return;
        }
        replaceRow(res.row);
        setDirty(true);
        refreshWords();
        const overwrite = mode === 'overwrite';
        const note = `${res.public ? `見本のうち ${res.public} 行は公開の例。` : ''}Qwen の答えは hint_by_qwen で見られます`;
        setStatus(res.filled.length
            ? `${name} の ${res.filled.join('・')} ${overwrite ? 'を上書きしました' : 'に下書きを入れました'}（${note}）`
            : `${name}: ${overwrite ? '入れられる答えがありませんでした' : '入れられる空の欄がありませんでした'}（${note}）`,
            res.filled.length ? 'ok' : 'warn');
    } finally {
        state.qwenBusy.delete(index);
        paintQwenButtons();
    }
}

// その行の 👀 の選択肢: 人物の種類（A, B を除いた名前）ごとに、その行で入力のある段落が2つ以上ならその段落（guy A, guy B）、
// ほかは種類の名前（guy）だけ（入力のある段落が1つの種類は、キャプションも A, B を除いた名前で書き出す）。
// 選ぶ元は、サーバーの選択肢（第三者と、種類の名前・段落の名前の全部）
function rowPovChoices(row) {
    const [third, ...people] = state.viewChoices.pov;
    const nameOf = choice => choice.phrase.replace(/ POV$/, '');
    const present = state.sections.filter(s => !state.fixedSections.includes(s)
        && (row.texts[s] || '').split('\n').some(line => parseLine(line).phrases.length));
    const bases = [...new Set(people.map(c => baseName(nameOf(c))))];
    return [third, ...bases.flatMap(base => {
        const written = present.filter(s => baseName(s) === base);
        const names = written.length >= 2 ? written : [base];
        return names.map(name => people.find(c => nameOf(c) === name)).filter(Boolean);
    })];
}

// view のボタン（各組の先頭の ☓ でその組の語句を消す）。押されている語句は on
// 🎥 は絵文字だけ、👀 は絵文字と A, B（女性・男性で色を変える）。語句はマウスを載せると見える
function choicesHtml(row) {
    const view = phrasesOfKey(row.texts.picture, 'view');
    const targeted = state.viewChoices.targeted || [];
    // ボタンの語句にあたる、入力の語句（close-up は後ろに対象の付いたもの（close-up face）も）。title にはこれを出す
    const current = phrase => view.find(p => p === phrase || (targeted.includes(phrase) && p.startsWith(`${phrase} `)));
    // classes: 絵文字だけのボタンは icon（☓ と同じ幅）、👀 の人物は female / male
    const button = (phrase, label, group, classes = []) => {
        const set = current(phrase);
        return `<button type="button" class="${['choice', ...classes, set ? 'on' : ''].filter(Boolean).join(' ')}" data-group="${group}" ` +
            `data-phrase="${escapeHtml(phrase)}" title="${escapeHtml(set || phrase)}" aria-label="${escapeHtml(phrase)}">${escapeHtml(label)}</button>`;
    };
    const clear = group => `<button type="button" class="choice clear" data-group="${group}" title="選択なし">☓</button>`;
    const emoji = state.viewChoices.camera_emoji || {};
    const camera = state.viewChoices.camera.map((phrases, g) =>
        `<span class="group">${clear(`camera${g}`)}` +
        `${phrases.map(p => button(p, emoji[p] || p.replace(/^from /, ''), `camera${g}`, emoji[p] ? ['icon'] : [])).join('')}</span>`);
    const pov = `<span class="group">${clear('pov')}` +
        `${rowPovChoices(row).map(c => button(c.phrase, [c.emoji, c.label].filter(Boolean).join(' '), 'pov', [c.tone, c.label ? '' : 'icon'])).join('')}</span>`;
    return `<div class="choices"><div class="choice-row camera"><span class="choice-label">🎥</span>${camera.join('')}</div>` +
        `<div class="choice-row pov"><span class="choice-label">👀</span>${pov}</div></div>`;
}

// picture の列幅: 🎥 の行の最後のボタン（close-up）の右端 + 10px。ボタンは固定なので、表が見えているときに1回だけ測る
const PICTURE_SPARE = 10;

function fitPictureColumn() {
    if ($('grid').style.getPropertyValue('--picture-width')) return;
    const last = [...$('gridBody').querySelectorAll('td.cell[data-section="picture"] .choice-row.camera .choice')].pop();
    const td = last && last.closest('td');
    if (!td || td.getBoundingClientRect().width === 0) return;
    const right = last.getBoundingClientRect().right - td.getBoundingClientRect().left;
    const border = parseFloat(getComputedStyle(td).borderRightWidth) || 0;
    $('grid').style.setProperty('--picture-width', `${Math.ceil(right + PICTURE_SPARE + border)}px`);
}

// サムネイルは正方形で、picture の欄のキーの名前の行とボタンの高さ（見えている行でいちばん低いもの）に合わせる。表を描くたびに測る
// 値の行（キーの名前の下）の分では大きくしない（列を広げない）。picture を畳んでいるときは測らない（畳む前の大きさのまま）
function fitThumbnails() {
    if (!state.foldedSections.has('picture')) {
        const heights = [...$('gridBody').querySelectorAll('td.cell[data-section="picture"]')]
            .filter(td => td.getBoundingClientRect().height > 0)
            .map(td => [...td.querySelectorAll('.text .key'), ...td.querySelectorAll(':scope > .choices')]
                .reduce((sum, el) => sum + el.getBoundingClientRect().height + parseFloat(getComputedStyle(el).marginTop), 0));
        if (heights.length) state.thumbBase = Math.floor(Math.min(...heights));
    }
    zoomThumbnails();
}

const THUMB_ZOOM = 1.5;     // ▶ で広げたときの大きさ（元の大きさの倍率）
const THUMB_DEFAULT = 96;  // 測れていないとき（picture を畳んだまま開いたとき）の大きさ（CSS の既定と同じ）

// サムネイルの大きさを入れる。広げているときは 1.5 倍にし、増えた幅は picture より右の畳んでいない列（右端の列も）から
// 同じだけずつ借りる（--lend の分だけ各列の最小・最大の幅を下げる。段落は最小の幅で、残りは右端の列が取っているため）
function zoomThumbnails() {
    const base = state.thumbBase || THUMB_DEFAULT;
    const extra = state.thumbZoomed ? Math.round(base * (THUMB_ZOOM - 1)) : 0;
    const lenders = state.sections.filter(s => s !== 'picture' && !state.foldedSections.has(s)).length + 1;
    $('grid').style.setProperty('--thumb-size', `${base + extra}px`);
    $('grid').style.setProperty('--lend', `${extra / lenders}px`);
}

const choiceGroup = group => (group === 'pov' ? state.viewChoices.pov.map(c => c.phrase) : state.viewChoices.camera[Number(group.slice(6))]);

// 欄の表示: 確定タグのキーを並びどおりに、入力欄と同じくキーの名前の下に値を出す。値の無いキーは名前だけ薄く、自動のキー（characters）は自動の値
// ほかの行（キーの無い文・確定タグに無いキー）は、あれば「その他:」の下に（最後のキーの値の続きに見えないように）。確定タグの無い段落（action・else）は行をそのまま
// 同じグループの語句が2つ以上ある行には ⚠（CSS）
function cellHtml(section, row) {
    const keys = templateKeys(section);
    const byKey = phrasesByKey(row.texts[section]);
    const lineHtml = (line, keyed) => {
        const {key, phrases} = parseLine(line);
        if (state.autoKeys.includes(key)) {
            const value = row.characters || '';
            return `<div class="ln auto${value ? '' : ' empty'}" title="自動">${keyValueHtml(key, value)}</div>`;
        }
        const conflict = key ? conflictOf(key, byKey[key] || []) : null;
        const classes = ['ln', phrases.length === 0 ? 'empty' : '', conflict ? 'conflict' : ''].filter(Boolean).join(' ');
        const title = conflict ? ` title="${escapeHtml(`1つだけのグループ: ${conflict.phrases.join(' / ')}`)}"` : '';
        const body = keyed ? keyValueHtml(key, phrases.length ? line.slice(line.indexOf(':') + 1).trim() : '') : escapeHtml(line.trimEnd());
        return `<div class="${classes}"${title}>${body}</div>`;
    };
    const lines = mergeTemplate(row.texts[section] || '', keys);
    const rest = lines.slice(keys.length).map(line => lineHtml(line, false));
    const others = keys.length && rest.length ? ['<div class="others">その他:</div>', ...rest] : rest;
    return `<div class="text">${[...lines.slice(0, keys.length).map(line => lineHtml(line, true)), ...others].join('')}</div>` +
        `${keys.includes('view') ? choicesHtml(row) : ''}`;
}

// キーの名前の行と、その下の値の行（名前の後ろの空白は、文字として読んだときに「key: value」になるように）
const keyValueHtml = (key, value) => `<div class="key">${escapeHtml(key)}: </div>${value ? `<div class="val">${escapeHtml(value)}</div>` : ''}`;

// 段落の欄。畳んだ列は、入力があれば ● だけ（クリックで列を開いて編集を始める）
function cellTd(section, row) {
    const s = escapeHtml(section);
    if (!state.foldedSections.has(section)) return `<td class="cell" data-section="${s}">${cellHtml(section, row)}</td>`;
    const mark = (row.texts[section] || '').trim() ? '●' : '';
    return `<td class="cell folded" data-section="${s}" title="${s} を開いて書く">${mark}</td>`;
}

function rowHtml(row) {
    const name = row['サムネイル'];
    const classes = [row.is_dead ? 'dead' : '', state.selected.has(row.index) ? 'selected' : '',
        matchesFilter(row) ? '' : 'filtered'].filter(Boolean).join(' ');
    const cells = state.sections.map(s => cellTd(s, row)).join('');
    return `<tr data-index="${row.index}" data-name="${escapeHtml(name)}" class="${classes}">` +
        `<td class="thumb"><img loading="lazy" src="/thumbnail/${encodeURIComponent(name)}" alt="" title="${escapeHtml(name)}"></td>` +
        `<td class="meta">${metaHtml(row)}</td>${state.qwen ? qwenHtml(row) : ''}${marksHtml(row)}${cells}${sideHtml(row)}</tr>`;
}

const rowElement = index => $('gridBody').querySelector(`tr[data-index="${index}"]`);

function renderTable() {
    $('gridHead').innerHTML = headHtml();
    $('gridBody').innerHTML = state.rows.map(rowHtml).join('');
    fitPictureColumn();
    fitThumbnails();
    fitHints($('gridBody'));
    const bulkSection = $('bulkSection').value;  // 描き直しても一括入力の段落は選んだままにする
    $('bulkSection').innerHTML = state.sections.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
    if (state.sections.includes(bulkSection)) $('bulkSection').value = bulkSection;
    fillBulkKeys();
    fillMoveSections();
    $('emptyNote').hidden = state.loaded;
    $('tools').hidden = !state.loaded || state.view !== 'images';
    $('markTools').hidden = !state.loaded || state.view !== 'images';
    setDirty(state.dirty);
    updateSelectionInfo();
    paintResumeButton();
}

// 行だけ描き直す（グループが変わったときの ⚠ の付け直し）
function rerenderRows() {
    commitEdit();
    $('gridBody').innerHTML = state.rows.map(rowHtml).join('');
    fitHints($('gridBody'));
}

function replaceRow(row) {
    state.byIndex.set(row.index, row);
    state.rows = state.rows.map(r => (r.index === row.index ? row : r));
    paintResumeButton();
    const tr = rowElement(row.index);
    if (!tr) return;
    tr.outerHTML = rowHtml(row);
    fitHints(rowElement(row.index));
}

async function refreshTable() {
    commitEdit();
    const body = await getJson('/get_table_data');
    state.sections = body.sections;
    state.rows = body.data;
    state.byIndex = new Map(body.data.map(r => [r.index, r]));
    state.hasHints = body.data.some(r => r.hint);
    state.tokenLimit = body.token_limit;
    state.qwenSamples = body.qwen_samples;
    state.qwenPublic = body.qwen_public;
    state.templates = body.templates;
    state.fixedSections = body.fixed_sections;
    state.autoKeys = body.auto_keys;
    state.othersSection = body.others_section;
    state.candidateGroups = body.candidate_groups;
    state.qwen = body.qwen;
    state.viewChoices = body.view_choices;
    if (state.markChoices.one.length === 0) fillMarkFilters(body.mark_choices);
    state.markChoices = body.mark_choices;
    state.autoMarks = body.auto_marks;
    paintMarkFilters();
    state.selected = new Set([...state.selected].filter(i => state.byIndex.has(i)));
    if (!state.byIndex.has(state.anchor)) state.anchor = null;
    state.loaded = true;
    renderTable();
    refreshWords();
}

// ---- 英字だけ（キャプションや辞書に入る欄。全角は半角に、日本語などは消す） ----

// キャプションや辞書に入る欄（表の入力欄・一括入力・キーを移す・単語のマークの語句・段落を追加・共用辞書の足す語句と改名）
const ENGLISH_FIELDS = 'td.cell textarea, #bulkText, #movePhrase, #moveNew, #autoMarkPhrase, #sectionName, #dictAddText, .rename-input';
// 英字の記号にそろえる文字（全角の英数字・記号・空白は NFKD で半角になる）
const ENGLISH_MARKS = {'、': ',', '。': '.', '‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', '\t': ' '};

// 英字にそろえ（全角は半角、アクセントは外す、「、」「。」と曲がった引用符・ダッシュは英字の記号、タブは空白）、
// そろえても英字（半角の英数字・記号・空白。複数行の欄は改行も）にならない文字は消す。{clean: 残した文字, removed: 消した文字}
function splitEnglish(text, multiline) {
    const allowed = multiline ? /[\x20-\x7e\n]/ : /[\x20-\x7e]/;
    const chars = [...text.normalize('NFKD').replace(/[̀-ͯ]/g, '')].map(ch => ENGLISH_MARKS[ch] ?? ch);
    return {clean: chars.filter(ch => allowed.test(ch)).join(''), removed: chars.filter(ch => !allowed.test(ch)).join('')};
}

const englishOnly = (text, multiline = true) => splitEnglish(text, multiline).clean;
const warnNotEnglish = removed => setStatus(`英字以外は入れられません（${removed} を外しました）`, 'warn');

// 欄の文字を英字だけにする（カーソルは、そろえたあとの同じ位置に）。消した文字があれば知らせる。変えたら true
function keepEnglish(el) {
    const multiline = el.tagName === 'TEXTAREA';
    const {clean, removed} = splitEnglish(el.value, multiline);
    if (clean === el.value) return false;
    const caret = englishOnly(el.value.slice(0, el.selectionStart), multiline).length;
    el.value = clean;
    el.setSelectionRange(caret, caret);
    if (removed) warnNotEnglish(removed);
    return true;
}

// ---- 空白と改行の印（打っている欄の上に、同じ文字組みの層を重ねて ␣ と ↵ だけを描く。文字には入らない） ----

// 欄から印の層へ写す文字組み（折り返しと文字の位置をそろえる）
const MIRRORED_STYLES = ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing', 'wordSpacing', 'lineHeight', 'tabSize',
    'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth'];

const whitespaceHtml = text => escapeHtml(text)
    .replace(/ /g, '<span class="sp"> </span>')
    .replace(/\n/g, '<span class="nl"></span>\n');

// 印の層を描く（欄のすぐ後ろの要素）。欄の中がスクロールしていれば合わせる
function paintWhitespace(el) {
    const layer = el.nextElementSibling;
    layer.innerHTML = whitespaceHtml(el.value);
    layer.scrollTop = el.scrollTop;
    layer.scrollLeft = el.scrollLeft;
}

// 印の層の文字組みと幅を欄に合わせて描く。幅はスクロールバーを除いた欄の中身に合わせ、一行の欄は文字の上下の位置も合わせる
function fitWhitespace(el) {
    const layer = el.nextElementSibling;
    const style = getComputedStyle(el);
    MIRRORED_STYLES.forEach(name => { layer.style[name] = style[name]; });
    layer.style.width = `${el.clientWidth + parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth)}px`;
    if (el.tagName === 'INPUT') {
        layer.style.lineHeight = `${el.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom)}px`;
    }
    paintWhitespace(el);
}

// 欄を包んで印の層を重ねる（包んだ要素を返す。欄が画面にあれば、その場所で包む）
function withWhitespaceMarks(el) {
    const wrap = document.createElement(el.tagName === 'TEXTAREA' ? 'div' : 'span');
    wrap.className = 'ws';
    if (el.parentNode) el.replaceWith(wrap);
    const layer = document.createElement('div');
    layer.className = 'ws-marks';
    layer.setAttribute('aria-hidden', 'true');
    wrap.append(el, layer);
    el.addEventListener('focus', () => fitWhitespace(el));
    ['input', 'scroll', 'keyup', 'click', 'select'].forEach(type => el.addEventListener(type, () => paintWhitespace(el)));
    new ResizeObserver(() => fitWhitespace(el)).observe(el);  // 高さを合わせたとき・表示されたとき・窓の幅を変えたとき
    return wrap;
}

// ---- 入力欄 ----

function startEdit(td) {
    if (state.editor && state.editor.td === td) return;
    commitEdit();
    const index = Number(td.closest('tr').dataset.index);
    const section = td.dataset.section;
    // 編集する行を選択状態にする（選択中の行の中なら選択はそのまま）
    if (!state.selected.has(index)) {
        state.selected = new Set([index]);
        state.anchor = index;
        paintSelection();
    }
    // 確定タグのある段落は、キーごとの欄に分ける（キーの名前の下に、そのキーの値だけ。最後に、ほかの行の「その他」）。無い段落（action・else）は1つの欄
    // 確定タグに extra のある段落（picture）は、extra に書けるので「その他」を出さない（前に書いたほかの行があれば、消えないように出す）
    const keys = editKeys(section);
    const {values, rest} = splitText(state.byIndex.get(index).texts[section] || '', keys);
    const others = !keys.includes('extra') || rest.length > 0;
    const fieldOf = (key, value) => {
        const el = document.createElement('textarea');
        el.dataset.key = key;
        el.value = value;
        if (keys.length) el.rows = 1;  // 分けた欄は1行から（打った分だけ伸びる）
        return el;
    };
    const fields = [...keys.map(key => fieldOf(key, values[key])), ...(others ? [fieldOf('', rest.join('\n'))] : [])];
    const editor = document.createElement('div');
    editor.className = keys.length ? 'editor split' : 'editor';
    editor.append(...fields.flatMap(el => {
        if (!keys.length) return [withWhitespaceMarks(el)];
        const label = document.createElement('div');
        label.className = 'field-key';
        label.textContent = el.dataset.key ? `${el.dataset.key}:` : 'その他:';
        return [label, withWhitespaceMarks(el)];
    }));
    td.replaceChildren(editor);
    state.editor = {index, section, td, keys, fields};
    fields.forEach(el => {
        el.addEventListener('input', () => { autosize(el); showSuggestions(el, section, editorContext); });
        el.addEventListener('keydown', event => {
            if (handleSuggestKey(event)) return;
            if (event.key === 'Escape' || (event.key === 'Enter' && event.ctrlKey)) {
                event.preventDefault();
                commitEdit();
            }
        });
        el.addEventListener('keyup', event => {
            if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) showSuggestions(el, section, editorContext);
        });
        el.addEventListener('click', () => showSuggestions(el, section, editorContext));
        autosize(el);
    });
    // 欄を移っても確定しない（前の欄の候補はしまう）。欄の外へフォーカスが出たら確定する
    editor.addEventListener('focusout', event => {
        hideSuggestions();
        if (!editor.contains(event.relatedTarget)) commitEdit();
    });
    // キーの名前などを押してもフォーカスを外さない（外すと確定する）。キーの名前を押せば、その欄へ
    editor.addEventListener('mousedown', event => {
        if (event.target.tagName === 'TEXTAREA') return;
        event.preventDefault();
        const label = event.target.closest('.field-key');
        if (label) focusEnd(label.nextElementSibling.querySelector('textarea'));
    });
    // 最初の値の無いキーの欄（無ければ最後の欄）の末尾から
    focusEnd(fields.find(el => el.dataset.key && !el.value.trim()) || fields[fields.length - 1]);
}

function focusEnd(el) {
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
}

function commitEdit() {
    const editor = state.editor;
    if (!editor) return;
    state.editor = null;
    hideSuggestions();
    const row = state.byIndex.get(editor.index);
    const fields = editor.fields.map(el => spacesToCommasInField({key: el.dataset.key, value: el.value}));
    const text = tidyInput(composeEditor(fields, editor.keys), editor.section);
    const changed = text !== (row.texts[editor.section] || '');
    row.texts[editor.section] = text;
    editor.td.innerHTML = cellHtml(editor.section, row);
    if (!changed) return;
    refreshAutoMarks(row);
    track(sendText(row, editor.section, text)).catch(e => setStatus(String(e.message || e), 'error'));
}

// 入力が変わった行の単語のマークを付け直す（単語のマークの絞り込みにも合わせる）
function refreshAutoMarks(row) {
    const tr = rowElement(row.index);
    if (!tr) return;
    tr.querySelector('td.marks').outerHTML = marksHtml(row);
    tr.classList.toggle('filtered', !matchesFilter(row));
}

async function sendText(row, section, text) {
    const res = await postJson('/update_text', {row_index: row.index, section, text});
    if (!res.success) {
        setStatus(`${row['サムネイル']} の入力を反映できませんでした`, 'error');
        return;
    }
    row.caption = res.caption;
    row.tokens = res.tokens;
    row.characters = res.characters;
    row.edited_at = res.edited_at;
    paintResumeButton();
    const tr = rowElement(row.index);
    if (tr) {
        tr.querySelector('td.meta').innerHTML = metaHtml(row);
        // preview を出していれば、書き出す文面も描き直す
        if (sideView() === 'preview') {
            tr.querySelector('td.hint').outerHTML = previewHtml(row);
            fitHints(tr);
        }
        // 人物の段落を書き換えると characters が変わるので picture の欄を描き直す（編集中なら触らない）
        const picture = tr.querySelector('td.cell[data-section="picture"]');
        if (picture && !picture.querySelector('textarea') && !picture.classList.contains('folded')) picture.innerHTML = cellHtml('picture', row);
    }
    paintQwenButtons();  // キャプションが空になった・空でなくなったら、下の行の見本の数が変わる
    setDirty(true);
    refreshWords();
}

// view のボタン: 押した行（選択中の行の中なら選択中の全行）の view の行に、組の語句を1つだけ置く
async function choose(button) {
    const index = Number(button.closest('tr').dataset.index);
    const rows = state.selected.has(index) ? visibleIndexes().filter(i => state.selected.has(i)) : [index];
    const group = choiceGroup(button.dataset.group);
    const clear = button.classList.contains('clear');
    commitEdit();
    await settled();
    const res = await postJson('/set_choice', {
        rows, section: 'picture', key: 'view', group,
        phrase: clear ? group[0] : button.dataset.phrase,
        on: !clear && !button.classList.contains('on'),
    });
    if (!res.success) return setStatus(res.message || '選べませんでした', 'error');
    res.rows.forEach(replaceRow);
    setDirty(true);
    refreshWords();
}

// ---- 行の選択（クリック: その行だけ / Ctrl: 足し引き / Shift: 最後にクリックした行からの範囲） ----

function visibleIndexes() {
    const showDead = $('showDead').checked;
    return state.rows.filter(r => (showDead || !r.is_dead) && matchesFilter(r)).map(r => r.index);
}

function selectVisible() {
    state.selected = new Set(visibleIndexes());
    paintSelection();
}

// 見えなくなった行を選択から外す
function dropHiddenFromSelection() {
    const visible = new Set(visibleIndexes());
    state.selected = new Set([...state.selected].filter(i => visible.has(i)));
    paintSelection();
}

function selectRow(index, event) {
    const additive = event.ctrlKey || event.metaKey;
    if (event.shiftKey && state.anchor !== null) {
        const order = visibleIndexes();
        const from = order.indexOf(state.anchor);
        const to = order.indexOf(index);
        const range = from < 0 || to < 0 ? [index] : order.slice(Math.min(from, to), Math.max(from, to) + 1);
        state.selected = new Set(additive ? [...state.selected, ...range] : range);
    } else if (additive) {
        if (state.selected.has(index)) state.selected.delete(index);
        else state.selected.add(index);
        state.anchor = index;
    } else {
        const onlyThis = state.selected.size === 1 && state.selected.has(index);
        state.selected = new Set(onlyThis ? [] : [index]);
        state.anchor = index;
    }
    paintSelection();
}

function paintSelection() {
    for (const tr of $('gridBody').rows) tr.classList.toggle('selected', state.selected.has(Number(tr.dataset.index)));
    updateSelectionInfo();
}

function updateSelectionInfo() {
    $('selectionInfo').textContent = `選択 ${state.selected.size} 行`;
    $('bulkForm').classList.toggle('idle', state.selected.size === 0);  // 行を選んでいる間だけ、一括入力と選択解除を出す
    $('deselectButton').hidden = state.selected.size === 0;
}

// ---- 操作 ----

async function bulkEdit(op) {
    commitEdit();
    const rows = visibleIndexes().filter(i => state.selected.has(i));
    const phrases = $('bulkText').value.trim();
    const key = $('bulkKey').value;
    if (!rows.length) return setStatus('行を選んでください', 'error');
    if (!phrases) return setStatus('語句を入力してください', 'error');
    const text = key ? `${key}: ${spacesToCommas(phrases)}` : phrases;
    await settled();
    const res = await postJson(op === 'add' ? '/add_phrase' : '/remove_phrase', {rows, section: $('bulkSection').value, text});
    if (!res.success) return setStatus(res.message || '一括入力できませんでした', 'error');
    res.rows.forEach(replaceRow);
    $('bulkText').value = '';
    paintWhitespace($('bulkText'));
    hideSuggestions();
    setDirty(true);
    refreshWords();
    const done = `${rows.length} 行${op === 'add' ? 'に追加' : 'から削除'}しました`;
    if (res.skipped) return setStatus(`${done}（${res.skipped} 行は、同じグループの語句があるので足していません）`, 'warn');
    setStatus(done, 'ok');
}

async function addSection() {
    const name = $('sectionName').value.trim();
    if (!name) return;
    $('sectionName').value = '';  // 応答を待つ間に次の名前を打っても消さないよう、送った時点で空にする
    const res = await postJson('/add_section', {name});
    if (!res.success) {
        if (!$('sectionName').value) $('sectionName').value = name;
        return setStatus(res.message, 'error');
    }
    setDirty(true);
    await refreshTable();
}

async function renameSection(old) {
    const typed = window.prompt('新しい段落名', old);
    if (typed === null) return;
    const {clean: name, removed} = splitEnglish(typed, false);  // 段落の名前もキャプションに出るので英字だけ
    if (removed) warnNotEnglish(removed);
    if (!name.trim() || name.trim() === old) return;
    await settled();
    const res = await postJson('/rename_section', {old, new: name});
    if (!res.success) return setStatus(res.message, 'error');
    setDirty(true);
    await refreshTable();
}

async function removeSection(name) {
    const message = `段落「${name}」を表から外しますか？\nこの段落の入力も消えます（保存しなければ、プロジェクトを開き直すと戻ります）。`;
    if (!window.confirm(message)) return;
    await settled();
    const res = await postJson('/remove_section', {name});
    if (!res.success) return setStatus(res.message, 'error');
    setDirty(true);
    await refreshTable();
}

async function freezeDictionary() {
    if (!window.confirm('今使っている語句と単語を共用辞書に入れますか？\n入れた語句は、どの画像からも消えても候補に残ります。')) return;
    commitEdit();
    await settled();
    const res = await postJson('/freeze');
    if (!res.success) return setStatus(res.message, 'error');
    refreshWords();
    setStatus(res.message, 'ok');
}

async function refreshProjects() {
    const body = await getJson('/get_existing_projects');
    const options = body.projects
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(p => `<option value="${escapeHtml(p.name)}" title="${escapeHtml(p.image_path)}">${escapeHtml(p.name)}</option>`);
    $('projectSelect').innerHTML = ['<option value="">選んでください</option>', ...options].join('');
    $('projectSelect').value = state.projectName;
}

const confirmDiscard = () => !state.dirty || window.confirm('保存していない変更があります。破棄して続けますか？');

// 読み込み（保存の読み直しも）で、拡張子だけ違う画像の名前を変えたこと（と、変えられなかった画像）
const renamedNote = ({renamed = [], rename_failed: failed = []} = {}) =>
    (renamed.length ? `。拡張子だけ違う画像の名前を変えて保存しました: ${renamed.map(([from, to]) => `${from} → ${to}`).join('、')}` : '')
    + (failed.length ? `。名前を変えられませんでした: ${failed.join('、')}` : '');

// report: 読み込みの応答（名前を変えた画像）
async function opened(name, report = {}) {
    state.projectName = name;
    state.foldedHints = loadFolded('hints');
    carryFoldedHints(report.renamed);
    state.foldedSections = loadFolded('sections');
    state.sideView = loadSideView();
    state.thumbZoomed = loadThumbZoom();
    state.selected = new Set();
    state.anchor = null;
    state.dirty = false;
    await refreshTable();
    await refreshProjects();
    const note = renamedNote(report);
    setStatus(`「${name}」を開きました（${state.rows.length} 枚）${note}`, note ? 'warn' : 'ok');
}

async function openProject() {
    const name = $('projectSelect').value;
    if (!name) return;
    commitEdit();
    if (!confirmDiscard()) {
        $('projectSelect').value = state.projectName;
        return;
    }
    await settled();
    const res = await postJson('/load_existing_project', {project_name: name});
    if (!res.success) {
        $('projectSelect').value = state.projectName;
        return setStatus(res.message, 'error');
    }
    $('imageDir').value = res.image_dir;
    await opened(name, res);
}

// confirmed: 未保存の変更を破棄してよいか、もう確かめた（参照…から）
async function loadDirectory(confirmed = false) {
    const dir = $('imageDir').value.trim();
    if (!dir) return setStatus('画像フォルダのパスを入力してください', 'error');
    commitEdit();
    if (!confirmed && !confirmDiscard()) return;
    await settled();
    const res = await postJson('/load_directory', {image_dir: dir});
    if (!res.success) return setStatus(res.message, 'error');
    await opened(dir.replace(/["']/g, '').replace(/[\\/]+$/, '').split(/[\\/]/).pop(), res);
}

// 参照…: このPCでフォルダを選ぶ窓をアプリ側で開き、選んだらそのまま読み込む
async function browseDirectory() {
    commitEdit();
    if (!confirmDiscard()) return;
    $('browseButton').disabled = true;
    setStatus('フォルダを選ぶ窓を開きました（見当たらなければタスクバーを見てください）');
    try {
        const res = await postJson('/choose_directory', {initial: $('imageDir').value.trim()});
        if (!res.success) return setStatus(res.message, 'error');
        if (!res.path) return setStatus('フォルダの選択をやめました');
        $('imageDir').value = res.path;
        await loadDirectory(true);
    } finally {
        $('browseButton').disabled = false;
    }
}

// 改名…: 今の名前を入れた窓を開く。Qwen が書いている間と、保存していない変更があるときは止める
function openRenameDialog() {
    commitEdit();
    if (state.qwenBusy.size) return setStatus('Qwen が書き終わってから改名してください', 'error');
    if (state.dirty) return setStatus('保存してから改名してください', 'error');
    $('renameName').value = state.projectName;
    $('renameDialog').returnValue = '';
    $('renameDialog').showModal();
    $('renameName').select();
}

// プロジェクトの名前（画像フォルダ・data_out・data_work のフォルダ名）を変えて開き直す。ブラウザに覚えたものも新しい名前へ移す
async function renameProject() {
    const from = state.projectName;
    await settled();
    const res = await postJson('/rename_project', {name: $('renameName').value});
    if (!res.success) return setStatus(res.message, 'error');
    moveRemembered(from, res.project_name);
    $('imageDir').value = res.image_dir;
    await opened(res.project_name, res);
    const note = renamedNote(res);
    setStatus(`「${from}」を「${res.project_name}」に改名しました${note}`, note ? 'warn' : 'ok');
}

async function save() {
    if (!state.loaded) return;
    commitEdit();
    await settled();
    const res = await postJson('/save_data');
    if (!res.success) return setStatus(res.message, 'error');
    state.dirty = false;
    carryFoldedHints(res.renamed);
    await refreshTable();
    await refreshProjects();
    const note = renamedNote(res);
    setStatus(`保存しました${note}`, note ? 'warn' : 'ok');
}

async function removeDead() {
    if (!window.confirm('削除済み画像の行を完全に削除しますか？（あわせて保存します）')) return;
    commitEdit();
    await settled();
    const res = await postJson('/remove_all_dead');
    if (!res.success) return setStatus(res.message, 'error');
    state.dirty = false;
    await refreshTable();
    setStatus(res.message, 'ok');
}

function toggleDead() {
    $('grid').classList.toggle('hide-dead', !$('showDead').checked);
    dropHiddenFromSelection();
}

// ---- マーキング ----

// マークの記号の並び（A〜H のように最初と最後）。クリアのボタンと知らせに使う
const markRange = labels => `${labels[0]}〜${labels[labels.length - 1]}`;

// クリアのボタンの名前（記号は marks.py の表から）
function fillMarkFilters(choices) {
    document.querySelectorAll('.clear-marks .hold').forEach(button => {
        const range = markRange(button.dataset.column === 'mark' ? choices.one : choices.many);
        button.textContent = `${range} をクリア`;
        button.title = `1秒長押しで、全行の ${range} を消す`;
    });
}

// 絞り込みのボタン（3段目の帯）を描く: 段（排他・複数・単語）ごとに2段。上の段は名前・左端の ☓（その段の印の無い行）・記号、
// 下の段は記号の真下に ☓（その印の無い行）。押しているものは on。単語の ①〜⑯ は設定の無いもの（と下の ☓）を薄く、語句は title（右クリックで設定）
function paintMarkFilters() {
    const noneTitle = {one: '排他の印の無い行だけ', many: '複数の印の無い行だけ', auto: '単語の印の無い行だけ'};
    document.querySelectorAll('#markFilters .filter-group').forEach(group => {
        const kind = group.dataset.kind;
        const button = (pressed, mark, label, title, extra = '') => `<button type="button" class="filter-btn${extra}` +
            `${pressed.has(mark) ? ' on' : ''}" data-kind="${kind}" data-mark="${mark}" title="${escapeHtml(title)}">${escapeHtml(label)}</button>`;
        const unset = i => (kind === 'auto' && !state.autoMarks[i] ? ' unset' : '');
        const pairs = state.markChoices[kind].map((label, i) => (kind === 'auto'
            ? button(state.filter[kind], i, label, autoMarkTitle(i), ` auto-mark${unset(i)}`)
            : button(state.filter[kind], i, label, `${label} の行だけ（もう一度押すと外す）`))
            + button(state.without[kind], i, '☓', `${label} の無い行だけ（もう一度押すと外す）`, ` without${unset(i)}`));
        group.innerHTML = `<span class="filter-label">${escapeHtml(group.dataset.label)}</span>` +
            button(state.without[kind], 'none', '☓', `${noneTitle[kind]}（もう一度押すと外す）`, ' none') + '<span></span>' + pairs.join('');
    });
}

// 絞り込みのボタンを押す・外す（印のボタンは押したもののどれかがある行、☓ はどれも無い行を出す）
function toggleFilter(kind, mark, without) {
    const pressed = (without ? state.without : state.filter)[kind];
    if (pressed.has(mark)) pressed.delete(mark);
    else pressed.add(mark);
    paintMarkFilters();
    applyFilter();
}

// ---- 単語のマークの設定（帯の ①〜⑯ を右クリック: 段落 → キー → 語句を選ぶと、その語句のある行に付く） ----

// 設定の欄を、押したボタンの下に開く（今の設定を入れておく）
function openAutoMarkForm(button) {
    const i = Number(button.dataset.mark);
    const m = state.autoMarks[i];
    const form = $('autoMarkForm');
    form.dataset.mark = i;
    $('autoMarkLabel').textContent = state.markChoices.auto[i];
    fillOptions($('autoMarkSection'), baseSections(), m ? m.section : null);
    fillOptions($('autoMarkKey'), wordMarkKeys($('autoMarkSection').value), m ? m.key : null, keyLabel);
    $('autoMarkPhrase').value = m ? m.phrase : '';
    paintWhitespace($('autoMarkPhrase'));
    form.hidden = false;
    const rect = button.getBoundingClientRect();
    form.style.left = `${Math.max(0, Math.min(rect.left, window.innerWidth - form.offsetWidth - 8))}px`;
    form.style.top = `${rect.bottom + 2}px`;
    $('autoMarkPhrase').focus();
}

function closeAutoMarkForm() {
    $('autoMarkForm').hidden = true;
    hideSuggestions();
}

// 設定を送る（mark が null なら外す）。行の単語のマークと絞り込みを描き直す（保存はまだ）
async function sendAutoMark(mark) {
    const res = await postJson('/set_auto_mark', {index: Number($('autoMarkForm').dataset.mark), mark});
    if (!res.success) return setStatus(res.message, 'error');
    state.autoMarks = res.auto_marks;
    state.autoMarks.forEach((m, i) => {  // 外した番号の絞り込み（下の ☓ も）も外す
        if (m) return;
        state.filter.auto.delete(i);
        state.without.auto.delete(i);
    });
    closeAutoMarkForm();
    paintMarkFilters();
    rerenderRows();
    applyFilter();
    setDirty(true);
}

const saveAutoMark = () => sendAutoMark({section: $('autoMarkSection').value, key: $('autoMarkKey').value,
    phrase: splitPhrases($('autoMarkPhrase').value)[0] || ''});

function applyFilter() {
    for (const tr of $('gridBody').rows) {
        tr.classList.toggle('filtered', !matchesFilter(state.byIndex.get(Number(tr.dataset.index))));
    }
    dropHiddenFromSelection();
}

// 対象の行: 押した行が選択中なら選択中の（見えている）全行、そうでなければその行だけ
function targetRows(index) {
    return state.selected.has(index) ? visibleIndexes().filter(i => state.selected.has(i)) : [index];
}

async function sendMarks(url, payload) {
    commitEdit();
    await settled();
    const res = await postJson(url, payload);
    if (!res.success) return setStatus(res.message || 'マークを付けられませんでした', 'error');
    res.rows.forEach(replaceRow);
    setDirty(true);
}

// 排他のマーク（番号）: 対象の行がみなそのマークなら外し、そうでなければ付ける
function markOne(rows, mark) {
    const all = rows.every(i => state.byIndex.get(i).mark === mark);
    return sendMarks('/set_mark', {rows, mark: all ? null : mark});
}

// 複数のマーク（番号）: 対象の行がみなその番号を持っていれば外し、そうでなければ付ける
function markMany(rows, mark) {
    const all = rows.every(i => state.byIndex.get(i).marks.includes(mark));
    return sendMarks('/set_marks', {rows, mark, on: !all});
}

function clickMark(button) {
    const rows = targetRows(Number(button.closest('tr').dataset.index));
    const mark = Number(button.dataset.mark);
    return button.dataset.kind === 'one' ? markOne(rows, mark) : markMany(rows, mark);
}

// 行の ①〜⑯: その番号の語句を行に入れる（選択中の行の中で押すと選択中の全行）。* を含む語句は、合う語句のうち件数が最も多いもの
// （サーバーが決める）。付いている行と、同じグループの別の語句がある行には入れない（付いている行だけなら何もしない）
async function putWordMark(span) {
    const i = Number(span.dataset.mark);
    const label = state.markChoices.auto[i];
    if (!state.autoMarks[i]) return setStatus(`${label} は語句が決まっていません（帯の ${label} を右クリックで決めます）`, 'warn');
    const rows = targetRows(Number(span.closest('tr').dataset.index));
    if (rows.every(r => autoMarksOf(state.byIndex.get(r)).includes(i))) return;
    commitEdit();
    await settled();
    const res = await postJson('/add_word_mark', {rows, index: i});
    if (!res.success) return setStatus(res.message, 'error');
    res.rows.forEach(replaceRow);
    const put = rows.length - res.skipped;
    if (!put) return setStatus(`${label}: 入れられる行がありませんでした（付いているか、同じグループの語句があります）`, 'warn');
    setDirty(true);
    refreshWords();
    const done = `${put} 行に「${res.phrase}」を入れました`;
    setStatus(res.skipped ? `${done}（${res.skipped} 行は、付いているか同じグループの語句があるので入れていません）` : done,
        res.skipped ? 'warn' : 'ok');
}

// キーボード（入力欄の外で）: Ctrl+A で表示中をすべて選択（マークのショートカットは無い。マークが増えて数字キーでは足りない）
function handleMarkKey(event) {
    const typing = event.target instanceof Element && event.target.closest('input, textarea, select');
    if (typing || !state.loaded || state.view !== 'images') return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {
        event.preventDefault();
        selectVisible();
    }
}

// 長押し（1秒）でマークの列を全行クリア。短く押しただけなら案内だけ出す
const HOLD_MS = 1000;  // 長押しで実行するまでの時間（ボタンの中の帯もこの時間で満タンになる）

// 長押し（1秒）で run を行う。押している間はボタンの中で帯が伸び、満タンで実行。短く押しただけなら hint を出すだけ
function holdToRun(button, run, hint) {
    button.style.setProperty('--hold-ms', `${HOLD_MS}ms`);
    let timer = null;
    const cancel = () => {
        if (timer === null) return;
        clearTimeout(timer);
        timer = null;
        button.classList.remove('holding');
        setStatus(hint);
    };
    button.addEventListener('pointerdown', () => {
        button.classList.add('holding');
        timer = setTimeout(() => {
            timer = null;
            button.classList.remove('holding');
            guarded(run)();
        }, HOLD_MS);
    });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach(name => button.addEventListener(name, cancel));
}

async function clearMarks(column) {
    const res = await postJson('/clear_marks', {column});
    if (!res.success) return setStatus(res.message, 'error');
    setDirty(true);
    await refreshTable();
    setStatus(`全行の ${markRange(state.markChoices[column === 'mark' ? 'one' : 'many'])} を消しました`, 'ok');
}

async function deselectAll() {
    state.selected = new Set();
    state.anchor = null;
    paintSelection();
    setStatus('選択を解除しました', 'ok');
}

// 一括入力のキー: 段落の確定タグ、辞書でその段落に使われたキー、（キーなし）
function bulkKeys(section) {
    const template = editKeys(section);
    const used = [...new Set(state.phrases.filter(p => p.section === section && p.key).map(p => p.key))];
    const keys = [...template, ...used.filter(k => !template.includes(k))];
    return template.length ? [...keys, ''] : ['', ...keys];
}

function fillBulkKeys() {
    // 前に選んでいたキーが新しい段落にもあれば残す（最初の1回は先頭のキー）
    const keep = $('bulkKey').options.length ? $('bulkKey').value : null;
    const keys = bulkKeys($('bulkSection').value);
    $('bulkKey').innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${k ? escapeHtml(k) : '（キーなし）'}</option>`).join('');
    if (keys.includes(keep)) $('bulkKey').value = keep;
}

// 一括入力の語句の欄の文脈: キーは選んだもの。キーなしなら文と単語
// 入力欄と同じく、選んだ範囲は無いものとして見る
function bulkContext(el) {
    const key = $('bulkKey').value;
    const caret = el.selectionStart;
    const end = el.selectionEnd;
    const value = el.value.slice(0, caret) + el.value.slice(end);
    const before = value.slice(0, caret);
    const after = value.slice(caret);
    const current = key ? splitPhrases(spacesToCommas(value)) : [];
    const base = {end, after, current, cellPhrases: key ? {[key]: current} : {}};
    if (key) {
        const segment = before.lastIndexOf(',') + 1;
        return {...base, mode: 'phrase', key, ...phraseQuery(before.slice(segment), segment)};
    }
    const lastBreak = Math.max(before.lastIndexOf(' '), before.lastIndexOf(','));
    if (lastBreak >= 0) {
        const lead = before.length - before.trimStart().length;
        return {...base, mode: 'word', key: null, query: before.slice(lastBreak + 1), queryStart: lastBreak + 1, spaces: spacesAfterWord(before),
            ...sentenceQuery(before.slice(lead), lead)};
    }
    const query = before.trimStart();
    return {...base, mode: 'keyless', key: null, query, queryStart: before.length - query.length};
}

// ---- 段落（A, B を除いた名前）・キー・語句を選ぶ欄（キーを移す・単語のマークの設定） ----

// 選択肢を入れ直す（prefer か、前に選んでいたものが新しい選択肢にもあれば残す）
function fillOptions(select, list, prefer = null, label = v => v) {
    const keep = prefer ?? select.value;
    select.innerHTML = list.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(label(v))}</option>`).join('');
    if (list.includes(keep)) select.value = keep;
}

// 単語のマークのキーの選択肢: 段落のキーと「（キーなし）」（文に合わせる）。確定タグの無い段落（action など）はキーなしが先
function wordMarkKeys(section) {
    const keys = sectionKeys(section);
    return editKeys(section).length ? [...keys, ''] : ['', ...keys];
}

// 段落の選択肢: A, B を除いた名前（表の並び）
const baseSections = () => [...new Set(state.sections.map(baseName))];

// キーの選択肢: 確定タグのキー（自動のキーは除く）と、その段落（A, B も）で使っているキー
function sectionKeys(section) {
    const used = state.phrases.filter(p => p.key && baseName(p.section) === section && !state.autoKeys.includes(p.key)).map(p => p.key);
    return [...new Set([...editKeys(section), ...used])];
}

// 語句の欄の文脈: key の語句（カンマで区切って何個でも。候補はその段落（A, B も）のそのキーの語句）。選んだ範囲は無いものとして見る
function keyPhraseContext(el, key) {
    const caret = el.selectionStart;
    const end = el.selectionEnd;
    const value = el.value.slice(0, caret) + el.value.slice(end);
    const before = value.slice(0, caret);
    const segment = before.lastIndexOf(',') + 1;
    const raw = before.slice(segment);
    const query = raw.trimStart();
    return {end, after: value.slice(caret), current: splitPhrases(value), cellPhrases: {}, mode: 'moving', key,
        query, queryStart: segment + (raw.length - query.length)};
}

const autoMarkContext = el => keyPhraseContext(el, $('autoMarkKey').value);

// ---- キーを移す（帯の「共用辞書に入れる」の右。段落（A, B も）のキーの語句を、ほかのキーへ。開いているプロジェクトの全行と共用辞書） ----

function fillMoveSections() {
    fillOptions($('moveSection'), baseSections());
    fillMoveKeys();
}

// 移す先は、移す元と同じキーも選べる（同じキーなら置換）。段落・移す元を選び直して同じキーになるときは、別のキーにする
function fillMoveKeys(reselected = false) {
    const keys = sectionKeys($('moveSection').value);
    fillOptions($('moveFrom'), keys);
    const [from, to] = [$('moveFrom').value, $('moveTo').value];
    const keep = keys.includes(to) && !(reselected && to === from);
    fillOptions($('moveTo'), keys, keep ? to : keys.find(k => k !== from) ?? from);
    showReplace();
}

// 移す先が移す元と同じキー（置換）
const replacingMove = () => Boolean($('moveFrom').value) && $('moveTo').value === $('moveFrom').value;

// 置換なら、置換後の語句の欄を出し、ボタンを「置換」にする
function showReplace() {
    $('moveNewField').hidden = !replacingMove();
    $('moveButton').textContent = replacingMove() ? '置換' : '移す';
}

const moveContext = el => keyPhraseContext(el, $('moveFrom').value);

async function movePhrases() {
    const [section, from, to] = [$('moveSection').value, $('moveFrom').value, $('moveTo').value];
    const phrases = splitPhrases($('movePhrase').value);
    commitEdit();
    await settled();
    const res = await postJson('/move_phrases', {section, from_key: from, to_key: to, phrases});
    if (!res.success) return setStatus(res.message, 'error');
    $('movePhrase').value = '';
    paintWhitespace($('movePhrase'));
    if (res.changed) {
        setDirty(true);
        await refreshTable();
    }
    applyDictionary(res.dictionary);
    const where = res.changed ? `開いているプロジェクトの ${res.changed} 行。保存はまだです` : '共用辞書だけ';
    setStatus(`${section} の ${from} の ${phrases.join('・')} を ${to} に移しました（${where}）`, 'ok');
}

// 置換: その段落（A, B も）のキーの語句を、置換後の語句 1つにする（今ある語句でもよい）。候補を選ぶと行末に付く「, 」は外して送る
async function replacePhrases() {
    const [section, key] = [$('moveSection').value, $('moveFrom').value];
    const phrases = splitPhrases($('movePhrase').value);
    const to = $('moveNew').value.replace(/[\s,]+$/, '').trim();
    commitEdit();
    await settled();
    const res = await postJson('/replace_phrases', {section, key, phrases, to_phrase: to});
    if (!res.success) return setStatus(res.message, 'error');
    for (const el of [$('movePhrase'), $('moveNew')]) {
        el.value = '';
        paintWhitespace(el);
    }
    if (res.changed) {
        setDirty(true);
        await refreshTable();
    }
    applyDictionary(res.dictionary);
    const where = res.changed ? `開いているプロジェクトの ${res.changed} 行。保存はまだです` : '共用辞書だけ';
    setStatus(`${section} の ${key} の ${phrases.join('・')} を ${to} に置き換えました（${where}）`, 'ok');
}

// ---- 動詞の形をそろえる（action の見出しの ⇄） ----

const VERB_FORM_NAMES = {progressive: 'is doing の形（girl is sitting.）', present: 'does の形（girl sits.）'};
const VERB_FORMS = {progressive: 'is doing', present: 'does'};

function verbSummary({counts, verbs, changes}) {
    if (!counts.progressive && !counts.present) return 'action に、形の分かる文がありません';
    if (verbs.some(verb => !verb.target)) return '同じ数の動詞があります。どちらにそろえますか？';
    if (!changes.length) return 'どの動詞も、1つの形にそろっています';
    return '動詞ごとに、多い方の形にそろえます';
}

// 同じ数の動詞があるとき: どちらにそろえるかのボタン（押すと、同じ数の動詞をその形にした案を出し直す）
function verbChoiceHtml() {
    return '<p class="verb-choice">' + Object.entries(VERB_FORM_NAMES).map(([target, name]) =>
        `<button type="button" data-target="${target}">${name}</button>`).join(' ') + '</p>';
}

// 動詞の件数の行: 原形・形ごとの数・そろえる形（同じ数で選んだ形には「同じ数」と添える。まだ決まらなければ出さない）
function verbHeadHtml({verb, progressive, present, target}) {
    const to = target ? ` → ${VERB_FORMS[target]}${progressive === present ? '（同じ数）' : ''}` : '';
    return `<h4 class="verb-head"><span class="verb-word">${escapeHtml(verb)}</span> ` +
        `is doing ${progressive}・does ${present}${to}</h4>`;
}

// 動詞ごとに、件数の行とその文（直す文はチェック入りで先に、迷う文はチェック無しで後に）。
// 2つの動詞が変わる文は両方の動詞に出る（data-i が同じで、チェックは共通）
function verbGroupsHtml(verbs, changes) {
    return verbs.map(verb => {
        const items = changes.map((change, i) => [change, i]).filter(([change]) => change.verbs.includes(verb.verb))
            .sort(([a], [b]) => b.sure - a.sure);
        return `<section class="verb-group">${verbHeadHtml(verb)}<ul class="verb-list">` + items.map(([change, i]) =>
            `<li class="${change.sure ? 'verb-sure' : 'verb-unsure'}"><label>` +
            `<input type="checkbox" data-i="${i}"${change.sure ? ' checked' : ''}> ` +
            (change.sure ? '' : '<span class="verb-mark">迷う</span> ') +
            `<span class="verb-name">${escapeHtml(change.name)}</span> ${escapeHtml(change.before)} → ` +
            `<b>${escapeHtml(change.after)}</b></label></li>`).join('') + '</ul></section>';
    }).join('');
}

async function openVerbForms() {
    commitEdit();
    await settled();
    if (await showVerbForms({})) $('verbDialog').showModal();
}

// 案を窓に出す（{target} を渡すと、同じ数の動詞をその形に）。同じ数の動詞の形が決まらなければ、どちらにするか聞く。出せなければ false
async function showVerbForms(payload) {
    const res = await postJson('/verb_forms', payload);
    if (!res.success) {
        setStatus(res.message, 'error');
        return false;
    }
    const ask = res.verbs.some(verb => !verb.target);  // 同じ数の動詞がある（案はまだ無い）
    state.verbChanges = res.changes;
    $('verbSummary').textContent = verbSummary(res);
    $('verbLists').innerHTML = verbGroupsHtml(res.verbs, res.changes) + (ask ? verbChoiceHtml() : '');
    $('verbApply').disabled = !res.changes.length;
    return true;
}

async function applyVerbForms() {
    const checked = new Set([...$('verbLists').querySelectorAll('input:checked')].map(box => Number(box.dataset.i)));
    const picked = [...checked].map(i => state.verbChanges[i]);
    $('verbDialog').close();
    if (!picked.length) return;
    const res = await postJson('/apply_verb_forms', {changes: picked.map(({index, before, after}) => ({index, before, after}))});
    if (!res.success) return setStatus(res.message, 'error');
    if (res.changed) {
        setDirty(true);
        await refreshTable();
    }
    setStatus(`${res.changed} 行の文の動詞をそろえました（保存はまだです）`, 'ok');
}

function openImage(name) {
    $('imageTitle').textContent = name;
    $('imageFull').src = `/image/${encodeURIComponent(name)}`;
    $('imageDialog').showModal();
}

// ---- つなぎ込み ----

function wire() {
    $('loadButton').addEventListener('click', guarded(() => loadDirectory()));
    $('renameProjectButton').addEventListener('click', openRenameDialog);
    $('renameDialog').addEventListener('close', () => {
        if ($('renameDialog').returnValue === 'rename') guarded(renameProject)();
    });
    $('browseButton').addEventListener('click', guarded(browseDirectory));
    $('imageDir').addEventListener('keydown', event => {
        if (event.key === 'Enter') guarded(loadDirectory)();
    });
    $('projectSelect').addEventListener('change', guarded(openProject));
    $('saveButton').addEventListener('click', guarded(save));
    $('removeDeadButton').addEventListener('click', guarded(removeDead));
    $('resumeButton').addEventListener('click', resume);
    $('verbApply').addEventListener('click', guarded(applyVerbForms));
    $('verbLists').addEventListener('click', event => {
        const choice = event.target.closest('.verb-choice button');
        if (choice) guarded(showVerbForms)({target: choice.dataset.target});
    });
    $('verbLists').addEventListener('change', event => {  // 2つの動詞に出る文は、どちらのチェックも同じに
        const box = event.target.closest('input[data-i]');
        if (box) $('verbLists').querySelectorAll(`input[data-i="${box.dataset.i}"]`).forEach(other => { other.checked = box.checked; });
    });
    $('freezeButton').addEventListener('click', guarded(freezeDictionary));
    $('showDead').addEventListener('change', toggleDead);
    $('sectionForm').addEventListener('submit', event => {
        event.preventDefault();
        guarded(addSection)();
    });
    $('bulkForm').addEventListener('submit', event => {
        event.preventDefault();
        guarded(bulkEdit)(event.submitter ? event.submitter.value : 'add');
    });
    withWhitespaceMarks($('bulkText'));
    // 一括入力: 「.」で終えた所（文を書き終えた所）では候補を出さない。Enter では行に足さない（追加・削除はボタンだけ。候補が出ていれば Enter で選ぶ）
    $('bulkText').addEventListener('input', () => {
        const el = $('bulkText');
        if (el.value.slice(0, el.selectionStart).endsWith('.')) hideSuggestions();
        else showSuggestions(el, $('bulkSection').value, bulkContext);
    });
    $('bulkSection').addEventListener('change', () => {
        fillBulkKeys();
        hideSuggestions();
    });
    $('bulkKey').addEventListener('change', hideSuggestions);
    $('bulkText').addEventListener('keydown', event => {
        if (!handleSuggestKey(event) && event.key === 'Enter') event.preventDefault();
    });
    $('bulkText').addEventListener('blur', hideSuggestions);
    // キャプションや辞書に入る欄は英字だけ。欄の input より先に直す（候補・高さ・印は直した文字で描く）。IME の変換中は待ち、確定したら直す
    document.addEventListener('input', event => {
        if (!event.isComposing && event.target instanceof Element && event.target.matches(ENGLISH_FIELDS)) keepEnglish(event.target);
    }, true);
    document.addEventListener('compositionend', event => {
        if (event.target instanceof Element && event.target.matches(ENGLISH_FIELDS) && keepEnglish(event.target)) {
            event.target.dispatchEvent(new Event('input'));
        }
    }, true);
    $('moveForm').addEventListener('submit', event => {
        event.preventDefault();
        guarded(replacingMove() ? replacePhrases : movePhrases)();
    });
    // 移す語句と置換後の語句の欄: 候補はどちらも、その段落のそのキーの語句
    for (const el of [$('movePhrase'), $('moveNew')]) {
        withWhitespaceMarks(el);
        el.addEventListener('input', () => showSuggestions(el, $('moveSection').value, moveContext));
        el.addEventListener('keydown', handleSuggestKey);
        el.addEventListener('blur', hideSuggestions);
    }
    $('moveSection').addEventListener('change', () => {
        fillMoveKeys(true);
        hideSuggestions();
    });
    $('moveFrom').addEventListener('change', () => {
        fillMoveKeys(true);
        hideSuggestions();
    });
    $('moveTo').addEventListener('change', showReplace);

    // 絞り込みのボタン: 押すとその印の行だけ（☓ はその印の無い行だけ）、もう一度押すと外す
    // （設定の無い単語の ①〜⑯ と、その下の ☓ は、絞り込まずに案内だけ）
    $('markFilters').addEventListener('click', event => {
        const button = event.target.closest('.filter-btn');
        if (!button) return;
        const {kind} = button.dataset;
        const mark = button.dataset.mark === 'none' ? 'none' : Number(button.dataset.mark);
        if (kind === 'auto' && mark !== 'none' && !state.autoMarks[mark]) {
            setStatus('右クリックで、段落・キー・語句を選びます（その語句のある行に付きます）');
            return;
        }
        toggleFilter(kind, mark, mark === 'none' || button.classList.contains('without'));
    });
    // 単語のマーク: 帯の ①〜⑯ を右クリックで設定の欄を開く。欄の外を押すか Esc で閉じる
    $('autoMarks').addEventListener('contextmenu', event => {
        const button = event.target.closest('.auto-mark');
        if (!button) return;
        event.preventDefault();
        openAutoMarkForm(button);
    });
    $('autoMarkForm').addEventListener('submit', event => {
        event.preventDefault();
        guarded(saveAutoMark)();
    });
    $('autoMarkClear').addEventListener('click', () => guarded(sendAutoMark)(null));
    $('autoMarkForm').addEventListener('keydown', event => {
        if (event.key === 'Escape' && !event.defaultPrevented) closeAutoMarkForm();
    });
    document.addEventListener('mousedown', event => {
        const form = $('autoMarkForm');
        if (!form.hidden && !form.contains(event.target) && !$('suggestions').contains(event.target)) closeAutoMarkForm();
    });
    $('autoMarkSection').addEventListener('change', () => {
        fillOptions($('autoMarkKey'), wordMarkKeys($('autoMarkSection').value), null, keyLabel);
        hideSuggestions();
    });
    $('autoMarkKey').addEventListener('change', hideSuggestions);
    withWhitespaceMarks($('autoMarkPhrase'));
    $('autoMarkPhrase').addEventListener('input', () => showSuggestions($('autoMarkPhrase'), $('autoMarkSection').value, autoMarkContext));
    $('autoMarkPhrase').addEventListener('keydown', handleSuggestKey);
    $('autoMarkPhrase').addEventListener('blur', hideSuggestions);
    $('selectVisibleButton').addEventListener('click', selectVisible);
    document.querySelectorAll('.clear-marks .hold').forEach(button =>
        holdToRun(button, () => clearMarks(button.dataset.column), '1秒長押しすると、全行のマークを消します'));
    holdToRun($('deselectButton'), deselectAll, '1秒長押しすると、選択を解除します');
    document.addEventListener('keydown', handleMarkKey);

    $('gridBody').addEventListener('click', event => {
        const hintToggle = event.target.closest('.hint-toggle');
        if (hintToggle) {
            toggleHint(hintToggle);
            return;
        }
        const choice = event.target.closest('.choice');
        if (choice) {
            guarded(choose)(choice);
            return;
        }
        const markButton = event.target.closest('.mark-btn');
        if (markButton) {
            guarded(clickMark)(markButton);
            return;
        }
        const wordMark = event.target.closest('.mark-auto');
        if (wordMark) {
            guarded(putWordMark)(wordMark);
            return;
        }
        const qwenButton = event.target.closest('.qwen-btn');
        if (qwenButton) {
            guarded(qwenFill)(Number(qwenButton.closest('tr').dataset.index), qwenButton.dataset.mode);
            return;
        }
        const td = event.target.closest('td');
        if (!td) return;
        const index = Number(td.closest('tr').dataset.index);
        if (td.classList.contains('thumb')) {
            if (event.target.tagName === 'IMG') openImage(td.closest('tr').dataset.name);
        } else if (td.classList.contains('meta')) {
            selectRow(index, event);
        } else if (td.classList.contains('folded')) {
            openSection(td.dataset.section, index);
        } else if (td.classList.contains('cell') && !td.querySelector('textarea')) {
            // ボタンのある欄（picture）は文字の部分だけで編集を始める（ボタンの間や余白の誤クリックで開かない）
            if (td.querySelector('.choices') && !event.target.closest('.text')) return;
            startEdit(td);
        }
    });
    // hint はフォーカスしたら全体を選ぶ（すぐコピーできるように）
    $('gridBody').addEventListener('focusin', event => {
        if (event.target.matches('td.hint textarea')) event.target.select();
    });
    $('gridHead').addEventListener('click', event => {
        const fold = event.target.closest('.fold-section');
        if (fold) toggleSection(fold.closest('th').dataset.section);
        const view = event.target.closest('.side-view');
        if (view) switchSideView(view.dataset.view);
        if (event.target.closest('.thumb-zoom')) toggleThumbZoom();
        if (event.target.closest('.verb-forms')) guarded(openVerbForms)();
        const button = event.target.closest('.remove-section');
        if (button) guarded(removeSection)(button.closest('th').dataset.section);
    });
    $('gridHead').addEventListener('dblclick', event => {
        const name = event.target.closest('.section-name:not(.fixed)');
        if (name) guarded(renameSection)(name.closest('th').dataset.section);
    });

    // 候補をクリックしても入力欄のフォーカスを外さない
    $('suggestions').addEventListener('mousedown', event => event.preventDefault());
    $('suggestions').addEventListener('click', event => {
        const li = event.target.closest('li');
        if (li && state.suggest) accept(state.suggest.items[Number(li.dataset.i)]);
    });

    $('imageDialog').addEventListener('click', event => {
        if (event.target === $('imageDialog')) $('imageDialog').close();
    });
    document.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
            event.preventDefault();
            guarded(save)();
        }
    });
    window.addEventListener('beforeunload', event => {
        if (state.dirty) {
            event.preventDefault();
            event.returnValue = '';
        }
    });
}

wire();
toggleDead();
guarded(refreshProjects)();
