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
};

const KEYLESS_FILTER = ':keyless';  // キーの絞り込みの「キーなし」「単語」（キーに「:」は無いので重ならない）
const WORD_FILTER = ':word';
const NO_KIND = ':none';            // kind の絞り込みの「kind なし」
const GROUP_COLORS = 6;

// ---- 一覧の行 ----

function dictionaryRows() {
    const rows = new Map();
    const add = (id, base, entry) => {
        const row = rows.get(id) || {...base, id, sections: [], count: 0, shared: false};
        const section = baseName(entry.section);
        if (!row.sections.includes(section)) row.sections.push(section);
        row.count += entry.count;
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

// 絞り込み: 語句の文字、キーと kind（それぞれ「対象を表示 / 以外を表示」。「すべて」なら絞らない）、共用辞書に入っているか
function matchesDictFilter(row) {
    const query = $('dictFilter').value.trim().toLowerCase();
    const [key, kind, shared] = [$('dictKey').value, $('dictKind').value, $('dictShared').value];
    const keyHit = key === WORD_FILTER ? row.kind === 'word' : key === KEYLESS_FILTER ? row.kind === 'phrase' && !row.key : row.key === key;
    const kindHit = kind === NO_KIND ? rowKind(row) < 0 : rowKind(row) === Number(kind);
    const okKey = key === '' || keyHit === ($('dictKeyMode').value === 'in');
    const okKind = kind === '' || kindHit === ($('dictKindMode').value === 'in');
    return (!query || row.text.toLowerCase().includes(query)) && okKey && okKind && (!shared || (shared === 'in') === row.shared);
}

// 並べ替え（見出しの ▲▼）の比べる文字: キーは表示の名前、kind は印の文字（kind の無い行は向きによらず後ろ）、語句。同じなら元の並び
const SORT_TEXT = {
    key: row => dictKeyLabel(row),
    kind: row => (rowKind(row) < 0 ? null : groupLabel(state.groups[rowKind(row)], rowKind(row))),
    text: row => row.text,
};

function sortedRows(rows) {
    if (!dict.sort) return rows;
    const text = SORT_TEXT[dict.sort.by];
    return rows.map((row, i) => ({row, i, t: text(row)}))
        .sort((a, b) => (a.t === null) - (b.t === null)
            || (a.t === null ? 0 : dict.sort.dir * a.t.localeCompare(b.t, undefined, {sensitivity: 'base'})) || a.i - b.i)
        .map(x => x.row);
}

// 語句の入っている kind の位置（一覧か前後の決まりで。無ければ -1）
const groupIndex = (key, phrase) => state.groups.findIndex(g => inGroup(g, key, phrase));
const rowKind = row => (row.kind === 'phrase' && row.key ? groupIndex(row.key, row.text) : -1);

// kind の印（ダブルクリックで名前・前後の決まり・1つだけを変える）
function groupBadge(i) {
    const g = state.groups[i];
    return `<span class="group-badge g${i % GROUP_COLORS}" title="${escapeHtml(`${groupTitle(g, i)}（ダブルクリックで変える）`)}">` +
        `${escapeHtml(groupLabel(g, i))}</span>`;
}

// キーの列: 単語は（単語）、キーなしの文は action だけで使っていれば action、ほかは（キーなし）
const dictKeyLabel = row => (row.kind === 'word' ? '（単語）' : row.key || (row.sections.every(s => s === 'action') ? 'action' : '（キーなし）'));

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
        `<td class="dict-key">${escapeHtml(key)}</td>` +
        `<td class="dict-group">${group >= 0 ? groupBadge(group) : ''}</td>` +
        `<td class="dict-phrase">${text}</td>` +
        `<td class="dict-sections">${escapeHtml(row.sections.join(', '))}</td>` +
        `<td class="num">${row.count}</td>` +
        `<td class="dict-shared">${row.shared ? '<span class="shared-mark" title="共用辞書に入っている">✓</span>' : ''}</td>` +
        `<td>${row.kind === 'phrase' ? '<button type="button" class="dict-rename">改名</button>' : ''}</td></tr>`;
}

// 選択肢を入れ替える（前に選んでいた値があれば残す）
function keepOptions(select, options) {
    const keep = select.options.length ? select.value : null;
    select.innerHTML = options.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('');
    if (options.some(([value]) => value === keep)) select.value = keep;
}

function fillDictKeyFilter(rows) {
    const keys = [...new Set(rows.filter(r => r.kind === 'phrase' && r.key).map(r => r.key))];
    keepOptions($('dictKey'), [['', 'すべてのキー'], ...keys.map(k => [k, k]), [KEYLESS_FILTER, '（キーなし）'], [WORD_FILTER, '（単語）']]);
}

// kind の絞り込みの選択肢（すべて・kind なし・各 kind の印）。「対象を表示 / 以外を表示」は「すべて」のとき使えない
function fillDictKindFilter() {
    keepOptions($('dictKind'), [['', 'すべての kind'], [NO_KIND, '（kind なし）'], ...state.groups.map((g, i) => [String(i), groupLabel(g, i)])]);
    $('dictKeyMode').disabled = $('dictKey').value === '';
    $('dictKindMode').disabled = $('dictKind').value === '';
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
    fillDictKeyFilter(all);
    fillDictKindFilter();
    fillDictAdd();
    dict.rows = sortedRows(all.filter(matchesDictFilter));
    const visible = new Set(dict.rows.map(r => r.id));
    dict.selected = new Set([...dict.selected].filter(id => visible.has(id)));  // 見えなくなった行は選択から外す
    if (!dict.selected.has(dict.focus)) dict.focus = [...dict.selected].pop() ?? null;
    $('dictBody').innerHTML = dict.rows.map(dictRowHtml).join('');
    $('dictCount').textContent = `${dict.rows.length} 件`;
    $('dictEmpty').hidden = dict.rows.length > 0;
    paintDictSelection();
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
    // 今ある kind に足すときは聞かない（その kind のまま）。新しく付与するときは窓で名前・前後の決まり・1つだけを聞く（やめたら付与しない）
    const naming = rows.some(r => groupIndex(r.key, r.text) >= 0) ? {} : await askGroupName();
    if (!naming) return setStatus('kind の付与をやめました', 'ok');
    await changeDictionary('/group_phrases', {key: rows[0].key, phrases: rows.map(r => r.text), ...naming},
        `${rows[0].key} の ${rows.map(r => r.text).join(' / ')} に kind を付与しました`);
}

// kind の窓: 名前（前後の空白もそのまま）・前後の決まり・1つだけを聞く。決めたら {name, affix, exclusive}、やめたら null
function askGroupName(name = '', affix = 'postfix', exclusive = true) {
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

// 印のダブルクリック: その kind の名前・前後の決まり・1つだけを変える（名前が空なら番号に戻す）
async function renameGroup(tr) {
    const [key, phrase] = [tr.dataset.key, tr.dataset.text];
    const i = groupIndex(key, phrase);
    if (i < 0) return;
    const g = state.groups[i];
    const naming = await askGroupName(named(g) ? g.name : '', named(g) ? g.affix || '' : 'postfix', exclusiveKind(g));
    if (!naming) return;
    await changeDictionary('/name_group', {key, phrase, ...naming},
        named(naming) ? `kind を ${groupLabel(naming, i)} にしました` : `kind の名前を外しました（${groupLabel({}, i)}）`);
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
    $('dictFilter').addEventListener('input', renderDictionary);
    for (const id of ['dictKey', 'dictKeyMode', 'dictKind', 'dictKindMode', 'dictShared']) $(id).addEventListener('change', renderDictionary);
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
