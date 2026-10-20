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
    hasHints: false,      // 画像フォルダに hint（画像と同じ名前の .txt）があるか
    foldedHints: new Set(),  // hint を畳んだ画像の名前（プロジェクトごとにブラウザに覚える）
    markChoices: {one: [], many: []},  // マーク（排他 A〜D、複数 ★●▲■）
    filter: {one: '', many: ''},       // マークの絞り込み（'' はすべて、'none' はマークなし）
    viewChoices: {camera: [], pov: []},  // view のボタン（🎥 の組、👀 の人物ごとの POV）
    phrases: [],          // 辞書の語句 [{section, key, phrase, count, shared}]
    words: [],            // キーなしの文の単語 [{section, word, count, shared}]
    groups: [],           // 「1つだけ」のグループ [{key, phrases}]（共用辞書）
    defaultSections: [],  // 新規プロジェクトの段落（共用辞書の画面で語句を足す段落の候補）
    view: 'images',       // 表示中の画面（images / dictionary）
    selected: new Set(),  // 行の index
    anchor: null,         // Shift 範囲選択の起点（最後にクリックした行）
    dirty: false,
    editor: null,         // {index, section, td, el}
    suggest: null,        // {el, section, ctx, items, active, moved}
    pending: new Set(),   // 送信中の入力（保存の前に待つ）
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

// 1行を整える: 続いたカンマ（",, " ", ," ",  ,"）は1つにして、カンマの後ろは空白1つ（"a,b" "a,  b" "a , b" → "a, b"）。
// 語の間に続いた空白は1つ。値の頭と行末のカンマ・空白（候補の確定で付く ", "）は落とす
const tidyLine = line => line
    .replace(/\s*,[\s,]*/g, ', ')
    .replace(/(?<=\S)\s{2,}(?=\S)/g, ' ')
    .replace(/^(\s*-*\s*[^,:]*:)?\s*,\s*/, (match, head) => (head ? `${head} ` : ''))
    .replace(/[\s,]+$/, '');

// 保存する形に整える: 各行を整え、空行と値の無いキーの行を落とす
function tidyInput(text) {
    return text.split('\n')
        .map(tidyLine)
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

// 編集を始めたときのカーソル位置: 最初の値の無いキーの行の末尾（無ければ最後）
function firstEmptyKeyEnd(lines, keyCount) {
    let offset = 0;
    for (let i = 0; i < lines.length; i++) {
        if (i < keyCount && parseLine(lines[i]).phrases.length === 0) return offset + lines[i].length;
        offset += lines[i].length + 1;
    }
    return Math.max(0, offset - 1);
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

// 選んだ単語の後ろに付ける区切り: 行末なら ", "（欄を離れると行末のカンマは消える）。後ろに語が続けば空白、空白かカンマが続けば付けない
const wordSeparator = after => (!after.trim() ? ', ' : /^[\s,]/.test(after) ? '' : ' ');

// 入力欄のカーソル位置の文脈
// mode: phrase = キーのある行の語句 / word = キーなしの文の途中の単語（spaces は語の後ろに続くスペースの数）/ start = 行頭（キー・語句・文・単語）
function contextOf(el) {
    const value = el.value;
    const caret = el.selectionStart;
    const lineStart = value.lastIndexOf('\n', caret - 1) + 1;
    const lineEndAt = value.indexOf('\n', caret);
    const lineEnd = lineEndAt < 0 ? value.length : lineEndAt;
    const before = value.slice(lineStart, caret);
    const after = value.slice(caret, lineEnd);
    const base = {caret, after, restEmpty: after.trim() === '', current: parseLine(value.slice(lineStart, lineEnd)).phrases,
        cellPhrases: phrasesByKey(value)};
    const colon = before.indexOf(':');
    const keyPart = colon >= 0 ? before.slice(0, colon).replace(/^\s*-*\s*/, '').trim() : '';
    if (colon >= 0 && keyPart !== '' && !keyPart.includes(',')) {
        const segment = Math.max(before.lastIndexOf(','), colon) + 1;
        const raw = before.slice(segment);
        const query = raw.trimStart();
        return {...base, mode: 'phrase', key: keyPart, query, queryStart: lineStart + segment + (raw.length - query.length)};
    }
    const prefix = before.match(/^\s*-*\s*/)[0].length;
    const rest = before.slice(prefix);
    const lastBreak = Math.max(rest.lastIndexOf(' '), rest.lastIndexOf(','), rest.lastIndexOf('\t'));
    if (lastBreak >= 0) {
        return {...base, mode: 'word', key: null, query: rest.slice(lastBreak + 1), queryStart: lineStart + prefix + lastBreak + 1,
            spaces: spacesAfterWord(rest)};
    }
    return {...base, mode: 'start', key: null, query: rest, queryStart: lineStart + prefix};
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

// キーのある行: そのキーで使われた語句（打っていなくても使用回数の多い順に出す）。同じグループの語句が入っていれば出さない
function phraseCandidates(section, ctx) {
    return keepBest(state.phrases
        .filter(p => p.key === ctx.key && !ctx.current.includes(p.phrase) && !blockedIn(ctx.cellPhrases, p.key, p.phrase))
        .map(p => ({kind: 'phrase', label: p.phrase, match: p.phrase, phrase: p.phrase, count: p.count, bonus: wordBonus(p, section)})));
}

// キーなしの文の単語（1文字以上打ったとき。語の後にスペースを2つ続けたときは、打たなくても使用回数の多い順に出す）
function wordCandidates(section, ctx) {
    if (!(ctx.query || calledBySpaces(ctx))) return [];
    return keepBest(state.words.map(w => ({kind: 'word', label: w.word, match: w.word, word: w.word, count: w.count, bonus: wordBonus(w, section)})));
}

// 行頭: キー、キー付きの語句、キーなしの文、単語（1文字以上打ったときだけ）
function lineStartCandidates(section, ctx) {
    if (!ctx.query) return [];
    return keepBest([
        ...state.phrases.flatMap(p => {
            const bonus = wordBonus(p, section);
            if (!p.key) return [{kind: 'line', label: p.phrase, match: p.phrase, phrase: p.phrase, count: p.count, bonus}];
            const keyed = blockedIn(ctx.cellPhrases, p.key, p.phrase) ? []
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

const CANDIDATE_SOURCES = {phrase: phraseCandidates, word: wordCandidates, start: lineStartCandidates, keyless: keylessCandidates};

function candidates(section, ctx) {
    return CANDIDATE_SOURCES[ctx.mode](section, ctx)
        .map(item => ({...item, score: fuzzyScore(ctx.query, item.match)}))
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

function accept(item) {
    const {el, ctx} = state.suggest;
    if (item.kind === 'keyed' && el.tagName === 'TEXTAREA') {
        // 打ちかけの文字を消し、同じキーの行へ足す（無ければ行を足す）
        const without = el.value.slice(0, ctx.queryStart) + el.value.slice(ctx.caret);
        el.value = addPhrase(without.split('\n').filter(line => line.trim()).join('\n'), item.key, item.phrase);
        el.setSelectionRange(el.value.length, el.value.length);
    } else if (item.kind === 'keyed') {
        el.value = `${item.key}: ${item.phrase}`;  // 一括入力は1行
    } else {
        const text = {
            key: () => `${item.key}: `,
            phrase: () => item.phrase + (ctx.restEmpty ? ', ' : ''),
            word: () => item.word + wordSeparator(ctx.after),
            line: () => item.phrase,
        }[item.kind]();
        // 候補を出すために2つ続けたスペースは、1つにまとめる
        el.setRangeText(text, calledBySpaces(ctx) ? ctx.queryStart - 1 : ctx.queryStart, ctx.caret, 'end');
    }
    el.dispatchEvent(new Event('input'));
}

// 候補が出ているときのキー操作。Enter は打ちかけがあるか ↑↓ で選んだときだけ確定（改行を邪魔しない）
function handleSuggestKey(event) {
    const s = state.suggest;
    if (!s || s.el !== event.target) return false;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        moveActive(event.key === 'ArrowDown' ? 1 : -1);
    } else if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey && (s.ctx.query || s.moved))) {
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
    if (groupsChanged && state.loaded) rerenderRows();
    document.dispatchEvent(new CustomEvent('pictag:dictionary'));
}

// ---- 表 ----

function headHtml() {
    return [
        '<th>サムネイル</th>',
        '<th title="キャプションのトークン数 / 上限">token</th>',
        '<th>マーク</th>',
        ...state.sections.map(s => (state.fixedSections.includes(s)
            ? `<th data-section="${escapeHtml(s)}"><span class="section-name fixed">${escapeHtml(s)}</span></th>`
            : `<th data-section="${escapeHtml(s)}"><span class="section-name" title="ダブルクリックで改名">${escapeHtml(s)}</span>` +
              `<button type="button" class="remove-section" title="この段落を表から外す" aria-label="${escapeHtml(s)} を外す">×</button></th>`)),
        ...(state.hasHints ? ['<th class="hint-head" title="画像と同じ名前の .txt（読むだけ。保存には影響しない）">hint</th>'] : []),
    ].join('');
}

// マークの欄: 縦長の 2 列 × 4 行。左の列が排他（A〜D のどれか1つ）、右の列が複数（★●▲■）
function marksHtml(row) {
    const button = (kind, mark, on) =>
        `<button type="button" class="mark-btn${on ? ' on' : ''}" data-kind="${kind}" data-mark="${mark}">${mark}</button>`;
    const one = state.markChoices.one.map(m => button('one', m, row.mark === m)).join('');
    const many = state.markChoices.many.map(m => button('many', m, (row.marks || '').includes(m))).join('');
    return `<td class="marks"><div class="mark-grid">${one}${many}</div></td>`;
}

// マークの絞り込みに合うか
function matchesFilter(row) {
    const {one, many} = state.filter;
    const okOne = !one || (one === 'none' ? !row.mark : row.mark === one);
    const okMany = !many || (many === 'none' ? !row.marks : (row.marks || '').includes(many));
    return okOne && okMany;
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

// hint の高さを中身に合わせる（CSS の field-sizing が効かないブラウザ向け。先に全部読んでから書き、描き直しを1回にする）
function fitHints(root) {
    if (!root || CSS.supports('field-sizing', 'content')) return;
    const areas = [...root.querySelectorAll('td.hint textarea')];
    const heights = areas.map(el => el.scrollHeight);
    areas.forEach((el, i) => {
        if (heights[i]) el.style.height = `${heights[i] + 2}px`;  // 見えていない（0）ときは触らない
    });
}

const foldedHintsKey = () => `pictag:folded-hints:${state.projectName}`;

function loadFoldedHints() {
    try {
        state.foldedHints = new Set(JSON.parse(localStorage.getItem(foldedHintsKey()) || '[]'));
    } catch {
        state.foldedHints = new Set();
    }
}

function saveFoldedHints() {
    try {
        localStorage.setItem(foldedHintsKey(), JSON.stringify([...state.foldedHints]));
    } catch {
        // 覚えられなくても、畳む・開くはできる
    }
}

function toggleHint(button) {
    const tr = button.closest('tr');
    const name = tr.dataset.name;
    if (state.foldedHints.has(name)) state.foldedHints.delete(name);
    else state.foldedHints.add(name);
    saveFoldedHints();
    tr.querySelector('td.hint').outerHTML = hintHtml(state.byIndex.get(Number(tr.dataset.index)));
    fitHints(tr);
}

// token の欄: トークン数と上限を2行で（ファイル名はサムネイルの title）。クリックで行を選ぶ
function metaHtml(row) {
    const known = row.tokens !== null && row.tokens !== undefined;
    const over = known && row.tokens > state.tokenLimit;
    return `<div class="tokens${over ? ' over' : ''}" title="${escapeHtml(row.caption || '（空）')}">${known ? row.tokens : '—'}\n/ ${state.tokenLimit}</div>`;
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
        `${state.viewChoices.pov.map(c => button(c.phrase, [c.emoji, c.label].filter(Boolean).join(' '), 'pov', [c.tone, c.label ? '' : 'icon'])).join('')}</span>`;
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

// サムネイルは正方形で、picture の欄の中身の高さ（見えている行でいちばん低いもの）に合わせる。表を描くたびに測る
function fitThumbnails() {
    const heights = [...$('gridBody').querySelectorAll('td.cell[data-section="picture"]')]
        .filter(td => td.getBoundingClientRect().height > 0)
        .map(td => [...td.children].reduce((sum, el) => sum + el.getBoundingClientRect().height + parseFloat(getComputedStyle(el).marginTop), 0));
    if (heights.length) $('grid').style.setProperty('--thumb-size', `${Math.floor(Math.min(...heights))}px`);
}

const choiceGroup = group => (group === 'pov' ? state.viewChoices.pov.map(c => c.phrase) : state.viewChoices.camera[Number(group.slice(6))]);

// 欄の表示: 確定タグのキーを並びどおりに出し、値の無いキーは薄く、自動のキー（characters）は自動の値で出す
// 同じグループの語句が2つ以上ある行には ⚠（CSS）
function cellHtml(section, row) {
    const keys = templateKeys(section);
    const byKey = phrasesByKey(row.texts[section]);
    const lines = mergeTemplate(row.texts[section] || '', keys).map(line => {
        const {key, phrases} = parseLine(line);
        if (state.autoKeys.includes(key)) {
            const value = row.characters || '';
            return `<div class="ln auto${value ? '' : ' empty'}" title="自動">${escapeHtml(`${key}:${value ? ` ${value}` : ''}`)}</div>`;
        }
        const conflict = key ? conflictOf(key, byKey[key] || []) : null;
        const classes = ['ln', phrases.length === 0 ? 'empty' : '', conflict ? 'conflict' : ''].filter(Boolean).join(' ');
        const title = conflict ? ` title="${escapeHtml(`1つだけのグループ: ${conflict.phrases.join(' / ')}`)}"` : '';
        return `<div class="${classes}"${title}>${escapeHtml(line.trimEnd())}</div>`;
    });
    return `<div class="text">${lines.join('')}</div>${keys.includes('view') ? choicesHtml(row) : ''}`;
}

function rowHtml(row) {
    const name = row['サムネイル'];
    const classes = [row.is_dead ? 'dead' : '', state.selected.has(row.index) ? 'selected' : '',
        matchesFilter(row) ? '' : 'filtered'].filter(Boolean).join(' ');
    const cells = state.sections.map(s => `<td class="cell" data-section="${escapeHtml(s)}">${cellHtml(s, row)}</td>`).join('');
    return `<tr data-index="${row.index}" data-name="${escapeHtml(name)}" class="${classes}">` +
        `<td class="thumb"><img loading="lazy" src="/thumbnail/${encodeURIComponent(name)}" alt="" title="${escapeHtml(name)}"></td>` +
        `<td class="meta">${metaHtml(row)}</td>${marksHtml(row)}${cells}${state.hasHints ? hintHtml(row) : ''}</tr>`;
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
    $('emptyNote').hidden = state.loaded;
    $('tools').hidden = !state.loaded || state.view !== 'images';
    $('markTools').hidden = !state.loaded || state.view !== 'images';
    setDirty(state.dirty);
    updateSelectionInfo();
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
    state.templates = body.templates;
    state.fixedSections = body.fixed_sections;
    state.autoKeys = body.auto_keys;
    state.othersSection = body.others_section;
    state.viewChoices = body.view_choices;
    if (state.markChoices.one.length === 0) fillMarkFilters(body.mark_choices);
    state.markChoices = body.mark_choices;
    state.selected = new Set([...state.selected].filter(i => state.byIndex.has(i)));
    if (!state.byIndex.has(state.anchor)) state.anchor = null;
    state.loaded = true;
    renderTable();
    refreshWords();
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
    const keys = editKeys(section);
    const lines = mergeTemplate(state.byIndex.get(index).texts[section] || '', keys);
    const el = document.createElement('textarea');
    el.value = lines.join('\n');
    td.replaceChildren(withWhitespaceMarks(el));
    state.editor = {index, section, td, el};
    el.addEventListener('input', () => { autosize(el); showSuggestions(el, section); });
    el.addEventListener('keydown', event => {
        if (handleSuggestKey(event)) return;
        if (event.key === 'Escape' || (event.key === 'Enter' && event.ctrlKey)) {
            event.preventDefault();
            commitEdit();
        }
    });
    el.addEventListener('keyup', event => {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) showSuggestions(el, section);
    });
    el.addEventListener('click', () => showSuggestions(el, section));
    el.addEventListener('blur', () => commitEdit());
    autosize(el);
    el.focus();
    const caret = firstEmptyKeyEnd(lines, keys.length);
    el.setSelectionRange(caret, caret);
}

function commitEdit() {
    const editor = state.editor;
    if (!editor) return;
    state.editor = null;
    hideSuggestions();
    const row = state.byIndex.get(editor.index);
    const text = tidyInput(editor.el.value);
    const changed = text !== (row.texts[editor.section] || '');
    row.texts[editor.section] = text;
    editor.td.innerHTML = cellHtml(editor.section, row);
    if (changed) track(sendText(row, editor.section, text)).catch(e => setStatus(String(e.message || e), 'error'));
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
    const tr = rowElement(row.index);
    if (tr) {
        tr.querySelector('td.meta').innerHTML = metaHtml(row);
        // 人物の段落を書き換えると characters が変わるので picture の欄を描き直す（編集中なら触らない）
        const picture = tr.querySelector('td.cell[data-section="picture"]');
        if (picture && !picture.querySelector('textarea')) picture.innerHTML = cellHtml('picture', row);
    }
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
    // 行を選んでいる間は、キーの案内の代わりに一括入力を出す
    $('bulkForm').hidden = state.selected.size === 0;
    $('keyHelp').hidden = state.selected.size > 0;
}

// ---- 操作 ----

async function bulkEdit(op) {
    commitEdit();
    const rows = visibleIndexes().filter(i => state.selected.has(i));
    const phrases = $('bulkText').value.trim();
    const key = $('bulkKey').value;
    if (!rows.length) return setStatus('行を選んでください', 'error');
    if (!phrases) return setStatus('語句を入力してください', 'error');
    const text = key ? `${key}: ${phrases}` : phrases;
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
    const name = window.prompt('新しい段落名', old);
    if (name === null || name.trim() === old) return;
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

async function opened(name) {
    state.projectName = name;
    loadFoldedHints();
    state.selected = new Set();
    state.anchor = null;
    state.dirty = false;
    await refreshTable();
    await refreshProjects();
    setStatus(`「${name}」を開きました（${state.rows.length} 枚）`, 'ok');
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
    await opened(name);
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
    await opened(dir.replace(/["']/g, '').replace(/[\\/]+$/, '').split(/[\\/]/).pop());
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

async function save() {
    if (!state.loaded) return;
    commitEdit();
    await settled();
    const res = await postJson('/save_data');
    if (!res.success) return setStatus(res.message, 'error');
    state.dirty = false;
    await refreshTable();
    await refreshProjects();
    setStatus('保存しました', 'ok');
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

function fillMarkFilters(choices) {
    const options = (all, marks) => [`<option value="">${all}</option>`,
        ...marks.map(m => `<option value="${m}">${m}</option>`), '<option value="none">なし</option>'].join('');
    $('filterOne').innerHTML = options('排他: すべて', choices.one);
    $('filterMany').innerHTML = options('複数: すべて', choices.many);
}

function applyFilter() {
    state.filter = {one: $('filterOne').value, many: $('filterMany').value};
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

// 排他のマーク: 対象の行がみなそのマークなら外し、そうでなければ付ける
function markOne(rows, mark) {
    const all = rows.every(i => state.byIndex.get(i).mark === mark);
    return sendMarks('/set_mark', {rows, mark: all ? '' : mark});
}

// 複数のマーク: 対象の行がみなその記号を持っていれば外し、そうでなければ付ける
function markMany(rows, mark) {
    const all = rows.every(i => (state.byIndex.get(i).marks || '').includes(mark));
    return sendMarks('/set_marks', {rows, mark, on: !all});
}

function clickMark(button) {
    const rows = targetRows(Number(button.closest('tr').dataset.index));
    return button.dataset.kind === 'one' ? markOne(rows, button.dataset.mark) : markMany(rows, button.dataset.mark);
}

// キーボード（入力欄の外で）: 1〜4 で A〜D、0 で外す、5〜8 で ★●▲■。Ctrl+A で表示中をすべて選択
function handleMarkKey(event) {
    const typing = event.target instanceof Element && event.target.closest('input, textarea, select');
    if (typing || !state.loaded || state.view !== 'images') return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {
        event.preventDefault();
        selectVisible();
        return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey || !/^[0-8]$/.test(event.key)) return;
    const rows = visibleIndexes().filter(i => state.selected.has(i));
    if (!rows.length) return setStatus('先に行を選んでください', 'error');
    event.preventDefault();
    const n = Number(event.key);
    if (n === 0) guarded(sendMarks)('/set_mark', {rows, mark: ''});
    else if (n <= 4) guarded(markOne)(rows, state.markChoices.one[n - 1]);
    else guarded(markMany)(rows, state.markChoices.many[n - 5]);
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
    setStatus(`全行の ${column === 'mark' ? 'A〜D' : '★●▲■'} を消しました`, 'ok');
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
function bulkContext(el) {
    const key = $('bulkKey').value;
    const value = el.value;
    const caret = el.selectionStart;
    const before = value.slice(0, caret);
    const after = value.slice(caret);
    const current = key ? splitPhrases(value) : [];
    const base = {caret, after, restEmpty: after.trim() === '', current, cellPhrases: key ? {[key]: current} : {}};
    if (key) {
        const segment = before.lastIndexOf(',') + 1;
        const raw = before.slice(segment);
        const query = raw.trimStart();
        return {...base, mode: 'phrase', key, query, queryStart: segment + (raw.length - query.length)};
    }
    const lastBreak = Math.max(before.lastIndexOf(' '), before.lastIndexOf(','));
    if (lastBreak >= 0) {
        return {...base, mode: 'word', key: null, query: before.slice(lastBreak + 1), queryStart: lastBreak + 1, spaces: spacesAfterWord(before)};
    }
    const query = before.trimStart();
    return {...base, mode: 'keyless', key: null, query, queryStart: before.length - query.length};
}

function openImage(name) {
    $('imageTitle').textContent = name;
    $('imageFull').src = `/image/${encodeURIComponent(name)}`;
    $('imageDialog').showModal();
}

// ---- つなぎ込み ----

function wire() {
    $('loadButton').addEventListener('click', guarded(() => loadDirectory()));
    $('browseButton').addEventListener('click', guarded(browseDirectory));
    $('imageDir').addEventListener('keydown', event => {
        if (event.key === 'Enter') guarded(loadDirectory)();
    });
    $('projectSelect').addEventListener('change', guarded(openProject));
    $('saveButton').addEventListener('click', guarded(save));
    $('removeDeadButton').addEventListener('click', guarded(removeDead));
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
    $('bulkText').addEventListener('input', () => showSuggestions($('bulkText'), $('bulkSection').value, bulkContext));
    $('bulkSection').addEventListener('change', () => {
        fillBulkKeys();
        hideSuggestions();
    });
    $('bulkKey').addEventListener('change', hideSuggestions);
    $('bulkText').addEventListener('keydown', handleSuggestKey);
    $('bulkText').addEventListener('blur', hideSuggestions);

    $('filterOne').addEventListener('change', applyFilter);
    $('filterMany').addEventListener('change', applyFilter);
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
        const td = event.target.closest('td');
        if (!td) return;
        const index = Number(td.closest('tr').dataset.index);
        if (td.classList.contains('thumb')) {
            if (event.target.tagName === 'IMG') openImage(td.closest('tr').dataset.name);
        } else if (td.classList.contains('meta')) {
            selectRow(index, event);
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
