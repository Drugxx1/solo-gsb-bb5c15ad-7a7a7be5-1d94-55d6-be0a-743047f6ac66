"""solve_redundancy 核心求解器单元测试。"""

from __future__ import annotations

from app.schemas import ChainRequest, ConstraintIn
from app.solver import solve_redundancy


def C(cid: str, start: str, end: str, lower: int, upper: int) -> ConstraintIn:
    return ConstraintIn(id=cid, start=start, end=end, lower=lower, upper=upper)


def req(datum, measure, constraints) -> ChainRequest:
    return ChainRequest(
        datum_points=list(datum),
        measure_points=list(measure),
        constraints=list(constraints),
    )


def item_map(res):
    assert res.feasible
    return {it.cid: it for it in res.redundancy}


def test_simple_chain_nothing_redundant_and_null_means_unbounded():
    # 删除任一桥接约束后端点被断开：两侧均不可达 ⇒ null（无界）⇒ 非冗余
    r = req(["A"], ["B", "C"], [C("c1", "A", "B", 10, 12), C("c2", "B", "C", 5, 8)])
    res = solve_redundancy(r)
    assert [it.cid for it in res.redundancy] == ["c1", "c2"]  # 沿用请求顺序
    for cid in ("c1", "c2"):
        it = item_map(res)[cid]
        assert it.lower is None and it.upper is None
        assert it.redundant is False


def test_one_implied_constraint():
    # c1: A→B [10,12]，c2: B→C [5,8] ⇒ A→C ∈ [15,20]；
    # c3 给 [14,22]，完全包住推导区间 ⇒ 冗余；c1/c2 的推导界更宽，非冗余
    r = req(
        ["A"],
        ["B", "C"],
        [
            C("c1", "A", "B", 10, 12),
            C("c2", "B", "C", 5, 8),
            C("c3", "A", "C", 14, 22),
        ],
    )
    items = item_map(solve_redundancy(r))
    assert items["c1"].lower == 6 and items["c1"].upper == 17
    assert items["c1"].redundant is False
    assert items["c2"].lower == 2 and items["c2"].upper == 12
    assert items["c2"].redundant is False
    assert items["c3"].lower == 15 and items["c3"].upper == 20
    assert items["c3"].redundant is True


def test_exact_equality_boundary_is_redundant():
    # 推导区间与原区间相等（端点相等也算完全落入）⇒ 冗余
    r = req(
        ["A"],
        ["B", "C"],
        [
            C("c1", "A", "B", 10, 12),
            C("c2", "B", "C", 5, 8),
            C("c3", "A", "C", 15, 20),
        ],
    )
    items = item_map(solve_redundancy(r))
    assert items["c3"].lower == 15 and items["c3"].upper == 20
    assert items["c3"].redundant is True


def test_one_side_not_contained_is_not_redundant():
    # 推导下界 15 落在原下界 16 之外：仅一侧包住仍非冗余
    r = req(
        ["A"],
        ["B", "C"],
        [
            C("c1", "A", "B", 10, 12),
            C("c2", "B", "C", 5, 8),
            C("c3", "A", "C", 16, 20),
        ],
    )
    items = item_map(solve_redundancy(r))
    assert items["c3"].lower == 15 and items["c3"].upper == 20
    assert items["c3"].redundant is False


def test_duplicate_identical_constraints_both_redundant():
    # 两条完全相同的约束：删去其中一条，另一条仍在，推导区间等于原区间
    # —— 只删待判约束自身，不影响其他同形约束参与推导
    r = req(["A"], ["B"], [C("c1", "A", "B", 10, 12), C("c2", "A", "B", 10, 12)])
    items = item_map(solve_redundancy(r))
    for cid in ("c1", "c2"):
        assert items[cid].lower == 10 and items[cid].upper == 12
        assert items[cid].redundant is True


def test_looser_and_tighter_duplicate():
    # c1 [10,12] 紧、c2 [9,13] 松：松约束被紧约束蕴含；紧约束不被松约束蕴含
    r = req(["A"], ["B"], [C("c1", "A", "B", 10, 12), C("c2", "A", "B", 9, 13)])
    items = item_map(solve_redundancy(r))
    assert items["c1"].lower == 9 and items["c1"].upper == 13
    assert items["c1"].redundant is False
    assert items["c2"].lower == 10 and items["c2"].upper == 12
    assert items["c2"].redundant is True


def test_multiple_datums_pin_relations_participate():
    # D1、D2 互钉为 0：c1 给 M∈[3,7]，c2 给 M−D2∈[3,7]，二者经 pin 边互相蕴含
    r = req(
        ["D1", "D2"],
        ["M"],
        [C("c1", "D1", "M", 3, 7), C("c2", "M", "D2", -7, -3)],
    )
    items = item_map(solve_redundancy(r))
    assert items["c1"].lower == 3 and items["c1"].upper == 7
    assert items["c1"].redundant is True
    assert items["c2"].lower == -7 and items["c2"].upper == -3
    assert items["c2"].redundant is True


def test_negative_weight_equivalent_constraints():
    # B→A ∈ [-12,-10] 与 A→B ∈ [10,12] 是同一关系的两种写法，经负权边互相蕴含
    r = req(["A"], ["B"], [C("c1", "B", "A", -12, -10), C("c2", "A", "B", 10, 12)])
    items = item_map(solve_redundancy(r))
    assert items["c1"].lower == -12 and items["c1"].upper == -10
    assert items["c2"].lower == 10 and items["c2"].upper == 12
    assert items["c1"].redundant is items["c2"].redundant is True


def test_self_loop_containing_zero_is_vacuous():
    # A−A ∈ [-1,1] 恒成立（零长路径即推出 [0,0]）；连接 B 的 c1 仍是桥接约束
    r = req(
        ["A"],
        ["B"],
        [C("s", "A", "A", -1, 1), C("c1", "A", "B", 1, 2)],
    )
    items = item_map(solve_redundancy(r))
    assert items["s"].lower == 0 and items["s"].upper == 0
    assert items["s"].redundant is True
    assert items["c1"].lower is None and items["c1"].upper is None
    assert items["c1"].redundant is False


def test_infeasible_returns_same_cycle_report_as_solve():
    r = req(
        ["A"],
        ["B", "C"],
        [
            C("c1", "A", "B", 9, 10),
            C("c2", "B", "C", 9, 10),
            C("c3", "C", "A", -1, 0),
        ],
    )
    res = solve_redundancy(r)
    assert not res.feasible
    assert res.redundancy is None
    assert res.cycle_weight < 0
    cids = {e.cid for e in res.cycle_edges if e.cid is not None}
    assert cids == {"c1", "c2", "c3"}
