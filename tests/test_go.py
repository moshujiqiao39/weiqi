import unittest

import json

from go_site.ai import choose_move
from go_site.browser_api import handle
from go_site.engine import BLACK, WHITE, Board, is_eye, idx
from go_site.play import Practice
from go_site.problems import PROBLEMS
from go_site.ranks import RANKS, katago_profile


class RulesTest(unittest.TestCase):
    def test_capture_and_suicide_and_score(self):
        board = Board(7)
        board.setup([(2, 2), (3, 3), (4, 2)], [(3, 2)], BLACK)
        self.assertIsNone(board.play(3, 1))
        self.assertEqual(board.grid[idx(3, 2, 7)], 0)
        self.assertEqual(board.captures[BLACK], 1)

        eye = Board(7)
        eye.setup([], [(1, 0), (0, 1), (2, 1), (1, 2)], BLACK)
        self.assertEqual(eye.play(1, 1), "不能下在这里")

        empty = Board(9)
        score = empty.score()
        self.assertEqual(score["winner"], "W")
        self.assertAlmostEqual(score["white"], 7.5)

    def test_ko(self):
        board = Board(7)
        board.setup(
            [(1, 2), (2, 1), (2, 3)],
            [(2, 2), (3, 1), (4, 2), (3, 3)],
            BLACK,
        )
        self.assertIsNone(board.play(3, 2))
        self.assertEqual(board.grid[idx(2, 2, 7)], 0)
        self.assertEqual(board.play(2, 2), "不能下在这里")

    def test_ranks(self):
        self.assertEqual(len(RANKS), 27)
        self.assertEqual(RANKS[0], "18级")
        self.assertEqual(RANKS[-1], "9段")
        self.assertEqual(katago_profile("18级"), "rank_18k")
        self.assertEqual(katago_profile("1级"), "rank_1k")
        self.assertEqual(katago_profile("1段"), "rank_1d")
        self.assertEqual(katago_profile("9段"), "rank_9d")


class ProblemTest(unittest.TestCase):
    def test_every_solution(self):
        self.assertGreaterEqual(len(PROBLEMS), 10)
        for problem in PROBLEMS:
            with self.subTest(problem=problem["id"]):
                session = Practice(problem["id"])
                while not session.done:
                    step = problem["solution"][session.step]
                    x, y = step["moves"][0]
                    err = session.move(x, y)
                    self.assertIsNone(err, problem["title"])
                self.assertTrue(session.success)

    def test_wrong_move_does_not_change_board(self):
        session = Practice("life-01")
        before = session.board.grid[:]
        err = session.move(2, 2)
        self.assertIsNotNone(err)
        self.assertEqual(session.board.grid, before)

    def test_straight_three_eyes(self):
        live = Practice("life-01")
        live.solve()
        eyes = [
            (i % 7, i // 7)
            for i, _ in enumerate(live.board.grid)
            if is_eye(live.board.grid, i, BLACK, 7)
        ]
        self.assertEqual(len(eyes), 2)
        dead = Practice("life-02")
        dead.solve()
        white_eyes = [
            i for i, _ in enumerate(dead.board.grid) if is_eye(dead.board.grid, i, WHITE, 7)
        ]
        self.assertEqual(white_eyes, [])

    def test_snapback_removes_white(self):
        session = Practice("life-03")
        session.solve()
        self.assertNotIn(WHITE, session.board.grid)


class BrowserApiTest(unittest.TestCase):
    def test_game_and_problem_without_server(self):
        created = json.loads(handle("POST", "/api/games", json.dumps({"size": 9, "rank": "9段", "color": "B", "engine": "builtin"})))
        self.assertEqual(created["status"], 200)
        gid = created["body"]["id"]
        self.assertEqual(created["body"]["state"]["engine"], "builtin")
        moved = json.loads(handle("POST", f"/api/games/{gid}/move", json.dumps({"x": 2, "y": 2})))
        self.assertTrue(moved["body"]["ok"])
        self.assertGreaterEqual(moved["body"]["state"]["moveCount"], 2)
        practice = json.loads(handle("POST", "/api/practice", json.dumps({"id": "life-01"})))
        pid = practice["body"]["id"]
        solved = json.loads(handle("POST", f"/api/practice/{pid}/solve", "{}"))
        self.assertTrue(solved["body"]["state"]["success"])


class AgentTest(unittest.TestCase):
    def test_strong_rank_captures(self):
        board = Board(7)
        board.setup([(2, 2), (3, 3), (4, 2)], [(3, 2)], BLACK)
        x, y, _note = choose_move(board, "9段")
        self.assertEqual((x, y), (3, 1))

    def test_game_stays_legal(self):
        board = Board(9)
        for _ in range(30):
            if board.over:
                break
            x, y, _note = choose_move(board, "5级")
            err = board.play(x, y)
            self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
