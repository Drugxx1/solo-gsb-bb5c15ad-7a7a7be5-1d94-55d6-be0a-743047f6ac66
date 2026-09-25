"""约束冗余判定（solve_redundancy）求解器单元测试。"""

from __future__ import annotations

import pytest

from app.solver import ValidationError, solve_redundancy
from tests.test_solver import C, req


def triples(res):
    return [(x.cid, x.derived_lower, x.derived_upper, x.redundant) for x in res.redundancy]


def test_implied_constraint_marked_redundant():
    # c1: A→B [10,12] 与 c2: B→C [5,8] 联合推出 A→C ∈ [15,20]，
    # 完整落在 c3 的 [14,21] 内 ⇒ c3 冗余；c1/c2 不被其余条件蕴含
    r = req(
        ["A"], ["B", "C"],
        [C("c1", "A", "B", 10, 12), C("c2", "B", "C", 5, 8), C("c3", "A", "C", 14, 21)],
    )
    res = solve_redundancy(r)
    assert res.feasible
    assert triples(res) == [
        ("c1", 6, 16, False),
        ("c2", 2, 11, False),
        ("c3", 15, 20, True),
    ]


def test_tighter_constraint_not_implied_looser_one_is():
    # 同一对点上的两条约束：较紧的 c1 不被较松的 c2 蕴含（推导区间 [1,3]
    # 超出 [1,2]），较松的 c2 被 c1 蕴含。若把待判约束自身计入推导，
    # c1 会被误判为冗余
    r = req(
        ["A"], ["B"],
        [C("c1", "A", "B", 1, 2), C("c2", "A", "B", 1, 3)],
    )
    res = solve_redundancy(r)
    assert res.feasible
    assert triples(res) == [
        ("c1", 1, 3, False),
        ("c2", 1, 2, True),
    ]


def test_exact_duplicate_constraints_imply_each_other():
    r = req(["A"], ["B"], [C("c1", "A", "B", 5, 5), C("c2", "A", "B", 5, 5)])
    res = solve_redundancy(r)
    assert res.feasible
    assert triples(res) == [("c1", 5, 5, True), ("c2", 5, 5, True)]


def test_single_constraint_never_redundant():
    # 唯一约束被移除后差分图没有任何边：两侧均无界 ⇒ 不冗余
    r = req(["A"], ["B"], [C("c1", "A", "B", 0, 10)])
    res = solve_redundancy(r)
    assert res.feasible
    assert triples(res) == [("c1", None, None, False)]


def test_unbounded_when_constraint_is_sole_bridge():
    # c4 是 D 连入尺寸链的唯一约束：移除后 D 与其余点互不可达，两侧无界
    r = req(
        ["A"], ["B", "C", "D"],
        [
            C("c1", "A", "B", 10, 12),
            C("c2", "B", "C", 5, 8),
            C("c3", "A", "C", 14, 21),
            C("c4", "C", "D", 0, 3),
        ],
    )
    res = solve_redundancy(r)
    assert res.feasible
    assert triples(res)[3] == ("c4", None, None, False)


def test_datum_pin_relations_participate_in_derivation():
    # 两个基准点互钉为 0：c1 与 c2 各自被“另一条约束 + 基准钉零关系”蕴含
    r = req(
        ["D1", "D2"], ["M"],
        [C("c1", "D1", "M", 3, 7), C("c2", "M", "D2", -7, -3)],
    )
    res = solve_redundancy(r)
    assert res.feasible
    assert triples(res) == [("c1", 3, 7, True), ("c2", -7, -3, True)]


def test_self_loop_containing_zero_is_redundant():
    # 自环 A→A [0,5]：移除后空路径给出 0 ≤ x_A − x_A ≤ 0，落在 [0,5] 内
    r = req(
        ["A"], ["B"],
        [C("s", "A", "A", 0, 5), C("c1", "A", "B", 1, 2)],
    )
    res = solve_redundancy(r)
    assert res.feasible
    by_id = {x.cid: x for x in res.redundancy}
    assert (by_id["s"].derived_lower, by_id["s"].derived_upper, by_id["s"].redundant) == (0, 0, True)
    assert by_id["c1"].redundant is False


def test_results_follow_input_constraint_order():
    r = req(
        ["A"], ["B", "C"],
        [C("c3", "A", "C", 14, 21), C("c1", "A", "B", 10, 12), C("c2", "B", "C", 5, 8)],
    )
    res = solve_redundancy(r)
    assert res.feasible
    assert [x.cid for x in res.redundancy] == ["c3", "c1", "c2"]
    assert [x.redundant for x in res.redundancy] == [True, False, False]


def test_infeasible_returns_same_cycle_as_solve():
    r = req(
        ["A"], ["B", "C"],
        [C("c1", "A", "B", 9, 10), C("c2", "B", "C", 9, 10), C("c3", "C", "A", -1, 0)],
    )
    res = solve_redundancy(r)
    assert not res.feasible
    assert res.redundancy is None
    assert res.cycle_weight < 0
    assert {e.cid for e in res.cycle_edges if e.cid is not None} == {"c1", "c2", "c3"}


def test_self_loop_contradiction_is_infeasible():
    # 区间不含 0 的自环：静态校验不拦截，由负环判定为不可行
    r = req(
        ["A"], ["B"],
        [C("s", "A", "A", 1, 2), C("c1", "A", "B", 1, 2)],
    )
    res = solve_redundancy(r)
    assert not res.feasible
    assert res.redundancy is None
    assert [e.cid for e in res.cycle_edges if e.cid is not None] == ["s"]


def test_static_validation_raises():
    r = req(["A"], ["B"], [C("c1", "A", "X", 1, 2)])
    with pytest.raises(ValidationError):
        solve_redundancy(r)
