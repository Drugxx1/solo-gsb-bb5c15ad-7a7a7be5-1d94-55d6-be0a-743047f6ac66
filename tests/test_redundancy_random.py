"""solve_redundancy 的随机差分测试：与暴力枚举的推导界交叉验证。

对每个可行的随机实例，逐条移除约束后枚举其余约束系统（基准点为 0）的全部
整数可行赋值，取 x_end − x_start 的真实最小/最大值作为推导界；不可达
（无界）的一侧用差分图有向 BFS 判定，期望为 None。同时核对冗余标记。
"""

from __future__ import annotations

import itertools
import random
from collections import deque

from app.schemas import ChainRequest
from app.solver import solve_redundancy
from tests.test_random import random_instance


def _reduced_solutions(datum, measure, rest):
    """枚举 rest 约束系统的全部可行整数赋值（基准点为 0），返回坐标元组。

    坐标界取 ``2·Σ(max|w|+1)+1``：极值赋值（最短路距离，每个简单点路径
    每条约束至多贡献一条边）经平移使基准点为 0 后，任一点坐标不超过该界。
    """
    nodes = list(dict.fromkeys([*datum, *measure]))
    datum_set = set(datum)
    bound = 2 * sum(max(abs(c.lower), abs(c.upper)) + 1 for c in rest) + 1
    spans = [
        range(0, 1) if p in datum_set else range(-bound, bound + 1) for p in nodes
    ]
    idx = {p: i for i, p in enumerate(nodes)}
    sols = []
    for vals in itertools.product(*spans):
        if all(
            c.lower <= vals[idx[c.end]] - vals[idx[c.start]] <= c.upper for c in rest
        ):
            sols.append(vals)
    return sols, idx, datum_set


def _reachable(datum, rest, src) -> set[str]:
    """rest 约束转差分图后的有向可达集合（每条约束给出正反两条边）。"""
    adjacency: dict[str, list[str]] = {}

    def add(u: str, v: str) -> None:
        adjacency.setdefault(u, []).append(v)

    anchor = datum[0]
    for d in datum[1:]:  # 基准点钉零 pin 边
        add(anchor, d)
        add(d, anchor)
    for c in rest:
        add(c.start, c.end)  # 上限边
        add(c.end, c.start)  # 下限反向边

    seen = {src}
    queue: deque[str] = deque([src])
    while queue:
        u = queue.popleft()
        for v in adjacency.get(u, ()):
            if v not in seen:
                seen.add(v)
                queue.append(v)
    return seen


def test_random_redundancy_matches_brute_force():
    rng = random.Random(20260926)
    checked = 0
    redundant_seen = 0
    unbounded_seen = 0
    for _ in range(200):
        datum, measure, constraints = random_instance(rng)
        req_obj = ChainRequest(
            datum_points=datum, measure_points=measure, constraints=constraints
        )
        res = solve_redundancy(req_obj)
        if not res.feasible:
            # 不可行实例沿用矛盾闭环，无推导界可比对
            assert res.cycle_weight < 0
            continue

        assert res.redundancy is not None
        assert [x.cid for x in res.redundancy] == [c.id for c in constraints]

        for i, c in enumerate(constraints):
            rest = [x for j, x in enumerate(constraints) if j != i]
            sols, idx, datum_set = _reduced_solutions(datum, measure, rest)
            assert sols  # 可行系统的子系统必有可行赋值

            def coord(vals, p):
                return 0 if p in datum_set else vals[idx[p]]

            diffs = [coord(v, c.end) - coord(v, c.start) for v in sols]
            # end 从 start 不可达 ⇒ x_end−x_start 无上界；start 从 end 不可达同理
            exp_upper = max(diffs) if c.end in _reachable(datum, rest, c.start) else None
            exp_lower = min(diffs) if c.start in _reachable(datum, rest, c.end) else None

            got = res.redundancy[i]
            assert got.derived_lower == exp_lower, (
                f"lower: got {got.derived_lower}, bf {exp_lower}, "
                f"c={c}, rest={[(x.start, x.end, x.lower, x.upper) for x in rest]}"
            )
            assert got.derived_upper == exp_upper, (
                f"upper: got {got.derived_upper}, bf {exp_upper}, "
                f"c={c}, rest={[(x.start, x.end, x.lower, x.upper) for x in rest]}"
            )
            exp_redundant = (
                exp_lower is not None
                and exp_upper is not None
                and c.lower <= exp_lower
                and exp_upper <= c.upper
            )
            assert got.redundant == exp_redundant, (
                f"redundant: got {got.redundant}, bf {exp_redundant}, c={c}"
            )
            if got.redundant:
                redundant_seen += 1
            if got.derived_lower is None:
                unbounded_seen += 1
        checked += 1

    assert checked > 120  # 大多数随机实例可行，保证充分比对
    assert redundant_seen > 0  # 应覆盖到确有冗余约束的实例
    assert unbounded_seen > 0  # 应覆盖到移除唯一桥约束后无界的实例
