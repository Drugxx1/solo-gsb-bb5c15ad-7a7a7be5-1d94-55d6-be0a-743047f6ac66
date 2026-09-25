"""solve_redundancy 的随机差分测试：用暴力枚举交叉验证推导界与冗余标记。

对每个随机可行实例，单次枚举所有整数坐标赋值：
- 满足全部约束的赋值，对每条约束的“删边子系统”都是可行的；
- 恰好违反一条约束 c 的赋值，是删去 c 后子系统的可行赋值；
- 违反两条及以上的赋值，对任何删边子系统都不可行。

由此逐约束收集 coord(end)−coord(start) 的真实最小/最大值，与 Bellman-Ford
推导界比对；不可达（无界）用删边差分图上的有向 BFS 独立判定，与 null 对齐。
坐标盒取全部边权和的两倍余量，保证达到紧界的赋值落在盒内（有界时盒内极值
即真实极值）。
"""

from __future__ import annotations

import itertools
import random
from collections import deque

from app.schemas import ChainRequest, ConstraintIn
from app.solver import solve_redundancy
from tests.test_random import random_instance
from tests.test_reconcile_random import _multi_datum_instance


def brute_reduced_extrema(datum, measure, constraints):
    """枚举坐标盒：返回每条约束删去后 end−start 的 {cid: (min, max)}。"""
    nodes = list(dict.fromkeys([*datum, *measure]))
    datum_set = set(datum)
    # 两倍边权和余量：紧界赋值（最短路距离 + 基准点平移）必在盒内
    bound = 2 * sum(max(abs(c.lower), abs(c.upper)) + 1 for c in constraints)
    ranges = [
        range(0, 1) if p in datum_set else range(-bound, bound + 1) for p in nodes
    ]
    idx = {p: i for i, p in enumerate(nodes)}
    extrema: dict[str, list] = {c.id: [None, None] for c in constraints}

    for vals in itertools.product(*ranges):
        violated: list[ConstraintIn] = []
        for c in constraints:
            d = vals[idx[c.end]] - vals[idx[c.start]]
            if not (c.lower <= d <= c.upper):
                violated.append(c)
                if len(violated) > 1:
                    break  # 违反两条以上：删掉任何一条仍不可行，直接跳过
        if len(violated) > 1:
            continue
        targets = constraints if not violated else violated
        for c in targets:
            diff = vals[idx[c.end]] - vals[idx[c.start]]
            e = extrema[c.id]
            e[0] = diff if e[0] is None else min(e[0], diff)
            e[1] = diff if e[1] is None else max(e[1], diff)

    return {cid: (lo, hi) for cid, (lo, hi) in extrema.items()}


def reachable_after_removal(datum, measure, constraints, removed_id, src):
    """删去 removed_id 的两条边后，src 在差分图（含基准 pin 边）中的可达点集。"""
    nodes = list(dict.fromkeys([*datum, *measure]))
    adj: dict[str, set[str]] = {p: set() for p in nodes}
    anchor = datum[0]
    for d in datum:
        if d != anchor:
            adj[anchor].add(d)
            adj[d].add(anchor)
    for c in constraints:
        if c.id == removed_id:
            continue
        adj[c.start].add(c.end)
        adj[c.end].add(c.start)

    seen = {src}
    queue: deque[str] = deque([src])
    while queue:
        cur = queue.popleft()
        for nxt in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _assert_instance(datum, measure, constraints):
    req_obj = ChainRequest(
        datum_points=datum, measure_points=measure, constraints=constraints
    )
    res = solve_redundancy(req_obj)
    if not res.feasible:
        assert res.cycle_weight < 0
        return False

    extrema = brute_reduced_extrema(datum, measure, constraints)
    by_id = {it.cid: it for it in res.redundancy}
    assert list(by_id) == [c.id for c in constraints]
    desc = [(c.start, c.end, c.lower, c.upper) for c in constraints]
    for c in constraints:
        it = by_id[c.id]
        blo, bhi = extrema[c.id]
        connected = c.end in reachable_after_removal(
            datum, measure, constraints, c.id, c.start
        )
        if connected:
            assert it.lower == blo and it.upper == bhi, (
                f"derived bounds mismatch for {c.id}: got ({it.lower},{it.upper}), "
                f"brute ({blo},{bhi}), constraints={desc}"
            )
        else:
            # 每条约束上下界成对出边 ⇒ 有向图双向，不可达必两侧同时不可达
            assert it.lower is None and it.upper is None, f"{c.id}: {desc}"
        expected = connected and blo >= c.lower and bhi <= c.upper
        assert it.redundant == expected, f"{c.id}: {desc}"
    return True


def test_random_redundancy_matches_brute_force():
    rng = random.Random(20260925)
    checked = 0
    for _ in range(150):
        datum, measure, constraints = random_instance(rng)
        if _assert_instance(datum, measure, constraints):
            checked += 1
    assert checked > 50  # 该分布约一半实例可行，保证确实比对了推导界


def test_random_redundancy_multiple_datums_matches_brute_force():
    rng = random.Random(20260926)
    checked = 0
    for _ in range(80):
        datum, measure, constraints = _multi_datum_instance(rng)
        if _assert_instance(datum, measure, constraints):
            checked += 1
    assert checked > 30
