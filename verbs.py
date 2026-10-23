"""action の文の動詞の形（進行形 is doing / 現在形 does）を動詞ごとに数え、それぞれ多い方にそろえる

- 進行形: 「girl is sitting.」「girl and guy are hugging.」（is / are の後ろの -ing。is なら単数、are なら複数）
- 現在形: 「girl sits.」「girl and guy hug.」（主語のすぐ後ろの動詞）。s の無い「girl sit」も現在形として数え、直すときは s を付ける
- 主語は段落の名前（girl・girl A・guy …）と、その複数形（girls）、代名詞（he・she・it・they・both）。and やカンマでつないでもよい
- and でつないだ動詞（girl is sitting and smiling.）も1つずつ数え、1つずつ直す（girl sits and is smiling.）。
  受け身（is being carried）は、後ろの動詞（carry）として数える
- 綴りの変化（sitting → sit、lying → lie、has など）は lemminflect（英語の辞書）で引く
- 機械では迷う文（and の後ろの離れた動詞・is going to・辞書に無い動詞・体の部分の語）は、直す案を「迷う」として出す
"""
import re
from collections import Counter
from functools import lru_cache, reduce
from typing import NamedTuple

from lemminflect import getInflection, getLemma

PROGRESSIVE, PRESENT = 'progressive', 'present'
# 状態を表す動詞（進行形にしない。girl has long hair を is having にしない）
STATIVE = {'be', 'have', 'know', 'like', 'love', 'hate', 'want', 'need', 'seem', 'belong', 'own', 'contain', 'consist',
           'mean', 'prefer', 'understand', 'believe', 'remember', 'resemble'}
# 主語のすぐ後ろでは名詞のことが多い語（girl hand on chest）。動詞として直す案は「迷う」にする
BODY_PARTS = {'hand', 'arm', 'head', 'face', 'back', 'foot', 'eye', 'elbow', 'shoulder', 'knee', 'finger', 'nose',
              'mouth', 'lip', 'chin', 'neck', 'chest', 'hip', 'toe', 'leg', 'palm', 'thumb', 'hair', 'body', 'breast'}
PRONOUNS = {'he': False, 'she': False, 'it': False, 'they': True, 'both': True}  # 代名詞と、複数か
ADVERBS = {'also', 'still', 'just', 'both', 'all', 'only', 'often', 'always', 'even', 'now'}
ADVERB = r'(?:[a-z]+ly|also|still|just|both|all)'
WORD = r'[a-z]+'
AUX = re.compile(rf'\b(is|are)\s+(?:({ADVERB})\s+)?({WORD}ing)\b', re.IGNORECASE)  # 進行形
CHAIN = re.compile(rf'\band\s+(?:({ADVERB})\s+)?({WORD})\b', re.IGNORECASE)  # and でつないだ動詞
END = re.compile(r'[,;.!?]')  # 文の区切り


class Verb(NamedTuple):
    """文の中の動詞1つ（and でつないだ動詞も1つずつ）"""
    lemma: str
    word: tuple      # 動詞の語の (始め, 終わり)
    lead: int        # 進行形にするとき is / are を入れる所（副詞があればその前）
    aux: tuple = ()  # 自分の is / are の (始め, lead)（進行形の先頭の動詞だけ）


class Clause(NamedTuple):
    """形の分かる文（主語と動詞）1つ"""
    form: str            # PROGRESSIVE / PRESENT
    sure: bool           # 機械で直してよいか（False は迷う）
    plural: bool         # 主語が複数か（is / are と、s の有無）
    verbs: tuple         # 動詞（先頭から）
    passive: tuple = ()  # 受け身（is being carried）を現在形にする置き換え (始め, 終わり, 文字)


@lru_cache(maxsize=None)
def lemma_of(word, oov=False):
    """動詞としての原形（辞書に無ければ None。oov なら綴りから推す）"""
    lemmas = getLemma(word.lower(), upos='VERB', lemmatize_oov=oov)
    return lemmas[0] if lemmas else None


@lru_cache(maxsize=None)
def forms_of(lemma, tag):
    """原形 lemma の tag（VBZ: sits / VBG: sitting / NNS: girls）の形"""
    return getInflection(lemma, tag=tag)


def inflect(lemma, tag):
    forms = forms_of(lemma, tag)
    return forms[0] if forms else lemma


def is_gerund(word):
    """辞書にある動詞の -ing の形か"""
    lemma = lemma_of(word)
    return bool(lemma) and word.lower() in forms_of(lemma, 'VBG')


def present_verb(word):
    """現在形の動詞なら (原形, s が付いているか)。違えば（過去形・-ing・状態の動詞・辞書に無い語）None"""
    lemma = lemma_of(word)
    if not lemma or lemma in STATIVE:
        return None
    if word.lower() == lemma:
        return lemma, False
    return (lemma, True) if word.lower() in forms_of(lemma, 'VBZ') else None


def is_adverb(word):
    w = word.lower()
    return w in ADVERBS or (w.endswith('ly') and not lemma_of(w))


@lru_cache(maxsize=None)
def subject_regex(names):
    """主語（名前・その複数形・代名詞。and やカンマでつないでもよい）で始まる文と、その後ろの2語"""
    words = sorted({*names, *(inflect(n, 'NNS') for n in names if ' ' not in n), *PRONOUNS}, key=len, reverse=True)
    one = rf"(?:the\s+)?(?:{'|'.join(map(re.escape, words))})"
    return re.compile(rf"(?:^\s*(?:-\s*)?|(?<=[,;.!?]\s)|(?<=\band\s))(?P<subj>{one}(?:(?:\s*,\s*|\s+and\s+){one})*)"
                      rf"\s+(?P<w1>{WORD})\b(?:\s+(?P<w2>{WORD})\b)?", re.IGNORECASE)


def is_plural(subject, names):
    """主語が複数か（and・カンマでつないだもの、複数形、they・both）"""
    s = subject.lower()
    if re.search(r',|\band\b', s):
        return True
    word = re.sub(r'^the\s+', '', s)
    return PRONOUNS.get(word, word not in names)


def chained(c, lemma):
    """and でつないだ動詞（CHAIN の一致 c）"""
    return Verb(lemma, c.span(2), c.start(1) if c.group(1) else c.start(2))


def progressive_clause(line, m, stop):
    """is / are + -ing の文。is going to・辞書に無い動詞・離れた and は迷う"""
    adv, verb = m.group(2), m.group(3)
    plural = m.group(1).lower() == 'are'
    lead = m.start(2) if adv else m.start(3)

    def head(lemma):
        return Verb(lemma, m.span(3), lead, (m.start(1), lead))

    if verb.lower() == 'being':  # 受け身（is being carried → is carried）。後ろの動詞（carry）として数える
        end = m.end(3) + len(line[m.end(3):]) - len(line[m.end(3):].lstrip())
        done = re.match(WORD, line[end:], re.IGNORECASE)
        return Clause(PROGRESSIVE, True, plural, (head((done and lemma_of(done[0], oov=True)) or 'be'),),
                      (m.start(3), end, ''))
    lemma, sure = (lemma_of(verb), True) if is_gerund(verb) else (lemma_of(verb, oov=True), False)
    if lemma is None:
        return None
    sure = sure and not (lemma == 'go' and re.match(r'\s+to\b', line[m.end():]))  # is going to（これからすること）
    verbs, last = [head(lemma)], m.end()
    for c in CHAIN.finditer(line, m.end(), stop):
        if is_gerund(c.group(2)):
            sure = sure and not line[last:c.start()].strip()  # 動詞のすぐ後ろの and だけ確か
            verbs.append(chained(c, lemma_of(c.group(2))))
            last = c.end()
    return Clause(PROGRESSIVE, sure, plural, tuple(verbs))


def present_clause(line, m, stop, names):
    """主語 + 現在形の文。体の部分の語・離れた and は迷う"""
    w1, w2 = m['w1'], m['w2']
    if found := present_verb(w1):
        word = m.span('w1')
    elif w2 and is_adverb(w1) and (found := present_verb(w2)):
        word = m.span('w2')
    else:
        return None
    lemma, with_s = found
    sure = line[slice(*word)].lower() not in BODY_PARTS
    verbs, last = [Verb(lemma, word, m.start('w1'))], word[1]
    for c in CHAIN.finditer(line, word[1], stop):
        verb = present_verb(c.group(2))
        if verb is None or verb[1] != with_s:
            continue
        sure = sure and not line[last:c.start()].strip()
        verbs.append(chained(c, verb[0]))
        last = c.end()
    return Clause(PRESENT, sure, is_plural(m['subj'], names), tuple(verbs))


def clauses(line, subjects):
    """line の中の、形の分かる文（line の順）。subjects は主語になる名前"""
    names = tuple(sorted({s.lower() for s in subjects}))
    heads = sorted([(m.start(), 0, m) for m in AUX.finditer(line)]
                   + [(m.start('subj'), 1, m) for m in subject_regex(names).finditer(line)], key=lambda h: h[:2])

    def clause(k):
        _, kind, m = heads[k]
        punctuation = END.search(line, m.end())
        stop = min([*([heads[k + 1][0]] if k + 1 < len(heads) else []),
                    punctuation.start() if punctuation else len(line)])
        return progressive_clause(line, m, stop) if kind == 0 else present_clause(line, m, stop, frozenset(names))

    return [c for c in map(clause, range(len(heads))) if c]


def edits_of(line, clause, target_of):
    """clause の動詞を、それぞれ target_of(原形) の形（None は今の形のまま）にする置き換え [(始め, 終わり, 文字, 原形)]

    原形は、形か s を変えた動詞のもの（前の動詞の形が変わって is / are を足すだけのものは None）
    """
    if clause.passive:
        verb = clause.verbs[0]
        return [(*clause.passive, verb.lemma)] if target_of(verb.lemma) == PRESENT else []
    edits, shared = [], False  # shared: 前の動詞が進行形（続く -ing は、その is / are を分け合う）
    for verb in clause.verbs:
        form = target_of(verb.lemma) or clause.form
        if form == PROGRESSIVE:
            if not shared and not verb.aux:
                edits.append((verb.lead, verb.lead, 'are ' if clause.plural else 'is ', None))
            if clause.form == PRESENT:
                edits.append((*verb.word, inflect(verb.lemma, 'VBG'), verb.lemma))
        else:
            present = verb.lemma if clause.plural else inflect(verb.lemma, 'VBZ')  # 主語に合う現在形
            if verb.aux:
                edits.append((*verb.aux, '', None))
            if line[slice(*verb.word)].lower() != present:
                edits.append((*verb.word, present, verb.lemma))
        shared = form == PROGRESSIVE
    return edits


def rewrite(line, found, target_of):
    """line（found はその clauses）の動詞を、それぞれ target_of(原形) の形にした (文, 確か, 形か s を変えた動詞の原形)

    変える所が無ければ None
    """
    picked = [(edits_of(line, c, target_of), c.sure) for c in found]
    edits = [edit for each, _ in picked for edit in each]
    if not edits:
        return None
    text = reduce(lambda s, e: s[:e[0]] + e[2] + s[e[1]:], sorted(edits, key=lambda e: e[:2], reverse=True), line)
    return text, all(sure for each, sure in picked if each), tuple(dict.fromkeys(e[3] for e in edits if e[3]))


def convert(line, subjects, target):
    """line の文の動詞を target の形にした (文, 確か)。target は形か、原形からその形を返す関数（None は今の形のまま）

    変える所が無ければ None
    """
    found = rewrite(line, clauses(line, subjects), target if callable(target) else lambda _: target)
    return found and found[:2]


def count_forms(lines, subjects):
    """文の形の数 Counter({PROGRESSIVE: n, PRESENT: m})"""
    return Counter(c.form for line in lines for c in clauses(line, subjects))


def majority(counts):
    """多い方の形（同じ数・どちらも無ければ None）"""
    progressive, present = counts[PROGRESSIVE], counts[PRESENT]
    return PROGRESSIVE if progressive > present else PRESENT if present > progressive else None


def survey(lines, subjects, target=None):
    """[(行の印, 文)] の動詞を動詞ごとに数え、それぞれ多い方の形にそろえる案を作る:
    ({原形: {形: 数}}, {原形: そろえる形}, [(行の印, 前, 後, 確か, (形か s を変える動詞の原形, …))])

    同じ数の動詞は target の形にする。target が無ければ、その動詞のそろえる形は None で、案は無い
    （画面がどちらにするか聞いて、target を渡し直す）
    """
    found = [(key, line, clauses(line, subjects)) for key, line in lines]
    tally = Counter((verb.lemma, c.form) for *_, cs in found for c in cs for verb in c.verbs)
    counts = {lemma: {PROGRESSIVE: tally[lemma, PROGRESSIVE], PRESENT: tally[lemma, PRESENT]} for lemma, _ in tally}
    targets = {lemma: majority(n) or target for lemma, n in counts.items()}
    if None in targets.values():
        return counts, targets, []
    return counts, targets, [(key, line, *changed) for key, line, cs in found
                             if (changed := rewrite(line, cs, targets.get))]
