"""「1つだけ」のグループ: 同じキーの語句のうち、1枚の画像の1段落に1つだけ置けるもの（例: looks の standing / sitting / lying）

グループは {key, phrases}。1つの語句が入るグループは、キーごとに1つまで（重なれば1つにまとめる）
"""
from functools import reduce

from caption_format import phrases_of


def normalize_groups(groups):
    """同じキーで語句の重なるグループを1つにまとめ（先に出たグループの位置へ）、語句が2つ未満のグループを除く"""
    def merge(merged, group):
        phrases = list(dict.fromkeys(group['phrases']))
        hits = [i for i, g in enumerate(merged) if g['key'] == group['key'] and set(g['phrases']) & set(phrases)]
        if not hits:
            return [*merged, {'key': group['key'], 'phrases': phrases}]
        joined = {'key': group['key'], 'phrases': list(dict.fromkeys([p for i in hits for p in merged[i]['phrases']] + phrases))}
        return [joined if i == hits[0] else g for i, g in enumerate(merged) if i == hits[0] or i not in hits]

    return [g for g in reduce(merge, groups, []) if len(g['phrases']) >= 2]


def clean_groups(groups):
    """読み込んだグループのうち形の正しいものだけを残してまとめ直す（手で書き換えたファイルでも落ちないように）"""
    valid = [{'key': g['key'], 'phrases': [p for p in g['phrases'] if isinstance(p, str) and p]}
             for g in groups
             if isinstance(g, dict) and isinstance(g.get('key'), str) and g['key'] and isinstance(g.get('phrases'), list)]
    return normalize_groups(valid)


def group_of(groups, key, phrase):
    """phrase の入っているグループの語句（無ければ空）"""
    return next((g['phrases'] for g in groups if g['key'] == key and phrase in g['phrases']), [])


def blocked_by(groups, text, key, phrase):
    """入力の key の行に、phrase と同じグループの別の語句があればそれを返す（無ければ None）"""
    mates = set(group_of(groups, key, phrase)) - {phrase}
    return next((p for k, p in phrases_of(text) if k == key and p in mates), None)
