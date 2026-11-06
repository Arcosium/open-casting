import json
from pathlib import Path

import pytest

from app import engine as rules


@pytest.mark.parametrize('word', ['라면','달','닭','삶','넓다','곬','핥다','읊다','싫다','ㄹ','ᄅ','ᆰ','\u1105\u1161'])
def test_rieul_initial_final_and_compounds(word):
    assert rules.has_rieul(word)


@pytest.mark.parametrize('word', ['사과','수박','포도','바나나','김밥','축구',''])
def test_no_rieul(word):
    assert not rules.has_rieul(word)


def test_word_bank_and_validation():
    assert len(rules.WORDS) >= 8
    for words in rules.WORDS.values():
        assert len(set(words)) >= 40
        assert any(rules.has_rieul(word) for word in words)
        assert any(not rules.has_rieul(word) for word in words)
    assert rules.valid_word(' 사 과 ', 'fruit', [])
    assert not rules.valid_word('딸기','fruit',[])
    assert not rules.valid_word('사과','animal',[])
    assert not rules.valid_word('사과','fruit',['사과'])
    assert not rules.valid_word('없는단어','fruit',[])


def test_rules_are_pure_and_score_uses_server_clock():
    state = rules.start('no-rieul','seed',100,1000)
    category = state['categories'][0]
    word = next(w for w in rules.WORDS[category] if not rules.has_rieul(w))
    updated, score, done, _ = rules.answer('no-rieul',state,0,word,102,1000)
    assert score == 150 and not done
    assert not state['used'] and updated['used'] == [word]
    _, score, done, _ = rules.answer('no-rieul',state,0,word,108.5,1000)
    assert score == 0 and done
    _, score, done, _ = rules.answer('no-rieul',state,0,word,107.5,1000)
    assert score == 100 and not done  # Network grace never grants extra speed points.


def test_ore_determinism_distance_points_and_duplicate():
    board = rules.ore_board('same')
    assert board == rules.ore_board('same') and board != rules.ore_board('other')
    assert len(board) == 12 and len(set(board)) == 12
    state = rules.start('ore-hunt','same',10,1000)
    score = 0
    for cell, ore in board.items():
        state, score, done, result = rules.dig(state,score,'same',cell%10,cell//10,11,1000)
        assert result['points'] == rules.POINTS[ore]
    assert score == sum(rules.POINTS[ore] for ore in board.values()) and done
    with pytest.raises(rules.RuleError, match='already_dug'):
        rules.dig(state,score,'same',cell%10,cell//10,12,1000)
    blank = next(i for i in range(100) if i not in board)
    state = rules.start('ore-hunt','same',10,1000)
    _, _, _, result = rules.dig(state,0,'same',blank%10,blank//10,11,1000)
    assert result == {'distance': min(abs(blank%10-i%10)+abs(blank//10-i//10) for i in board)}


def test_majority_ties_and_empty():
    assert rules.majority([3,3,1,0]) == [0,1]
    assert rules.majority([0,0,0,0]) == []
    assert rules.telepathy_score([1,2], [[3,3,0,0],[0,0,5,0]]) == 200


def test_i18n_key_parity_and_no_missing_ui_keys():
    root = Path(__file__).parents[1] / 'app/static'
    ko = json.loads((root/'i18n/ko.json').read_text())
    en = json.loads((root/'i18n/en.json').read_text())
    assert ko.keys() == en.keys()
    assert all(ko.values()) and all(en.values())
    import re
    js = (root/'app.js').read_text()
    literals = re.findall(r"\b(?:tr|t|button|pageTop)\('([a-z_][a-z_0-9-]*)'(?=[,)])", js)
    for key in literals:
        assert key in ko
