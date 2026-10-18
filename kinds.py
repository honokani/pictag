"""タグ辞書（大kind → 中kind → 小kind → 値）と表の列の操作

すべて純粋関数で、辞書は書き換えずに作り直して返す。

辞書（data_work/kinds.json）:
    {"bigs": [{"name": "girl", "mids": ["looks", "body"], "lines": []},
              {"name": "action", "mids": [], "lines": ["girl walks a dog"]}],
     "mids": [{"name": "body", "entries": [{"small": "hair", "value": "long"}, {"small": "", "value": "bare hands"}]}]}
- 中kind の値（entries）は、その中kind を使う大kind すべてで共有する。同じ小kind の値は隣り合わせに並べる
- lines は大kind が直接持つキーなしの行（action の文など）。大kind ごとに持ち、共有しない

列: (大kind, 中kind, 小kind, 値) のタプル。中kind が "" の列は lines の行、小kind が "" の値は小kind なし
"""
import json
from functools import reduce

LEVELS = ('big', 'mid', 'small', 'value')
LEVEL_NAMES = {'big': '大kind', 'mid': '中kind', 'small': '小kind', 'value': '値'}


def empty_kinds():
    return {'bigs': [], 'mids': []}


def column_key(item):
    """列の文字列キー（表の列名・画面とのやり取りに使う）"""
    return json.dumps(list(item), ensure_ascii=False)


def parse_key(key):
    return tuple(json.loads(key))


def named(items, name):
    return next((x for x in items if x['name'] == name), None)


def update_named(items, name, change):
    return [change(x) if x['name'] == name else x for x in items]


def entries_of(kinds, mid):
    found = named(kinds['mids'], mid)
    return found['entries'] if found else []


def mid_columns(kinds, big, mid):
    """中kind の全部の値を、指定の大kind の列にする"""
    return [(big, mid, e['small'], e['value']) for e in entries_of(kinds, mid)]


def big_columns(kinds, big):
    return [
        *(item for mid in big['mids'] for item in mid_columns(kinds, big['name'], mid)),
        *((big['name'], '', '', line) for line in big['lines']),
    ]


def dictionary_columns(kinds):
    """辞書の全列を辞書の順に（新規プロジェクトの初期列）"""
    return [item for big in kinds['bigs'] for item in big_columns(kinds, big)]


def order_columns(kinds, items):
    """表の列を辞書の順に並べる（辞書に無い列は元の順のまま後ろ）"""
    position = {item: i for i, item in enumerate(dictionary_columns(kinds))}
    return sorted(items, key=lambda item: position.get(item, len(position)))


def appended(items, value):
    return items if value in items else [*items, value]


def insert_entry(entries, entry):
    """値を足す。同じ小kind の値があれば、その最後の後ろに入れる"""
    if entry in entries:
        return entries
    same = [i for i, e in enumerate(entries) if entry['small'] and e['small'] == entry['small']]
    at = same[-1] + 1 if same else len(entries)
    return [*entries[:at], entry, *entries[at:]]


def with_big(kinds, name):
    if named(kinds['bigs'], name):
        return kinds
    return {**kinds, 'bigs': [*kinds['bigs'], {'name': name, 'mids': [], 'lines': []}]}


def with_mid(kinds, name):
    if named(kinds['mids'], name):
        return kinds
    return {**kinds, 'mids': [*kinds['mids'], {'name': name, 'entries': []}]}


def change_big(kinds, name, change):
    return {**kinds, 'bigs': update_named(kinds['bigs'], name, change)}


def change_entries(kinds, mid, change):
    return {**kinds, 'mids': update_named(kinds['mids'], mid, lambda m: {**m, 'entries': change(m['entries'])})}


def add_value(kinds, item):
    """列を辞書に足す（無い大kind・中kind も作り、大kind がその中kind を使うようにする）"""
    big, mid, small, value = item
    kinds = with_big(kinds, big)
    if not mid:
        return change_big(kinds, big, lambda b: {**b, 'lines': appended(b['lines'], value)})
    kinds = change_big(with_mid(kinds, mid), big, lambda b: {**b, 'mids': appended(b['mids'], mid)})
    return change_entries(kinds, mid, lambda entries: insert_entry(entries, {'small': small, 'value': value}))


def register_columns(kinds, items):
    """表にあって辞書に無い列を辞書へ足す"""
    known = set(dictionary_columns(kinds))
    return reduce(add_value, [item for item in items if item not in known], kinds)


def check_name(name):
    """名前の前後の空白を除いて検証する"""
    name = (name or '').strip()
    if not name:
        raise ValueError('名前を入力してください')
    if '\n' in name or '\r' in name:
        raise ValueError('名前に改行は使えません')
    return name


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(item):
    return item


def rename(kinds, level, target, new_name):
    """target (大kind, 中kind, 小kind, 値) の level の名前を変える。(新しい辞書, 列の付け替え関数) を返す

    中kind・小kind・値は共有の語彙なので、その中kind を使う大kind すべての列が変わる
    """
    big, mid, small, value = target
    new_name = check_name(new_name)
    old_name = dict(zip(LEVELS, target)).get(level)
    require(level in LEVELS, f'不明な階層です: {level}')
    if new_name == old_name:
        return kinds, identity
    exists = f'{LEVEL_NAMES[level]}「{new_name}」は既にあります'

    if level == 'big':
        require(named(kinds['bigs'], big), f'大kind「{big}」がありません')
        require(not named(kinds['bigs'], new_name), exists)
        return (change_big(kinds, big, lambda b: {**b, 'name': new_name}),
                lambda it: (new_name, *it[1:]) if it[0] == big else it)

    if level == 'mid':
        require(mid and named(kinds['mids'], mid), f'中kind「{mid}」がありません')
        require(not named(kinds['mids'], new_name), exists)
        bigs = [{**b, 'mids': [new_name if m == mid else m for m in b['mids']]} for b in kinds['bigs']]
        mids = update_named(kinds['mids'], mid, lambda m: {**m, 'name': new_name})
        return ({**kinds, 'bigs': bigs, 'mids': mids},
                lambda it: (it[0], new_name, *it[2:]) if it[1] == mid else it)

    if level == 'small':
        smalls = {e['small'] for e in entries_of(kinds, mid)}
        require(small and small in smalls, f'小kind「{small}」がありません')
        require(new_name not in smalls, exists)
        return (change_entries(kinds, mid, lambda entries: [
                    {**e, 'small': new_name} if e['small'] == small else e for e in entries]),
                lambda it: (it[0], mid, new_name, it[3]) if it[1:3] == (mid, small) else it)

    if not mid:
        found = named(kinds['bigs'], big)
        require(found and value in found['lines'], f'行「{value}」がありません')
        require(new_name not in found['lines'], exists)
        return (change_big(kinds, big, lambda b: {**b, 'lines': [new_name if x == value else x for x in b['lines']]}),
                lambda it: (big, '', '', new_name) if it == (big, '', '', value) else it)

    entry = {'small': small, 'value': value}
    require(entry in entries_of(kinds, mid), f'値「{value}」がありません')
    require({'small': small, 'value': new_name} not in entries_of(kinds, mid), exists)
    return (change_entries(kinds, mid, lambda entries: [{**e, 'value': new_name} if e == entry else e for e in entries]),
            lambda it: (it[0], mid, small, new_name) if it[1:] == (mid, small, value) else it)


def remove(kinds, level, target):
    """辞書から消す。(新しい辞書, 表から消える列かを判定する関数) を返す

    - 値・小kind: 共有の語彙から消す（その中kind を使う大kind すべてから消える）
    - 中kind: 選んだ大kind から外すだけ（語彙は残り、他の大kind はそのまま使える）
    - 大kind: 大kind ごと消す
    """
    big, mid, small, value = target
    require(level in LEVELS, f'不明な階層です: {level}')

    if level == 'big':
        require(named(kinds['bigs'], big), f'大kind「{big}」がありません')
        return {**kinds, 'bigs': [b for b in kinds['bigs'] if b['name'] != big]}, lambda it: it[0] == big

    if level == 'mid':
        require(named(kinds['bigs'], big), f'大kind「{big}」がありません')
        if not mid:
            return change_big(kinds, big, lambda b: {**b, 'lines': []}), lambda it: it[:2] == (big, '')
        return (change_big(kinds, big, lambda b: {**b, 'mids': [m for m in b['mids'] if m != mid]}),
                lambda it: it[:2] == (big, mid))

    if level == 'small':
        require(small and any(e['small'] == small for e in entries_of(kinds, mid)), f'小kind「{small}」がありません')
        return (change_entries(kinds, mid, lambda entries: [e for e in entries if e['small'] != small]),
                lambda it: it[1:3] == (mid, small))

    if not mid:
        found = named(kinds['bigs'], big)
        require(found and value in found['lines'], f'行「{value}」がありません')
        return (change_big(kinds, big, lambda b: {**b, 'lines': [x for x in b['lines'] if x != value]}),
                lambda it: it == (big, '', '', value))

    entry = {'small': small, 'value': value}
    require(entry in entries_of(kinds, mid), f'値「{value}」がありません')
    return (change_entries(kinds, mid, lambda entries: [e for e in entries if e != entry]),
            lambda it: it[1:] == (mid, small, value))


def in_table_scope(level, target, item):
    """「表から外す」の範囲か（選んだ大kind の中だけ。level までの名前が一致する列）"""
    depth = LEVELS.index(level) + 1
    return tuple(item[:depth]) == tuple(target[:depth])
