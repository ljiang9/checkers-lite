#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkers-lite: 极简英式跳棋 (English draughts) 引擎。

规则 (美式/英式跳棋):
- 8x8 棋盘, 只在深色格走子; 红方在下往上走, 黑方在上往下走。
- 有吃必吃; 连跳; 兵到底线升王; 王可前后走/吃 (兵只能向前吃)。
- 跳入底线即升王, 本回合停止 (不再以王的身份继续跳)。
- 多条可吃路线时可任选一条 (不强制吃子数最多)。
- 对方无子或无合法走法时判胜。

纯标准库。交互为回合制命令行 + --auto 无头 AI 对战演示。
"""

import argparse
import random
import sys

RED, BLACK = "r", "b"
EMPTY = "."
FILES = "abcdefgh"


def opponent(side):
    return "b" if side == "r" else "r"


def new_board():
    """标准开局。"""
    b = [[EMPTY] * 8 for _ in range(8)]
    for r in range(3):
        for c in range(8):
            if (r + c) % 2 == 1:
                b[r][c] = "b"
    for r in range(5, 8):
        for c in range(8):
            if (r + c) % 2 == 1:
                b[r][c] = "r"
    return b


def _in(r, c):
    return 0 <= r < 8 and 0 <= c < 8


def _dirs(piece):
    if piece.isupper():  # 王: 四向
        return [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    if piece == "r":  # 红兵向上
        return [(-1, -1), (-1, 1)]
    return [(1, -1), (1, 1)]  # 黑兵向下


def _gen_captures(board, r, c, piece):
    """返回所有吃子路线, 每条路线是 [(r0,c0),(r1,c1),...]。"""
    res = []

    def dfs(cr, cc, path, taken):
        any_cap = False
        for dr, dc in _dirs(piece):
            mr, mc = cr + dr, cc + dc
            lr, lc = cr + 2 * dr, cc + 2 * dc
            if not _in(lr, lc) or board[lr][lc] != EMPTY:
                continue
            if not _in(mr, mc):
                continue
            mid = board[mr][mc]
            if mid == EMPTY or mid.lower() == piece.lower() or (mr, mc) in taken:
                continue
            any_cap = True
            board[mr][mc] = EMPTY
            board[cr][cc] = EMPTY
            board[lr][lc] = piece
            taken.add((mr, mc))
            last = 0 if piece == "r" else 7
            if not piece.isupper() and lr == last:
                # 跳入底线升王, 回合结束 (美式规则)
                res.append(path + [(lr, lc)])
            else:
                dfs(lr, lc, path + [(lr, lc)], taken)
            board[mr][mc] = mid
            board[cr][cc] = piece
            board[lr][lc] = EMPTY
            taken.discard((mr, mc))
        if not any_cap and len(path) > 1:
            res.append(path)

    dfs(r, c, [(r, c)], set())
    return res


def _gen_quiets(board, r, c, piece):
    res = []
    for dr, dc in _dirs(piece):
        nr, nc = r + dr, c + dc
        if _in(nr, nc) and board[nr][nc] == EMPTY:
            res.append([(r, c), (nr, nc)])
    return res


def legal_moves(board, side):
    """有吃必吃: 只要有吃子路线, 只返回吃子路线。"""
    caps = []
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p != EMPTY and p.lower() == side:
                caps.extend(_gen_captures(board, r, c, p))
    if caps:
        return caps
    quiets = []
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p != EMPTY and p.lower() == side:
                quiets.extend(_gen_quiets(board, r, c, p))
    return quiets


def apply_move(board, path):
    """在 board 上执行路线, 返回吃掉的子数。"""
    (r0, c0) = path[0]
    piece = board[r0][c0]
    caps = 0
    for (r1, c1) in path[1:]:
        if abs(r1 - r0) == 2:  # 跳吃
            board[(r0 + r1) // 2][(c0 + c1) // 2] = EMPTY
            caps += 1
        r0, c0 = r1, c1
    board[path[0][0]][path[0][1]] = EMPTY
    last = 0 if piece == "r" else 7
    if not piece.isupper() and path[-1][0] == last:
        piece = piece.upper()
    board[path[-1][0]][path[-1][1]] = piece
    return caps


def game_result(board, side):
    """返回 'r' / 'b' 获胜方, 'draw', 或 None (未结束)。"""
    has_piece = any(board[r][c].lower() == side for r in range(8) for c in range(8))
    if not has_piece:
        return opponent(side)
    if not legal_moves(board, side):
        return opponent(side)  # 被困死
    return None


def evaluate(board):
    """正数偏向红方: 兵 100, 王 300, 推进加成。"""
    s = 0
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p == EMPTY:
                continue
            v = 300 if p.isupper() else 100
            v += (7 - r) * 2 if p == "r" else r * 2
            s += v if p.lower() == "r" else -v
    return s


def _search(board, side, depth, alpha, beta):
    res = game_result(board, side)
    if res == side:
        return 100000
    if res == opponent(side):
        return -100000
    if res == "draw":
        return 0
    if depth == 0:
        return evaluate(board) * (1 if side == "r" else -1)
    best = -10**9
    for mv in legal_moves(board, side):
        nb = [row[:] for row in board]
        apply_move(nb, mv)
        val = -_search(nb, opponent(side), depth - 1, -beta, -alpha)
        if val > best:
            best = val
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def ai_move(board, side, depth, rng):
    """返回 AI 选择的路线 (等分随机打破平局)。"""
    moves = legal_moves(board, side)
    if not moves:
        return None
    rng.shuffle(moves)
    scored = []
    for mv in moves:
        nb = [row[:] for row in board]
        apply_move(nb, mv)
        val = -_search(nb, opponent(side), depth - 1, -10**9, 10**9)
        scored.append((val, mv))
    top = max(v for v, _ in scored)
    return rng.choice([mv for v, mv in scored if v == top])


def render(board):
    lines = ["  " + " ".join(FILES)]
    for r in range(8):
        row = []
        for c in range(8):
            p = board[r][c]
            if (r + c) % 2 == 0:
                row.append("·")
            elif p == EMPTY:
                row.append(" ")
            elif p == "r":
                row.append("●")
            elif p == "R":
                row.append("♛")
            elif p == "b":
                row.append("○")
            else:
                row.append("♕")
        lines.append(f"{8 - r} " + " ".join(row) + f" {8 - r}")
    lines.append("  " + " ".join(FILES))
    return "\n".join(lines)


def parse_move(text):
    """解析 'c3 d4 e5' 或 'c3-d4-e5' 为坐标列表, 失败返回 None。"""
    toks = text.replace("-", " ").split()
    path = []
    for t in toks:
        t = t.strip().lower()
        if len(t) != 2 or t[0] not in FILES or t[1] not in "12345678":
            return None
        path.append((8 - int(t[1]), FILES.index(t[0])))
    if len(path) < 2:
        return None
    return path


def fmt_move(path):
    return "-".join(f"{FILES[c]}{8 - r}" for r, c in path)


def play_game(depth_r, depth_b, rng, max_halfmoves=160, verbose=False):
    """AI 对 AI 一局。返回 (结果, 半回合数, 红吃子数, 黑吃子数)。"""
    board = new_board()
    side = "r"
    half = 0
    caps = {"r": 0, "b": 0}
    while half < max_halfmoves:
        res = game_result(board, side)
        if res is not None:
            return res, half, caps["r"], caps["b"]
        mv = ai_move(board, side, depth_r if side == "r" else depth_b, rng)
        caps[side] += apply_move(board, mv)
        half += 1
        side = opponent(side)
        if verbose:
            print(render(board))
            print()
    return "draw", half, caps["r"], caps["b"]


def interactive(depth, rng):
    board = new_board()
    side = "r"
    print("checkers-lite: 你执红 (●/♛) 先行, AI 执黑 (○/♕)。")
    print("输入走法如: c3 d4   连跳如: c3 e5 g7   退出: q")
    print("有吃必吃, 兵到底线升王。")
    while True:
        res = game_result(board, side)
        if res == "r":
            print("你赢了!")
            return
        if res == "b":
            print("AI 赢了!")
            return
        if res == "draw":
            print("和棋。")
            return
        print()
        print(render(board))
        if side == "r":
            try:
                text = input("你的走法> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见。")
                return
            if text.lower() in ("q", "quit", "exit"):
                print("再见。")
                return
            path = parse_move(text)
            legal = legal_moves(board, side)
            if path is None or path not in legal:
                print("非法走法。合法走法示例:", fmt_move(legal[0]))
                continue
            apply_move(board, path)
        else:
            mv = ai_move(board, side, depth, rng)
            print("AI 走:", fmt_move(mv))
            apply_move(board, mv)
        side = opponent(side)


def auto(games, depth, seed, verbose):
    rng = random.Random(seed)
    wins = {"r": 0, "b": 0, "draw": 0}
    for i in range(games):
        res, half, cr, cb = play_game(depth, depth, rng, verbose=verbose)
        wins[res] += 1
        print(f"第 {i + 1} 局: {res} 胜, {half} 半回合, 红吃 {cr} 黑吃 {cb}")
    print(f"汇总: 红胜 {wins['r']}, 黑胜 {wins['b']}, 和棋 {wins['draw']}")
    return wins


def main(argv=None):
    ap = argparse.ArgumentParser(description="checkers-lite: 极简英式跳棋")
    ap.add_argument("--auto", action="store_true", help="AI 对 AI 无头演示")
    ap.add_argument("--games", type=int, default=4, help="--auto 对局数 (默认 4)")
    ap.add_argument("--depth", type=int, default=2, help="AI 搜索深度 (默认 2)")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="--auto 时打印每步棋盘")
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    if args.auto:
        auto(args.games, args.depth, args.seed, args.verbose)
    else:
        if not sys.stdin.isatty():
            print("交互模式需要终端; 非终端请用 --auto。", file=sys.stderr)
            sys.exit(2)
        interactive(args.depth + 1, rng)


if __name__ == "__main__":
    main()
