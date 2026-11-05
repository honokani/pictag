"""「1つだけ」のグループ: 同じキーの語句のうち、1枚の画像の1段落に1つだけ置けるもの（例: looks の standing / sitting / lying）

グループは {key, phrases}。名前（name）を付けられ、前後の決まり（affix: postfix / prefix）があれば、名前で終わる / 始まる同じキーの語句も
いつも仲間にする（「 face」の postfix なら crying face も）。1つの語句が入るグループは、キーごとに1つまで（重なれば1つにまとめる）
"""
from functools import reduce

from caption_format import phrases_of

AFFIXES = ('prefix', 'postfix')


def naming(group):
    """グループの名前と前後の決まり（名前が文字列でない・空白だけなら無し。決まりは prefix / postfix のときだけ）"""
    name = group.get('name')
    if not isinstance(name, str) or not name.strip():
        return {}
    return {'name': name, **({'affix': group['affix']} if group.get('affix') in AFFIXES else {})}


def follows_rule(group, phrase):
    """phrase がグループの前後の決まりに合うか（postfix は名前で終わる、prefix は名前で始まる。名前の空白もそのまま比べる）"""
    named = naming(group)
    affix = named.get('affix')
    return (affix == 'postfix' and phrase.endswith(named['name'])) or (affix == 'prefix' and phrase.startswith(named['name']))


def in_group(group, key, phrase):
    """phrase がグループの仲間か（同じキーで、語句の一覧に入っているか、前後の決まりに合う）"""
    return group['key'] == key and (phrase in group['phrases'] or follows_rule(group, phrase))


def overlaps(a, b):
    """2つのグループが重なるか（どちらかの一覧の語句が、もう一方の仲間）"""
    return any(in_group(a, b['key'], p) for p in b['phrases']) or any(in_group(b, a['key'], p) for p in a['phrases'])


def normalize_groups(groups):
    """重なるグループを1つにまとめ（先に出たグループの位置へ。名前は先にあった方）、語句が2つ未満で前後の決まりも無いグループを除く"""
    def merge(merged, group):
        new = {'key': group['key'], 'phrases': list(dict.fromkeys(group['phrases'])), **naming(group)}
        hits = [i for i, g in enumerate(merged) if overlaps(g, new)]
        if not hits:
            return [*merged, new]
        named = next((merged[i] for i in hits if naming(merged[i])), new)
        joined = {'key': group['key'], 'phrases': list(dict.fromkeys([p for i in hits for p in merged[i]['phrases']] + new['phrases'])),
                  **naming(named)}
        return [joined if i == hits[0] else g for i, g in enumerate(merged) if i == hits[0] or i not in hits]

    return [g for g in reduce(merge, groups, []) if len(g['phrases']) >= 2 or 'affix' in g]


def clean_groups(groups):
    """読み込んだグループのうち形の正しいものだけを残してまとめ直す（手で書き換えたファイルでも落ちないように）"""
    valid = [{'key': g['key'], 'phrases': [p for p in g['phrases'] if isinstance(p, str) and p], **naming(g)}
             for g in groups
             if isinstance(g, dict) and isinstance(g.get('key'), str) and g['key'] and isinstance(g.get('phrases'), list)]
    return normalize_groups(valid)


def group_of(groups, key, phrase):
    """phrase の入っているグループ（語句の一覧か前後の決まりで。無ければ None）"""
    return next((g for g in groups if in_group(g, key, phrase)), None)


def blocked_by(groups, text, key, phrase):
    """入力の key の行に、phrase と同じグループの別の語句があればそれを返す（無ければ None）"""
    group = group_of(groups, key, phrase)
    if group is None:
        return None
    return next((p for k, p in phrases_of(text) if k == key and p != phrase and in_group(group, key, p)), None)
