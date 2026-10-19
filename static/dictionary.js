// pictag 共用辞書の画面（タブで切り替え）
// 一覧は「キー: 語句」で1行（段落をまたいでまとめる）と、キーなしの文の単語。登録・削除・改名・「1つだけ」のグループ
// control.js の state・通信・表示の小物を使う
'use strict';

const dict = {
    rows: [],              // 表示中の行（絞り込み後）
    selected: new Set(),   // 行の id
    anchor: null,          // Shift 範囲選択の起点（最後にクリックした行）
    renaming: null,        // 改名中の行の id
    scroll: 0,             // 画像の画面のスクロール位置（戻ったときに戻す）
};

const KEYLESS_FILTER = ':keyless';  // キーの絞り込みの「キーなし」「単語」（キーに「:」は無いので重ならない）
const WORD_FILTER = ':word';
const GROUP_COLORS = 6;

const baseName = section => section.replace(/ [A-Z]$/, '');  // guy A → guy（subjects.py の base_name と同じ）

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
    const template = [...(state.templates.picture || []), ...(state.templates.subject || [])];
    const at = template.indexOf(row.key);
    return at >= 0 ? [0, String(at).padStart(3, '0')] : [1, row.key];
}

function compareRows(a, b) {
    const [rankA, keyA] = keyRank(a);
    const [rankB, keyB] = keyRank(b);
    return rankA - rankB || keyA.localeCompare(keyB) || a.text.localeCompare(b.text, undefined, {sensitivity: 'base'});
}

function matchesDictFilter(row) {
    const query = $('dictFilter').value.trim().toLowerCase();
    const key = $('dictKey').value;
    const shared = $('dictShared').value;
    const okKey = key === '' || (key === WORD_FILTER ? row.kind === 'word'
        : key === KEYLESS_FILTER ? row.kind === 'phrase' && !row.key : row.key === key);
    return (!query || row.text.toLowerCase().includes(query)) && okKey && (!shared || (shared === 'in') === row.shared);
}

const groupIndex = (key, phrase) => state.groups.findIndex(g => g.key === key && g.phrases.includes(phrase));

function groupBadge(i) {
    const title = `1つだけのグループ: ${state.groups[i].phrases.join(' / ')}`;
    return `<span class="group-badge g${i % GROUP_COLORS}" title="${escapeHtml(title)}">G${i + 1}</span>`;
}

function dictRowHtml(row) {
    const group = row.kind === 'phrase' && row.key ? groupIndex(row.key, row.text) : -1;
    const key = row.kind === 'word' ? '（単語）' : row.key || '（キーなし）';
    const text = dict.renaming === row.id
        ? `<input type="text" class="rename-input" value="${escapeHtml(row.text)}" aria-label="新しい名前" title="Enter で決定、Esc でやめる">`
        : escapeHtml(row.text);
    const on = dict.selected.has(row.id);
    return `<tr data-id="${escapeHtml(row.id)}" data-kind="${row.kind}" data-key="${escapeHtml(row.key || '')}" ` +
        `data-text="${escapeHtml(row.text)}"${on ? ' class="selected"' : ''}>` +
        `<td><input type="checkbox" class="dict-check"${on ? ' checked' : ''} aria-label="選ぶ"></td>` +
        `<td class="dict-key">${escapeHtml(key)}</td>` +
        `<td class="dict-phrase">${text}</td>` +
        `<td class="dict-sections">${escapeHtml(row.sections.join(', '))}</td>` +
        `<td class="num">${row.count}</td>` +
        `<td class="dict-shared">${row.shared ? '<span class="shared-mark" title="共用辞書に入っている">✓</span>' : ''}</td>` +
        `<td class="dict-group">${group >= 0 ? groupBadge(group) : ''}</td>` +
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

// 手で足す語句の段落とキー（一括入力と同じく 段落 → キー）
function fillDictAdd() {
    const sections = [...new Set([...state.defaultSections, ...state.sections, ...state.phrases.map(p => p.section)])];
    keepOptions($('dictAddSection'), sections.map(s => [s, s]));
    keepOptions($('dictAddKey'), bulkKeys($('dictAddSection').value).map(k => [k, k || '（キーなし）']));
}

function renderDictionary() {
    const all = dictionaryRows();
    fillDictKeyFilter(all);
    fillDictAdd();
    dict.rows = all.filter(matchesDictFilter);
    const visible = new Set(dict.rows.map(r => r.id));
    dict.selected = new Set([...dict.selected].filter(id => visible.has(id)));  // 見えなくなった行は選択から外す
    $('dictBody').innerHTML = dict.rows.map(dictRowHtml).join('');
    $('dictCount').textContent = `${dict.rows.length} 件`;
    $('dictEmpty').hidden = dict.rows.length > 0;
    paintDictSelection();
}

// ---- 選択（クリック: 足し引き / Shift: 最後にクリックした行からの範囲を足す） ----

function clickDictRow(tr, event) {
    const id = tr.dataset.id;
    const order = dict.rows.map(r => r.id);
    const from = order.indexOf(dict.anchor);
    const to = order.indexOf(id);
    if (event.shiftKey && from >= 0 && to >= 0) {
        order.slice(Math.min(from, to), Math.max(from, to) + 1).forEach(i => dict.selected.add(i));
    } else if (dict.selected.has(id)) {
        dict.selected.delete(id);
    } else {
        dict.selected.add(id);
    }
    dict.anchor = id;
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
    if (rows.some(r => r.kind !== 'phrase' || !r.key)) return setStatus('グループにできるのは、キーのある語句だけです', 'error');
    if (new Set(rows.map(r => r.key)).size > 1) return setStatus('グループにする語句は、同じキーのものを選んでください', 'error');
    if (rows.length < 2) return setStatus('グループにする語句を2つ以上選んでください', 'error');
    await changeDictionary('/group_phrases', {key: rows[0].key, phrases: rows.map(r => r.text)},
        `${rows[0].key} の ${rows.map(r => r.text).join(' / ')} を、1つだけのグループにしました`);
}

async function ungroupSelected() {
    const rows = selectedDictRows().filter(r => r.kind === 'phrase' && groupIndex(r.key, r.text) >= 0);
    if (!rows.length) return setStatus('選んだ語句は、グループに入っていません', 'error');
    await changeDictionary('/ungroup_phrases', {phrases: phrasePairs(rows)}, `${rows.length} 件をグループから外しました`);
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
    $('dictKey').addEventListener('change', renderDictionary);
    $('dictShared').addEventListener('change', renderDictionary);
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
        clickDictRow(tr, event);
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
