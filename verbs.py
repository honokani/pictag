"""action の文の動詞の形（進行形 is doing / 現在形 does）を数え、多い方にそろえる

- 進行形: 「girl is sitting.」「girl and guy are hugging.」（is / are の後ろの -ing。is なら単数、are なら複数）
- 現在形: 「girl sits.」「girl and guy hug.」（主語のすぐ後ろの動詞）。s の無い「girl sit」も現在形として数え、直すときは s を付ける
- 主語は段落の名前（girl・girl A・guy …）と、その複数形（girls）、代名詞（he・she・it・they・both）。and やカンマでつないでもよい
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


class Clause(NamedTuple):
    """形の分かる文（主語と動詞）1つ"""
    form: str        # PROGRESSIVE / PRESENT
    sure: bool       # 機械で直してよいか（False は迷う）
    flip: tuple      # もう一方の形にする置き換え ((始め, 終わり, 文字), …)
    fix: tuple = ()  # 形はそのままで、主語に合わせる置き換え（girl sit → girl sits）


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


def progressive_clause(line, m, stop):
    """is / are + -ing の文。is going to・辞書に無い動詞・離れた and は迷う"""
    aux, adv, verb = m.group(1), m.group(2), m.group(3)
    plural = aux.lower() == 'are'
    if verb.lower() == 'being':  # 受け身（is being carried → is carried）
        end = m.end(3) + len(line[m.end(3):]) - len(line[m.end(3):].lstrip())
        return Clause(PROGRESSIVE, True, ((m.start(3), end, ''),))
    lemma, sure = (lemma_of(verb), True) if is_gerund(verb) else (lemma_of(verb, oov=True), False)
    if lemma is None:
        return None
    sure = sure and not (lemma == 'go' and re.match(r'\s+to\b', line[m.end():]))  # is going to（これからすること）

    def present(lem):
        return lem if plural else inflect(lem, 'VBZ')

    edits, last = [(m.start(1), m.end(3), ' '.join(filter(None, [adv, present(lemma)])))], m.end()
    for c in CHAIN.finditer(line, m.end(), stop):
        if is_gerund(c.group(2)):
            sure = sure and not line[last:c.start()].strip()  # 動詞のすぐ後ろの and だけ確か
            edits.append((c.start(2), c.end(2), present(lemma_of(c.group(2)))))
            last = c.end()
    return Clause(PROGRESSIVE, sure, tuple(edits))


def present_clause(line, m, stop, names):
    """主語 + 現在形の文。s の付け方が主語と合わなければ fix で直す。体の部分の語・離れた and は迷う"""
    w1, w2 = m['w1'], m['w2']
    if found := present_verb(w1):
        adv, (start, end) = None, m.span('w1')
    elif w2 and is_adverb(w1) and (found := present_verb(w2)):
        adv, (start, end) = w1, m.span('w2')
    else:
        return None
    lemma, with_s = found
    plural = is_plural(m['subj'], names)
    sure = line[start:end].lower() not in BODY_PARTS

    def right(lem):  # 主語に合う現在形
        return lem if plural else inflect(lem, 'VBZ')

    flip = [(m.start('w1'), end, ' '.join(filter(None, ['are' if plural else 'is', adv, inflect(lemma, 'VBG')])))]
    fix = [(start, end, right(lemma))] if line[start:end].lower() != right(lemma) else []
    last = end
    for c in CHAIN.finditer(line, end, stop):
        chained = present_verb(c.group(2))
        if chained is None or chained[1] != with_s:
            continue
        sure = sure and not line[last:c.start()].strip()
        flip.append((c.start(2), c.end(2), inflect(chained[0], 'VBG')))
        if c.group(2).lower() != right(chained[0]):
            fix.append((c.start(2), c.end(2), right(chained[0])))
        last = c.end()
    return Clause(PRESENT, sure, tuple(flip), tuple(fix))


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


def convert(line, subjects, target):
    """line の文の動詞を target の形にした (文, 確か)。変える所が無ければ None"""
    picked = [(c.flip if c.form != target else c.fix, c.sure) for c in clauses(line, subjects)]
    edits = [edit for flip, _ in picked for edit in flip]
    if not edits:
        return None
    text = reduce(lambda s, e: s[:e[0]] + e[2] + s[e[1]:], sorted(edits, reverse=True), line)
    return text, all(sure for flip, sure in picked if flip)


def count_forms(lines, subjects):
    """文の形の数 Counter({PROGRESSIVE: n, PRESENT: m})"""
    return Counter(c.form for line in lines for c in clauses(line, subjects))


def majority(counts):
    """多い方の形（同じ数・どちらも無ければ None）"""
    progressive, present = counts[PROGRESSIVE], counts[PRESENT]
    return PROGRESSIVE if progressive > present else PRESENT if present > progressive else None


def survey(lines, subjects):
    """[(行の印, 文)] の形を数え、多い方にそろえる案を作る: ({形: 数}, 多い方, [(行の印, 前, 後, 確か)])"""
    counts = count_forms([line for _, line in lines], subjects)
    target = majority(counts)
    changes = [] if target is None else [(key, line, *converted) for key, line in lines
                                         if (converted := convert(line, subjects, target))]
    return {PROGRESSIVE: counts[PROGRESSIVE], PRESENT: counts[PRESENT]}, target, changes
