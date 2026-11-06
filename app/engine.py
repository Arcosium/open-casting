"""Mission rules. No HTTP, database, browser clock or network state."""
import json
import random
import unicodedata
from pathlib import Path

WORDS = json.loads((Path(__file__).parent / "words_ko.json").read_text())
TEMPLATES = ("no-rieul", "telepathy", "ore-hunt")
POINTS = {"iron": 10, "gold": 30, "gem": 100}


class RuleError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


def normalize(text):
    return "".join(unicodedata.normalize("NFC", text).split())


def has_rieul(text):
    for char in unicodedata.normalize("NFC", text):
        index = ord(char) - 0xAC00
        if char in "ㄹᄅᆯᆰᆱᆲᆳᆴᆵᆶ" or (0 <= index <= 11171 and (index // 588 == 5 or index % 28 in range(8, 16))):
            return True
    return False


def valid_word(text, category, used):
    word = normalize(text)
    return word in WORDS[category] and word not in used and not has_rieul(word)


def ore_board(seed):
    rng = random.Random(f"{seed}")
    cells = rng.sample(range(100), 12)
    return dict(zip(cells, ["iron"] * 7 + ["gold"] * 4 + ["gem"]))


def start(template, seed, now, ends_at):
    state = {"index": 0, "used": [], "answers": [], "digs": {}, "prompt_at": now, "reason": "", "cleared": 0}
    if template == "no-rieul":
        state["categories"] = random.Random(str(seed)).sample(list(WORDS), 8)
    # Prompt limits (no-rieul 7 s, telepathy 5 s) include 1.5 s network grace; the client shows the limit without it.
    state["deadline"] = min(ends_at, now + {"no-rieul": 8.5, "telepathy": 6.5, "ore-hunt": 60}[template])
    return state


def majority(counts):
    if not counts or max(counts, default=0) == 0:
        return []
    return [i for i, count in enumerate(counts) if count == max(counts)]


def telepathy_score(answers, counts):
    return sum(100 for q, option in enumerate(answers) if option in majority(counts[q]))


def answer(template, state, score, text, now, ends_at):
    if template == "ore-hunt":
        raise RuleError("wrong_action")
    state = json.loads(json.dumps(state))
    if now >= state["deadline"] or now >= ends_at:
        state["reason"] = "timeout"
        return state, score, True, None
    if template == "no-rieul":
        category = state["categories"][state["index"]]
        if not valid_word(text, category, state["used"]):
            state["reason"] = "invalid_word"
            return state, score, True, None
        state["used"].append(normalize(text))
        state["cleared"] += 1
        score += 100 + max(0, int((7 - (now - state["prompt_at"])) * 10))
        vote = None
    else:
        if type(text) is not int or text not in range(4):
            raise RuleError("invalid_option")
        vote = (state["index"], text)
        state["answers"].append(text)
    state["index"] += 1
    done = state["index"] == (8 if template == "no-rieul" else 10)
    state["prompt_at"] = now
    state["deadline"] = min(ends_at, now + (8.5 if template == "no-rieul" else 6.5))
    if done:
        state["reason"] = "complete"
    return state, score, done, vote


def dig(state, score, seed, x, y, now, ends_at):
    state = json.loads(json.dumps(state))
    if now >= state["deadline"] or now >= ends_at:
        state["reason"] = "timeout"
        return state, score, True, None
    if type(x) is not int or type(y) is not int or x not in range(10) or y not in range(10):
        raise RuleError("invalid_cell")
    cell = y * 10 + x
    if str(cell) in state["digs"]:
        raise RuleError("already_dug")
    board = ore_board(seed)
    if cell in board:
        result = {"ore": board[cell], "points": POINTS[board[cell]]}
        score += result["points"]
    else:
        hidden = [i for i in board if str(i) not in state["digs"]]
        result = {"distance": min((abs(x - i % 10) + abs(y - i // 10) for i in hidden), default=0)}
    state["digs"][str(cell)] = result
    done = len(state["digs"]) == 25 or sum("ore" in d for d in state["digs"].values()) == 12
    if done:
        state["reason"] = "complete"
    return state, score, done, result
