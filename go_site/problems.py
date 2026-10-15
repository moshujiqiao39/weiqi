"""死活与手筋。正解都短，方便在页面上一步步对。"""

from __future__ import annotations


def _straight_three() -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """外围和内圈。中间一排 (2,2)(3,2)(4,2) 是空的。"""
    outer: list[tuple[int, int]] = []
    inner: list[tuple[int, int]] = []
    for x in range(7):
        outer.extend([(x, 0), (x, 4)])
    for y in range(1, 4):
        outer.extend([(0, y), (6, y)])
    for x in range(1, 6):
        inner.extend([(x, 1), (x, 3)])
    inner.extend([(1, 2), (5, 2)])
    return outer, inner


_OUTER, _INNER = _straight_three()


PROBLEMS: list[dict] = [
    {
        "id": "life-01",
        "category": "死活",
        "title": "直三做活",
        "level": "12级",
        "size": 7,
        "black": _INNER,
        "white": _OUTER,
        "intro": "黑先。这块棋只剩横着的三个空点，要点只有一个。",
        "fail": "直三做活要占中间。下在边上，对方点中心就死了。",
        "success": "左右两头都成了真眼，这块棋活了。",
        "solution": [
            {"moves": [[3, 2]], "note": "占住中间。", "reply": None},
        ],
    },
    {
        "id": "life-02",
        "category": "死活",
        "title": "点死直三",
        "level": "10级",
        "size": 7,
        "black": _OUTER,
        "white": _INNER,
        "intro": "黑先。白棋的眼位是直三，点中就要杀，点偏就让白棋做活。",
        "fail": "杀直三也是点正中间。点在边上，白棋再占中心就能活。",
        "success": "白棋被点在眼位中央，做不出两只眼。",
        "solution": [
            {"moves": [[3, 2]], "note": "点在三空的正中。", "reply": None},
        ],
    },
    {
        "id": "life-03",
        "category": "死活",
        "title": "边线倒扑",
        "level": "6级",
        "size": 7,
        "black": [(2, 0), (2, 1), (0, 2), (2, 2), (1, 3)],
        "white": [(1, 0), (1, 1), (1, 2)],
        "intro": "黑先。白棋看着还有两气，要先送一子进去。",
        "fail": "先在角上扑。白棋若提掉这颗子，你再把整块提回来。",
        "success": "白棋提掉扑子之后，自己只剩一口气，被你倒扑吃净。",
        "solution": [
            {
                "moves": [[0, 0]],
                "note": "扑进角上。这一子本身会被提掉。",
                "reply": [0, 1],
                "reply_note": "白棋提掉扑子。",
            },
            {
                "moves": [[0, 0]],
                "note": "再落回这一点，四颗白子一起被吃。",
                "reply": None,
            },
        ],
    },
    {
        "id": "life-04",
        "category": "死活",
        "title": "气尽的一块",
        "level": "15级",
        "size": 7,
        "black": [(1, 0), (2, 0), (0, 1), (1, 2), (2, 2)],
        "white": [(1, 1), (2, 1)],
        "intro": "黑先。这两颗白子连在一起，只剩最后一口气。",
        "fail": "下在白棋唯一的气上，才能把整块提掉。",
        "success": "两颗白子一起被提掉。一块棋没有气，就会整块拿走。",
        "solution": [
            {"moves": [[3, 1]], "note": "打在最后一口气上。", "reply": None},
        ],
    },
    {
        "id": "te-01",
        "category": "手筋",
        "title": "提子",
        "level": "18级",
        "size": 7,
        "black": [(2, 2), (3, 3), (4, 2)],
        "white": [(3, 2)],
        "intro": "黑先。白子只剩一口气。",
        "fail": "提子要下在对方最后的那口气上。",
        "success": "白子被提掉。只剩一口气的子，补上那口气就能吃。",
        "solution": [
            {"moves": [[3, 1]], "note": "提。", "reply": None},
        ],
    },
    {
        "id": "te-02",
        "category": "手筋",
        "title": "边上提子",
        "level": "18级",
        "size": 7,
        "black": [(0, 0), (1, 1)],
        "white": [(1, 0)],
        "intro": "黑先。边上也是一样，白子只剩右边一口气。",
        "fail": "白子贴在边上，气更少，补上剩下的那口气。",
        "success": "边上的白子被提掉。越靠近边，气越少。",
        "solution": [
            {"moves": [[2, 0]], "note": "提。", "reply": None},
        ],
    },
    {
        "id": "te-03",
        "category": "手筋",
        "title": "长出",
        "level": "17级",
        "size": 7,
        "black": [(2, 1)],
        "white": [(1, 1), (3, 1), (2, 2)],
        "intro": "黑先。自己的子被打吃了，不长出去就会被提。",
        "fail": "这颗黑子只剩上面一口气，要往上长。",
        "success": "长出去之后有了两气，暂时安全。被打吃时，先看能不能长、连或者反提。",
        "solution": [
            {"moves": [[2, 0]], "note": "向上长出。", "reply": None},
        ],
    },
    {
        "id": "te-04",
        "category": "手筋",
        "title": "连回",
        "level": "16级",
        "size": 7,
        "black": [(0, 0), (1, 1)],
        "white": [(2, 0), (0, 1)],
        "intro": "黑先。角上这一子被打吃，旁边还有自己的棋，把它们连上。",
        "fail": "不要在别处跑。和旁边的黑子连上，两块就合成一块。",
        "success": "连上之后不再是一口气。连接是逃子最常用的办法。",
        "solution": [
            {"moves": [[1, 0]], "note": "连回旁边的黑子。", "reply": None},
        ],
    },
    {
        "id": "te-05",
        "category": "手筋",
        "title": "双打吃",
        "level": "14级",
        "size": 7,
        "black": [(1, 0), (0, 1), (2, 1), (3, 2), (1, 3), (2, 3)],
        "white": [(1, 1), (2, 2)],
        "intro": "黑先。两颗白子不相连，但最后一口气是同一个点。",
        "fail": "找两块棋共同的那口气。下在那里，两颗一起提掉。",
        "success": "一子同时吃掉两颗白子。这种手筋叫双打。",
        "solution": [
            {"moves": [[1, 2]], "note": "打在共同的气上。", "reply": None},
        ],
    },
    {
        "id": "te-06",
        "category": "手筋",
        "title": "征子",
        "level": "9级",
        "size": 9,
        "black": [(1, 0), (0, 1), (2, 2)],
        "white": [(1, 1)],
        "intro": "黑先。白子每逃一步都还是被打吃，要一路追到底。",
        "fail": "征子必须每步都打吃。下错方向，白子就逃出征子了。",
        "success": "白子沿边逃不出去，最后被征吃。征子之前要看路上有没有对方的援军。",
        "solution": [
            {
                "moves": [[2, 1]],
                "note": "打吃。",
                "reply": [1, 2],
                "reply_note": "白棋只剩这一口气。",
            },
            {
                "moves": [[1, 3]],
                "note": "继续打吃。",
                "reply": [0, 2],
                "reply_note": "白棋再长。",
            },
            {
                "moves": [[0, 3]],
                "note": "征吃净。",
                "reply": None,
            },
        ],
    },
]


def by_id(problem_id: str) -> dict:
    for problem in PROBLEMS:
        if problem["id"] == problem_id:
            return problem
    raise KeyError(problem_id)


def summary() -> list[dict]:
    rows = []
    for problem in PROBLEMS:
        rows.append(
            {
                "id": problem["id"],
                "category": problem["category"],
                "title": problem["title"],
                "level": problem["level"],
                "size": problem["size"],
            }
        )
    return rows
