"""Krea2 用キャプションの整形（表の1行 → 構造化テキスト）

1行のうち True の項目を (大kind, 中kind, 小kind, 値) で受け取り、辞書の順を保って次の形にする。

    girl:
      - body: long black hair, bare hands

- 大kind ごとに段落を分け、空行でつなぐ
- 中kind が空の値は、キーなしで1行ずつ並べる
- 小kind の値はスペースでつなぎ、後ろに小kind の名前を付ける（hair の long と black → long black hair）
"""


def group_in_order(pairs):
    """(キー, 値) を、キーが最初に出た順にまとめる"""
    groups = {}
    for key, value in pairs:
        groups.setdefault(key, []).append(value)
    return groups.items()


def entry_key(name, value):
    """名前があれば名前でまとめ、空なら値ごとに分けるキー"""
    return (name, "") if name else ("", value)


def merge_values(small, values):
    return " ".join([*values, small])


def render_phrases(small_values):
    """中kind の中身 [(小kind, 値)] を語句にする"""
    groups = group_in_order((entry_key(small, value), value) for small, value in small_values)
    return [merge_values(small, values) if small else values[0] for (small, _), values in groups]


def render_lines(mid_entries):
    """大kind の中身 [(中kind, 小kind, 値)] を「  - ...」の行にする"""
    groups = group_in_order((entry_key(mid, value), (small, value)) for mid, small, value in mid_entries)
    return [
        f"  - {mid}: {', '.join(render_phrases(entries))}" if mid else f"  - {entries[0][1]}"
        for (mid, _), entries in groups
    ]


def render_caption(items):
    sections = group_in_order((big, (mid, small, value)) for big, mid, small, value in items)
    return "\n\n".join("\n".join([f"{big}:", *render_lines(entries)]) for big, entries in sections)
