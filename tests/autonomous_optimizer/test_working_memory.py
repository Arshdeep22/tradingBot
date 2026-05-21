import pytest
from autonomous_optimizer.memory.working_memory import WorkingMemory, IterationRecord


def _make_record(i: int) -> IterationRecord:
    return IterationRecord(
        iteration=i, phase="A", hypothesis_slug=f"slug_{i}",
        hypothesis_description=f"desc {i}", root_cause_category="entry",
        win_rate=50.0 + i, pnl=float(i * 100), trade_count=i,
        composite_score=0.5 + i * 0.01, reverted=False,
    )


def test_add_respects_window():
    wm = WorkingMemory(window=10)
    for i in range(15):
        wm.add(_make_record(i))
    records = wm.get_last(10)
    assert len(records) == 10
    assert records[-1].iteration == 14   # newest preserved
    assert records[0].iteration == 5     # oldest kept


def test_get_last_fewer_than_window():
    wm = WorkingMemory(window=10)
    for i in range(3):
        wm.add(_make_record(i))
    assert len(wm.get_last(10)) == 3


def test_get_last_truncates_to_n():
    wm = WorkingMemory(window=10)
    for i in range(8):
        wm.add(_make_record(i))
    result = wm.get_last(3)
    assert len(result) == 3
    assert result[-1].iteration == 7


def test_serialise_roundtrip():
    wm = WorkingMemory(window=10)
    for i in range(5):
        wm.add(_make_record(i))
    data = wm.to_dict()
    wm2 = WorkingMemory.from_dict(data, window=10)
    assert wm2.to_dict() == data
    assert len(wm2.get_last(10)) == 5


def test_clear_oldest():
    wm = WorkingMemory(window=10)
    for i in range(8):
        wm.add(_make_record(i))
    evicted = wm.clear_oldest(keep=3)
    assert len(evicted) == 5
    assert len(wm.get_last(10)) == 3
    assert evicted[0].iteration == 0
    assert evicted[-1].iteration == 4


def test_clear_oldest_keep_more_than_stored():
    wm = WorkingMemory(window=10)
    for i in range(3):
        wm.add(_make_record(i))
    evicted = wm.clear_oldest(keep=10)
    assert evicted == []
    assert len(wm.get_last(10)) == 3
