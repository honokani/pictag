// pictag 共用辞書の画面（タブで切り替え）
// 一覧は「キー: 語句」で1行（段落をまたいでまとめる）と、キーなしの文の単語。登録・削除・改名・kind
// control.js の state・通信・表示の小物を使う
'use strict';

const dict = {
    rows: [],              // 表示中の行（絞り込み・並べ替えのあと）
    selected: new Set(),   // 行の id
    anchor: null,          // Shift 範囲選択の起点（最後にクリックした行）
    focus: null,           // 最後に選んだ行の id（右に画像を出す行）
    sort: null,            // 見出しの ▲▼ の並べ替え {by: key / kind / text, dir: 1 / -1}（無ければ元の並び）
    renaming: null,        // 改名中の行の id
    scroll: 0,             // 画像の画面のスクロール位置（戻ったときに戻す）
    exact: false,          // 検索ボタンか Enter で、文字どおりの一致にしたか（また打つと、あいまいに戻る）
    preview: null,         // 簡易表示に出している画像 {project, name}（別の語句を選んでも残す）
};

const GROUP_COLORS = 6;

// ---- 一覧の行 ----

function dictionaryRows() {
    const rows = new Map();
    const add = (id, base, entry) => {
        const row = rows.get(id) || {...base, id, sections: [], count: 0, here: 0, shared: false};
        const section = baseName(entry.section);
        if (!row.sections.includes(section)) row.sections.push(section);
        row.count += entry.count;
        row.here += entry.here || 0;
        row.shared = row.shared || entry.shared;
        rows.set(id, row);
    };
    state.phrases.forEach(p => add(JSON.stringify(['phrase', p.key, p.phrase]), {kind: 'phrase', key: p.key, text: p.phrase}, p));
    state.words.forEach(w => add(JSON.stringify(['word', w.word]), {kind: 'word', key: null, text: w.word}, w));
    return [...rows.values()].sort(compareRows);
}

// 並び: 確定タグのキー（picture → 人物の順）、ほかのキー、キーなしの文、単語。その中は語句の abc 順
function keyRank(row) {
    if (row.kind === 'word') return [3, ''];
    if (!row.key) return [2, ''];
    const at = templateOrder().indexOf(row.key);
    return at >= 0 ? [0, String(at).padStart(3, '0')] : [1, row.key];
}

// 確定タグのキーの並び: 組を順に重ね、まだ無いキーは同じ組の1つ前のキーの次に入れる（subject と girl → looks, face, clothes, body）
function templateOrder() {
    return Object.values(state.templates).reduce((order, keys) => keys.reduce((acc, key, i) => {
        if (acc.includes(key)) return acc;
        const at = i > 0 ? acc.indexOf(keys[i - 1]) + 1 : acc.length;
        return [...acc.slice(0, at), key, ...acc.slice(at)];
    }, order), []);
}

function compareRows(a, b) {
    const [rankA, keyA] = keyRank(a);
    const [rankB, keyB] = keyRank(b);
    return rankA - rankB || keyA.localeCompare(keyB) || a.text.localeCompare(b.text, undefined, {sensitivity: 'base'});
}

// kind の名前: キーの kind（.looks。キーなしの文は .action など、単語は .（単語））と、kind の印（._face など）
const kindText = row => [`.${dictKeyLabel(row)}`, rowKind(row) >= 0 ? groupLabel(state.groups[rowKind(row)], rowKind(row)) : ''].join(' ');

// 検索で見る文字: 語句と kind の名前
const searchText = row => `${row.text} ${kindText(row)}`;

// 語が合うか: 打っている間はあいまい（fzf と同じ）、検索ボタンか Enter のあとは文字どおり（大文字と小文字は区別しない）
const termMatches = (term, text) => (dict.exact ? text.toLowerCase().includes(term.toLowerCase()) : fuzzyScore(term, text) !== null);

// 絞り込み: 検索の欄の、空白で区切った語の全部が合う行（「以外を表示」なら合わない行）。「.」で始まる語は kind の名前とだけ、
// ほかの語は語句と kind の名前のどれかと比べる。共用辞書に入っているかでも絞る
function matchesDictFilter(row) {
    const terms = $('dictFilter').value.trim().split(/\s+/).filter(Boolean);
    const hit = terms.every(term => termMatches(term, term.startsWith('.') ? kindText(row) : searchText(row)));
    const shared = $('dictShared').value;
    return (!terms.length || hit === ($('dictFilterMode').value === 'in')) && (!shared || (shared === 'in') === row.shared);
}

// 検索ボタンか Enter: 打った語がそのまま入っている行だけに絞る（また打つと、あいまいに戻る）
function searchExactly() {
    dict.exact = true;
    renderDictionary();
}

// リセット: 検索の文字を消し、「対象を表示」と「共用辞書: すべて」に戻す
function resetDictFilter() {
    $('dictFilter').value = '';
    $('dictFilterMode').value = 'in';
    $('dictShared').value = '';
    dict.exact = false;
    renderDictionary();
}

// 並べ替え（見出しの ▲▼）の比べるもの: キーは表示の名前、kind は印の文字（kind の無い行は向きによらず後ろ）、語句、
// 回数は開いているプロジェクトの回数（開く前は合計）と、ほかのプロジェクトの回数（開く前は合計。欄の書き方と同じ）。同じなら元の並び
const SORT_TEXT = {
    key: row => dictKeyLabel(row),
    kind: row => (rowKind(row) < 0 ? null : groupLabel(state.groups[rowKind(row)], rowKind(row))),
    text: row => row.text,
    here: row => (state.projectName ? row.here : row.count),
    others: row => (state.projectName ? row.count - row.here : row.count),
};

const compareSortKeys = (a, b) => (typeof a === 'number' ? a - b : a.localeCompare(b, undefined, {sensitivity: 'base'}));

function sortedRows(rows) {
    if (!dict.sort) return rows;
    const text = SORT_TEXT[dict.sort.by];
    return rows.map((row, i) => ({row, i, t: text(row)}))
        .sort((a, b) => (a.t === null) - (b.t === null)
            || (a.t === null ? 0 : dict.sort.dir * compareSortKeys(a.t, b.t)) || a.i - b.i)
        .map(x => x.row);
}

// 語句の入っている kind の位置（一覧か前後の決まりで。無ければ -1）
const groupIndex = (key, phrase) => state.groups.findIndex(g => inGroup(g, key, phrase));
const rowKind = row => (row.kind === 'phrase' && row.key ? groupIndex(row.key, row.text) : -1);

// kind の印（表の印はダブルクリックで名前・前後の決まり・排他制限を変える）
function groupBadge(i, dblclick = true) {
    const g = state.groups[i];
    return `<span class="group-badge g${i % GROUP_COLORS}" title="${escapeHtml(`${groupTitle(g, i)}${dblclick ? '（ダブルクリックで変える）' : ''}`)}">` +
        `${escapeHtml(groupLabel(g, i))}</span>`;
}

// キーの列: 単語は（単語）、キーなしの文は action だけで使っていれば action、ほかは（キーなし）
const dictKeyLabel = row => (row.kind === 'word' ? '（単語）' : row.key || (row.sections.every(s => s === 'action') ? 'action' : '（キーなし）'));

// 回数: プロジェクトを開いているときは「開いているプロジェクトの回数（ほかのプロジェクトの回数）」（候補と同じ書き方）、開く前は合計
const countLabel = row => (state.projectName ? `${row.here}（${row.count - row.here}）` : String(row.count));

function dictRowHtml(row) {
    const group = rowKind(row);
    const key = dictKeyLabel(row);
    const text = dict.renaming === row.id
        ? `<input type="text" class="rename-input" value="${escapeHtml(row.text)}" aria-label="新しい名前" title="Enter で決定、Esc でやめる">`
        : escapeHtml(row.text);
    const on = dict.selected.has(row.id);
    return `<tr data-id="${escapeHtml(row.id)}" data-kind="${row.kind}" data-key="${escapeHtml(row.key || '')}" ` +
        `data-text="${escapeHtml(row.text)}"${on ? ' class="selected"' : ''}>` +
        `<td><input type="checkbox" class="dict-check"${on ? ' checked' : ''} aria-label="選ぶ"></td>` +
        `<td class="dict-sections">${escapeHtml(row.sections.join(', '))}</td>` +
        `<td class="dict-key">${escapeHtml(key)}</td>` +
        `<td class="dict-group">${group >= 0 ? groupBadge(group) : ''}</td>` +
        `<td class="dict-phrase">${text}</td>` +
        `<td class="num">${countLabel(row)}</td>` +
        `<td class="dict-shared">${row.shared ? '<span class="shared-mark" title="共用辞書に入っている">✓</span>' : ''}</td>` +
        `<td>${row.kind === 'phrase' ? '<button type="button" class="dict-rename">改名</button>' : ''}</td></tr>`;
}

// 選択肢を入れ替える（前に選んでいた値があれば残す）
function keepOptions(select, options) {
    const keep = select.options.length ? select.value : null;
    select.innerHTML = options.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('');
    if (options.some(([value]) => value === keep)) select.value = keep;
}

// 見出しの ▲▼ のうち、今の並べ替えのボタンを目立たせる
function paintSortButtons() {
    for (const button of document.querySelectorAll('#dictGrid button.sort')) {
        const on = Boolean(dict.sort) && dict.sort.by === button.dataset.sort && dict.sort.dir === Number(button.dataset.dir);
        button.classList.toggle('on', on);
        button.setAttribute('aria-pressed', String(on));
    }
}

// 手で足す語句の段落とキー（一括入力と同じく 段落 → キー）
function fillDictAdd() {
    const sections = [...new Set([...state.defaultSections, ...state.sections, ...state.phrases.map(p => p.section)])];
    keepOptions($('dictAddSection'), sections.map(s => [s, s]));
    keepOptions($('dictAddKey'), bulkKeys($('dictAddSection').value).map(k => [k, k || '（キーなし）']));
}

function renderDictionary() {
    const all = dictionaryRows();
    fillDictAdd();
    dict.rows = sortedRows(all.filter(matchesDictFilter));
    const visible = new Set(dict.rows.map(r => r.id));
    dict.selected = new Set([...dict.selected].filter(id => visible.has(id)));  // 見えなくなった行は選択から外す
    if (!dict.selected.has(dict.focus)) dict.focus = [...dict.selected].pop() ?? null;
    $('dictBody').innerHTML = dict.rows.map(dictRowHtml).join('');
    $('dictCount').textContent = `${dict.rows.length} 件`;
    $('dictEmpty').hidden = dict.rows.length > 0;
    paintDictSelection();
    renderDictKinds();
}

// ---- 選択（クリック: その行だけ / Ctrl と左端のチェック: 足し引き / Shift: 最後にクリックした行からの範囲を足す） ----

// 選んである行をふつうにクリックしたときは、選択はそのままで、最後に選んだ行（dict.focus。右に画像を出す行）だけを変える
function clickDictRow(tr, event) {
    const id = tr.dataset.id;
    const order = dict.rows.map(r => r.id);
    const from = order.indexOf(dict.anchor);
    const to = order.indexOf(id);
    if (event.shiftKey && from >= 0 && to >= 0) {
        order.slice(Math.min(from, to), Math.max(from, to) + 1).forEach(i => dict.selected.add(i));
    } else if (event.ctrlKey || event.metaKey || event.target.closest('.dict-check')) {
        if (dict.selected.has(id)) dict.selected.delete(id);
        else dict.selected.add(id);
    } else if (!dict.selected.has(id)) {
        dict.selected = new Set([id]);
    }
    dict.anchor = id;
    dict.focus = dict.selected.has(id) ? id : [...dict.selected].pop() ?? null;
    paintDictSelection();
}

function paintDictSelection() {
    for (const tr of $('dictBody').rows) {
        const on = dict.selected.has(tr.dataset.id);
        tr.classList.toggle('selected', on);
        tr.querySelector('.dict-check').checked = on;
    }
    const count = dict.selected.size;
    $('dictSelInfo').textContent = `選択 ${count} 件`;
    $('dictSelForm').hidden = count === 0;
    $('dictHelp').hidden = count > 0;
    $('dictAll').checked = count > 0 && dict.rows.every(r => dict.selected.has(r.id));
    renderDictImages();
}

// ---- 右半分（上: 最後に選んだ語句の画像 / 下: 全部の kind） ----

const WORD_CHARS = /[^\s,.;:!?"()\[\]]+/g;  // 文の単語（words.py の WORD と同じ）

// 画像の行が、辞書の行（キーのある語句・キーなしの文・単語）を使っているか（辞書の行の段落と同じ種類の段落で）
function usesEntry(r, entry) {
    return Object.entries(r.texts || {}).some(([section, text]) => entry.sections.includes(baseName(section))
        && (text || '').split('\n').map(parseLine).some(({key, phrases}) => (entry.kind === 'word'
            ? !key && phrases.some(p => (p.match(WORD_CHARS) || []).includes(entry.text))
            : key === (entry.key || '') && phrases.includes(entry.text))));
}

// 右上: 最後に選んだ行（dict.focus）の語句を使っている、開いているプロジェクトの画像（表の並び。クリックで下の簡易表示に、
// ダブルクリックで画像の画面のその行へ）
function renderDictImages() {
    const entry = dict.rows.find(r => r.id === dict.focus);
    const rows = entry && state.loaded ? state.rows.filter(r => usesEntry(r, entry)) : [];
    $('dictImagesNote').textContent = !entry ? '語句の行を選ぶと、開いているプロジェクトでその語句を使っている画像を出します'
        : !state.loaded ? 'プロジェクトを開くと、その語句を使っている画像を出します'
        : `${dictKeyLabel(entry)}: ${entry.text} を使っている画像（${rows.length} 枚。クリックで下に画像の画面の行を出し、ダブルクリックで画像の画面のその行へ）`;
    $('dictImageList').innerHTML = rows.map(r => `<button type="button" class="dict-thumb${r.is_dead ? ' dead' : ''}" data-index="${r.index}" ` +
        `title="${escapeHtml(r['サムネイル'])}"><img loading="lazy" src="/thumbnail/${encodeURIComponent(r['サムネイル'])}" alt=""></button>`).join('');
    renderRowView();
}

const GRID_VARS = ['--picture-width', '--action-extra', '--thumb-size', '--lend'];  // 画像の画面の列の幅（control.js が #grid に置く）

// 右の真ん中（簡易表示）: 右上でクリックした画像の、画像の画面の行のサムネイルと段落の欄をそのまま（token・🤖・マーク・hint の列は
// 出さない。列の幅も画像の画面と同じ）。見るだけで、サムネイルのクリックで画像の画面のその行へ。別の語句を選んでも残し、
// ほかのプロジェクトを開いたら出さない
function renderRowView() {
    const shown = dict.preview && dict.preview.project === state.projectName
        ? state.rows.find(r => r['サムネイル'] === dict.preview.name) : null;
    const table = $('dictRowTable');
    $('dictRowNote').textContent = shown ? `${shown['サムネイル']}（サムネイルのクリックで、画像の画面のその行へ）`
        : '右上の画像をクリックすると、画像の画面のその行（サムネイルと段落の欄）をここに出します';
    table.hidden = !shown;
    if (!shown) return;
    GRID_VARS.forEach(name => table.style.setProperty(name, $('grid').style.getPropertyValue(name)));
    table.tBodies[0].innerHTML = rowHtml(shown);
    table.tHead.rows[0].innerHTML = headHtml();
    const tr = table.tBodies[0].rows[0];
    // 見出しと行は同じ並び（サムネイル・token・🤖・マーク・段落…・hint）なので、行で残す列を決めて、見出しも同じ位置を残す
    const keep = [...tr.cells].map(td => td.classList.contains('thumb') || td.classList.contains('cell'));
    [...table.tHead.rows[0].cells].forEach((th, i) => keep[i] || th.remove());
    [...tr.cells].forEach((td, i) => keep[i] || td.remove());
    tr.classList.remove('filtered', 'selected');  // 画像の画面の絞り込みと選択には左右されない
}

// 右上の画像のクリック: 簡易表示に出す
function previewImage(index) {
    const row = state.rows.find(r => r.index === index);
    dict.preview = row ? {project: state.projectName, name: row['サムネイル']} : null;
    renderRowView();
}

// 画像の画面へ切り替えて、その行を列の見出しのすぐ下に見せる（絞り込みなどで隠れていれば、📍 と同じく知らせるだけ）
function jumpToImage(index) {
    showView('images');
    const tr = rowElement(index);
    if (!tr || tr.getBoundingClientRect().height === 0) {
        const row = state.rows.find(r => r.index === index);
        return setStatus(`${row ? row['サムネイル'] : '画像'} は、絞り込みか「削除済み画像を表示」で隠れています`, 'warn');
    }
    showRowBelowHead(index, 0);
}

// kind の仲間の語句: 一覧の語句と、前後の決まりに合う辞書の語句（同じキー）
const kindMembers = g => [...new Set([...g.phrases, ...state.phrases.filter(p => p.key === g.key && followsRule(g, p.phrase)).map(p => p.phrase)])];

// 右下: 全部の kind（印・キー・排他制限・改名・消すと、仲間の語句。語句をクリックすると左の表のその行へ。消すは1秒長押し）
function renderDictKinds() {
    $('dictKindsNote').textContent = state.groups.length ? `kind ${state.groups.length} 件（語句をクリックすると、左の表のその行へ）`
        : 'kind はまだありません（左の表で語句を選び、「kindを付与する」）';
    $('dictKindList').innerHTML = state.groups.map((g, i) => `<div class="dict-kind" data-i="${i}">${groupBadge(i, false)} ` +
        `<span class="key-help">${escapeHtml(g.key)}</span> <label class="key-help"><input type="checkbox" class="kind-exclusive"` +
        `${exclusiveKind(g) ? ' checked' : ''}> 排他制限</label> <button type="button" class="kind-edit">改名</button> ` +
        `<button type="button" class="kind-delete hold" title="1秒長押しで、この kind を消す（語句はそのまま）">消す</button>` +
        `<div class="kind-members">${kindMembers(g).map(p => kindMemberHtml(g, p)).join('')}</div></div>`).join('');
    $('dictKindList').querySelectorAll('.kind-delete').forEach(button => holdToRun(button,
        () => deleteKind(Number(button.closest('.dict-kind').dataset.i)), '1秒長押しすると、この kind を消します（語句はそのまま）'));
}

// kind の仲間の語句のボタン。suffix・prefix の決まりに合う語句は色を付ける（合わないが付与した語句は白のまま）
function kindMemberHtml(g, phrase) {
    const rule = followsRule(g, phrase);
    const title = rule ? ` title="${escapeHtml(`決まり（「${g.name}」で${g.affix === 'suffix' ? '終わる' : '始まる'}）に合う語句`)}"` : '';
    return `<button type="button" class="kind-member${rule ? ' rule' : ''}" data-key="${escapeHtml(g.key)}" ` +
        `data-text="${escapeHtml(phrase)}"${title}>${escapeHtml(phrase)}</button>`;
}

// 左の表のその語句の行へ（検索で見えなければ検索を外す）。その行だけを選ぶので、右上の画像もその語句の
function jumpToEntry(key, text) {
    const id = JSON.stringify(['phrase', key, text]);
    if (!dict.rows.some(r => r.id === id)) resetDictFilter();
    const tr = [...$('dictBody').rows].find(row => row.dataset.id === id);
    if (!tr) return setStatus(`${key}: ${text} は、どこにも使っていない語句です（表にありません）`, 'warn');
    dict.selected = new Set([id]);
    dict.anchor = dict.focus = id;
    paintDictSelection();
    tr.scrollIntoView({block: 'center'});
}

const selectedDictRows = () => dict.rows.filter(r => dict.selected.has(r.id));
const phrasePairs = rows => rows.filter(r => r.kind === 'phrase').map(r => ({key: r.key, phrase: r.text}));
const wordList = rows => rows.filter(r => r.kind === 'word').map(r => r.text);

// ---- 操作 ----

async function changeDictionary(url, payload, message) {
    const res = await postJson(url, payload);
    if (!res.success) {
        setStatus(res.message, 'error');
        return null;
    }
    applyDictionary(res.dictionary);
    setStatus(message, 'ok');
    return res;
}

async function registerSelected() {
    const rows = selectedDictRows().filter(r => !r.shared);
    if (!rows.length) return setStatus('選んだ語句は、もう共用辞書に入っています', 'ok');
    await changeDictionary('/register_entries', {phrases: phrasePairs(rows), words: wordList(rows)},
        `${rows.length} 件を共用辞書に入れました`);
}

async function unregisterSelected() {
    const rows = selectedDictRows().filter(r => r.shared);
    if (!rows.length) return setStatus('選んだ語句は、共用辞書に入っていません', 'error');
    await changeDictionary('/unregister_entries', {phrases: phrasePairs(rows), words: wordList(rows)},
        `${rows.length} 件を共用辞書から消しました（入力はそのまま）`);
}

async function groupSelected() {
    const rows = selectedDictRows();
    if (!rows.length) return setStatus('kind を付与する語句を選んでください', 'error');
    if (rows.some(r => r.kind !== 'phrase' || !r.key)) return setStatus('kind を付与できるのは、キーのある語句だけです', 'error');
    if (new Set(rows.map(r => r.key)).size > 1) return setStatus('kind を付与する語句は、同じキーのものを選んでください', 'error');
    // 今ある kind に足すときは聞かない（その kind のまま）。新しく付与するときは窓で名前・前後の決まり・排他制限を聞く（やめたら付与しない）
    const naming = rows.some(r => groupIndex(r.key, r.text) >= 0) ? {} : await askGroupName();
    if (!naming) return setStatus('kind の付与をやめました', 'ok');
    if ('name' in naming && !named(naming)) return setStatus('kind の名前を入れてください', 'error');  // 新しい kind には名前が要る
    await changeDictionary('/group_phrases', {key: rows[0].key, phrases: rows.map(r => r.text), ...naming},
        `${rows[0].key} の ${rows.map(r => r.text).join(' / ')} に kind を付与しました`);
}

// kind の窓: 名前（前後の空白もそのまま）・前後の決まり・排他制限を聞く。決めたら {name, affix, exclusive}、やめたら null
function askGroupName(name = '', affix = 'suffix', exclusive = true) {
    const dialog = $('groupDialog');
    $('groupName').value = name;
    dialog.querySelector(`input[name="groupAffix"][value="${affix}"]`).checked = true;
    $('groupExclusive').checked = exclusive;
    dialog.returnValue = '';
    dialog.showModal();
    return new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'
        ? {name: $('groupName').value, affix: dialog.querySelector('input[name="groupAffix"]:checked').value,
            exclusive: $('groupExclusive').checked} : null), {once: true}));
}

// kind の名前・前後の決まり・排他制限を窓で変える（名前は外せない）。phrase は仲間の語句（どの kind かをサーバーが見分ける）
async function renameKind(i, phrase = kindMembers(state.groups[i])[0]) {
    const g = state.groups[i];
    if (!g || phrase === undefined) return;
    const naming = await askGroupName(named(g) ? g.name : '', named(g) ? g.affix || '' : 'suffix', exclusiveKind(g));
    if (!naming) return;
    if (!named(naming)) return setStatus('kind の名前は外せません（名前を入れてください）', 'error');
    await changeDictionary('/name_group', {key: g.key, phrase, ...naming}, `kind を ${groupLabel(naming, i)} にしました`);
}

// 右下の kind の一覧の「排他制限」のチェック: その kind の排他制限を付け外しする（名前と前後の決まりはそのまま。
// 変えられなければ、チェックを元に戻す）
async function toggleExclusive(i, on) {
    const g = state.groups[i];
    const phrase = g && kindMembers(g)[0];
    if (phrase === undefined) return;
    const done = await changeDictionary('/name_group', {key: g.key, phrase, name: g.name || '', affix: g.affix || '', exclusive: on},
        `kind ${groupLabel(g, i)} ${on ? 'に排他制限を付けました' : 'の排他制限を外しました'}`);
    if (!done) renderDictKinds();
}

// 右下の kind の「消す」（1秒長押し）: その kind を消す（キー・名前・前後の決まりで決めるので、仲間の語句が無い kind も消せる。
// 語句は辞書と入力にそのまま）
async function deleteKind(i) {
    const g = state.groups[i];
    if (!g) return;
    await changeDictionary('/delete_group', {key: g.key, name: g.name || '', affix: g.affix || ''},
        `kind ${groupLabel(g, i)} を消しました（語句はそのまま）`);
}

// 名前の候補で今ある kind を選んだとき: その kind の前後の決まりと排他制限も窓に入れる（同じ印になり、同じキーなら1つにまとまる）
function applyKindTraits(g) {
    $('groupDialog').querySelector(`input[name="groupAffix"][value="${g.affix || ''}"]`).checked = true;
    $('groupExclusive').checked = exclusiveKind(g);
}

// ---- kind の窓の名前の候補（過去タグ: 今ある kind の名前を先に、後ろに辞書のタグ（語句と単語）） ----

const KIND_FIRST = 1000;  // kind の名前は、合えばいつも辞書のタグより先

// 辞書のタグ: 同じ文字の語句・単語は1つにまとめる（件数は足す。件数の多い順）
function tagCandidates() {
    const tags = new Map();
    const entries = [...state.phrases.map(p => [p.phrase, p]), ...state.words.map(w => [w.word, w])];
    for (const [text, {count, here}] of entries) {
        const tag = tags.get(text) || {kind: 'name', label: text, match: text, name: text, count: 0, here: 0};
        tag.count += count;
        tag.here += here || 0;
        tags.set(text, tag);
    }
    return [...tags.values()].map(tag => ({...tag, bonus: Math.log1p(tag.count)}));
}

// kind は印の形（.posture・._ face）で見せ、選ぶと名前を入れ、前後の決まりと排他制限も窓に入れる（同じ印の kind は1つ）
const sameTraits = (a, b) => a.name === b.name && (a.affix || '') === (b.affix || '');
CANDIDATE_SOURCES.kindName = () => [
    ...state.groups.map((g, i) => [g, i]).filter(([g], at, all) => named(g) && all.findIndex(([x]) => sameTraits(x, g)) === at)
        .map(([g, i]) => ({kind: 'name', label: groupLabel(g, i), match: g.name, name: g.name, bonus: KIND_FIRST,
            chosen: () => applyKindTraits(g)})),
    ...tagCandidates(),
];

// 名前の欄の候補を出す（all ならダブルクリック: 打った文字によらず全部の候補）。選ぶと欄の文字を全部置き換える。
// 窓（モーダル）の外の候補の一覧は窓の後ろに隠れるので、窓の中へ移す。欄の下の選択を覆わないよう、欄の右（入らなければ左）に置く
function suggestKindNames(all = false) {
    const dialog = $('groupDialog');
    const list = $('suggestions');
    if (list.parentElement !== dialog) dialog.append(list);
    showSuggestions($('groupName'), '', el => ({mode: 'kindName', query: all ? '' : el.value, queryStart: 0, end: el.value.length,
        after: '', current: [], cellPhrases: [], all}));
    if (list.hidden) return;
    const rect = $('groupName').getBoundingClientRect();
    const right = rect.right + 4;
    list.style.left = `${right + list.offsetWidth <= window.innerWidth ? right : Math.max(0, rect.left - list.offsetWidth - 4)}px`;
    list.style.top = `${rect.top}px`;
}

// 名前の欄のキー（候補が出ているとき）: ↑↓ で選び、Enter で入れる（ダブルクリックで出した一覧か、↑↓ で選んだときだけ。
// 打った名前のままの Enter は窓の「決める」）。Esc は候補だけを閉じる（窓は閉じない）。Tab は入れずに次へ
function kindNameKey(event) {
    const s = state.suggest;
    if (!s || s.el !== event.target) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') moveActive(event.key === 'ArrowDown' ? 1 : -1);
    else if (event.key === 'Enter' && (s.ctx.all || s.moved)) accept(s.items[s.active]);
    else if (event.key === 'Escape') hideSuggestions();
    else return;
    event.preventDefault();
}

// 表の印のダブルクリック: その行の kind を変える
async function renameGroup(tr) {
    const i = groupIndex(tr.dataset.key, tr.dataset.text);
    if (i >= 0) await renameKind(i, tr.dataset.text);
}

async function ungroupSelected() {
    const rows = selectedDictRows().filter(r => rowKind(r) >= 0);
    if (!rows.length) return setStatus('選んだ語句には kind がありません', 'error');
    // 前後の決まりで入っている語句は外さない（決まりに合う限り、また仲間になる）
    const bound = rows.filter(r => followsRule(state.groups[rowKind(r)], r.text));
    const free = rows.filter(r => !bound.includes(r));
    const reason = `${bound.map(r => r.text).join(' / ')} は前後の決まりで入っているので、外せません（kind の名前か前後を変えてください）`;
    if (!free.length) return setStatus(reason, 'error');
    await changeDictionary('/ungroup_phrases', {phrases: phrasePairs(free)},
        `${free.length} 件を kind から外しました${bound.length ? `（${reason}）` : ''}`);
}

async function addEntry() {
    const phrase = $('dictAddText').value.trim();
    if (!phrase) return setStatus('語句を入力してください', 'error');
    const res = await changeDictionary('/add_entry', {section: $('dictAddSection').value, key: $('dictAddKey').value, phrase},
        `「${phrase}」を共用辞書に足しました`);
    if (res) $('dictAddText').value = '';
}

function startRename(tr) {
    dict.renaming = tr.dataset.id;
    renderDictionary();
    const input = $('dictBody').querySelector('.rename-input');
    if (!input) return;
    input.focus();
    input.select();
}

function cancelRename() {
    dict.renaming = null;
    renderDictionary();
}

// 改名: 共用辞書の名前を変え、チェックが入っていれば開いているプロジェクトの入力も置き換える
async function commitRename(input) {
    const row = dict.rows.find(r => r.id === dict.renaming);
    const name = input.value.trim();
    dict.renaming = null;
    if (!row || !name || name === row.text) return renderDictionary();
    commitEdit();
    await settled();
    const inProject = state.loaded && $('dictRenameInProject').checked;
    const res = await postJson('/rename_entry', {key: row.key, old: row.text, new: name, in_project: inProject});
    if (!res.success) {
        renderDictionary();
        return setStatus(res.message, 'error');
    }
    if (res.changed) {
        setDirty(true);
        await refreshTable();
    }
    applyDictionary(res.dictionary);
    const replaced = res.changed ? `（開いているプロジェクトの ${res.changed} 行を置き換えました。保存はまだです）` : '';
    setStatus(`「${row.text}」を「${name}」にしました${replaced}`, 'ok');
}

// ---- 画面の切り替え ----

function showView(view) {
    if (view === state.view) return;
    if (view === 'dictionary') {
        commitEdit();
        hideSuggestions();
        dict.scroll = $('imagesView').scrollTop;
    }
    state.view = view;
    const images = view === 'images';
    document.querySelectorAll('.tab').forEach(tab => {
        const on = tab.dataset.view === view;
        tab.classList.toggle('on', on);
        tab.setAttribute('aria-pressed', String(on));
    });
    $('imagesView').hidden = !images;
    $('tools').hidden = !images || !state.loaded;
    $('markTools').hidden = !images || !state.loaded;
    $('dictTools').hidden = images;
    $('dictSelTools').hidden = images;
    $('dictView').hidden = images;
    if (images) {
        fitPictureColumn();  // 共用辞書の画面にいる間に表を描いた場合は、ここで測る
        fitThumbnails();
        fitHints($('gridBody'));
        $('imagesView').scrollTop = dict.scroll;
        return;
    }
    renderDictionary();
    refreshWords();  // 保存済みの他のプロジェクトの変更も拾う
}

// ---- つなぎ込み ----

function wireDictionary() {
    document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => showView(tab.dataset.view)));
    document.addEventListener('pictag:dictionary', () => {
        if (state.view === 'dictionary' && dict.renaming === null) renderDictionary();
    });
    $('dictFilter').addEventListener('input', () => {
        dict.exact = false;  // 打つと、あいまいに戻る
        renderDictionary();
    });
    $('dictFilter').addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.isComposing) searchExactly();
    });
    $('dictSearchButton').addEventListener('click', searchExactly);
    $('dictResetButton').addEventListener('click', resetDictFilter);
    for (const id of ['dictFilterMode', 'dictShared']) $(id).addEventListener('change', renderDictionary);
    // 見出しの ▲▼: その列で並べ替える。同じものをもう一度押すと元の並び
    document.querySelector('#dictGrid thead').addEventListener('click', event => {
        const button = event.target.closest('button.sort');
        if (!button) return;
        const next = {by: button.dataset.sort, dir: Number(button.dataset.dir)};
        dict.sort = dict.sort && dict.sort.by === next.by && dict.sort.dir === next.dir ? null : next;
        paintSortButtons();
        renderDictionary();
    });
    $('dictAll').addEventListener('change', () => {
        dict.selected = $('dictAll').checked ? new Set(dict.rows.map(r => r.id)) : new Set();
        paintDictSelection();
    });
    $('dictBody').addEventListener('click', event => {
        if (event.target.closest('.rename-input')) return;
        const tr = event.target.closest('tr');
        if (!tr) return;
        if (event.target.closest('.dict-rename')) {
            startRename(tr);
            return;
        }
        if (event.target.closest('.group-badge')) return;  // 印はダブルクリックで名前を変える（選択は変えない）
        clickDictRow(tr, event);
    });
    $('dictBody').addEventListener('dblclick', event => {
        const badge = event.target.closest('.group-badge');
        if (badge) guarded(renameGroup)(badge.closest('tr'));
    });
    // 右上の画像: クリックで画像の画面のその行へ / 右下の kind: 語句で左の表のその行へ、改名で窓
    // 右上の画像: クリックで簡易表示に出し、ダブルクリックで画像の画面のその行へ。簡易表示のサムネイルのクリックでも画像の画面へ
    $('dictImageList').addEventListener('click', event => {
        const thumb = event.target.closest('.dict-thumb');
        if (thumb) previewImage(Number(thumb.dataset.index));
    });
    $('dictImageList').addEventListener('dblclick', event => {
        const thumb = event.target.closest('.dict-thumb');
        if (thumb) jumpToImage(Number(thumb.dataset.index));
    });
    $('dictRowView').addEventListener('click', event => {
        const img = event.target.closest('td.thumb img');
        if (img) jumpToImage(Number(img.closest('tr').dataset.index));
    });
    $('dictKindList').addEventListener('click', event => {
        const member = event.target.closest('.kind-member');
        if (member) return jumpToEntry(member.dataset.key, member.dataset.text);
        const edit = event.target.closest('.kind-edit');
        if (edit) guarded(renameKind)(Number(edit.closest('.dict-kind').dataset.i));
    });
    $('dictKindList').addEventListener('change', event => {
        const box = event.target.closest('input.kind-exclusive');
        if (box) guarded(toggleExclusive)(Number(box.closest('.dict-kind').dataset.i), box.checked);
    });
    // kind の窓の名前の欄: ダブルクリックで過去タグの候補を全部出し、打つと fzf のように絞る。窓を閉じたら候補をしまい、一覧を元の場所へ
    $('groupName').addEventListener('dblclick', () => suggestKindNames(true));
    $('groupName').addEventListener('input', () => suggestKindNames());
    $('groupName').addEventListener('keydown', kindNameKey);
    $('groupName').addEventListener('blur', hideSuggestions);
    $('groupDialog').addEventListener('close', () => {
        hideSuggestions();
        document.body.append($('suggestions'));
    });
    $('dictBody').addEventListener('keydown', event => {
        const input = event.target.closest('.rename-input');
        if (!input) return;
        if (event.key === 'Enter') {
            event.preventDefault();
            guarded(commitRename)(input);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            cancelRename();
        }
    });
    // 改名の欄から外れたらやめる（決定は Enter だけ。誤って共用辞書や入力を変えないように）
    $('dictBody').addEventListener('focusout', event => {
        if (event.target.closest('.rename-input') && dict.renaming !== null) cancelRename();
    });
    $('dictAddForm').addEventListener('submit', event => {
        event.preventDefault();
        guarded(addEntry)();
    });
    $('dictAddSection').addEventListener('change', fillDictAdd);
    $('dictRegisterButton').addEventListener('click', guarded(registerSelected));
    $('dictGroupButton').addEventListener('click', guarded(groupSelected));
    $('dictUngroupButton').addEventListener('click', guarded(ungroupSelected));
    holdToRun($('dictUnregisterButton'), unregisterSelected, '1秒長押しすると、選んだ語句を共用辞書から消します');
    $('dictDeselectButton').addEventListener('click', () => {
        dict.selected = new Set();
        paintDictSelection();
    });
}

wireDictionary();
