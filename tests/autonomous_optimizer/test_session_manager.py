import json
import pytest
from pathlib import Path
from unittest.mock import patch

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import BacktestResult
from autonomous_optimizer.memory.working_memory import IterationRecord
from autonomous_optimizer.session_manager import SessionManager


def _config(tmp_path: Path) -> AgentConfig:
    cfg = AgentConfig()
    cfg.state_file = str(tmp_path / "session_state.json")
    cfg.working_memory_window = 10
    cfg.episodic_summarize_every = 10
    cfg.stuck_score_variance_threshold = 0.02
    return cfg


def _record(i: int, score: float = 0.5, reverted: bool = False) -> IterationRecord:
    return IterationRecord(
        iteration=i, phase="A", hypothesis_slug=f"slug_{i}",
        hypothesis_description=f"desc {i}", root_cause_category="entry",
        win_rate=55.0, pnl=1000.0, trade_count=10,
        composite_score=score, reverted=reverted,
    )


def test_load_fresh_start(tmp_path):
    sm = SessionManager(_config(tmp_path))
    sm.load()
    assert sm.state.iteration == 0
    assert sm.state.phase == "A"
    assert sm.state.best_composite == 0.0


def test_save_and_reload(tmp_path):
    cfg = _config(tmp_path)
    sm = SessionManager(cfg)
    sm.state.iteration = 5
    sm.state.phase = "B"
    sm.state.best_composite = 0.75
    sm.working.add(_record(1))
    sm.save()

    sm2 = SessionManager(cfg)
    sm2.load()
    assert sm2.state.iteration == 5
    assert sm2.state.phase == "B"
    assert sm2.state.best_composite == pytest.approx(0.75)
    assert len(sm2.working.get_last(10)) == 1


def test_save_atomic_no_corruption(tmp_path):
    cfg = _config(tmp_path)
    sm = SessionManager(cfg)
    sm.state.iteration = 3
    sm.save()

    state_path = Path(cfg.state_file)
    original_content = state_path.read_text()

    import builtins
    real_open = builtins.open
    call_count = [0]

    def flaky_open(path, *args, **kwargs):
        if ".tmp" in str(path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("simulated crash mid-write")
        return real_open(path, *args, **kwargs)

    with patch("builtins.open", flaky_open):
        try:
            sm.save()
        except OSError:
            pass

    assert state_path.read_text() == original_content


def test_record_iteration_appends(tmp_path):
    sm = SessionManager(_config(tmp_path))
    sm.record_iteration(_record(1, score=0.6))
    assert len(sm.working.get_last(10)) == 1
    assert sm.state.best_composite == pytest.approx(0.6)


def test_maybe_compress_runs_every_10(tmp_path):
    cfg = _config(tmp_path)
    sm = SessionManager(cfg)
    for i in range(10):
        sm.record_iteration(_record(i))
    sm.state.iteration = 10
    compressed = sm.maybe_compress()
    assert compressed is True
    assert len(sm.long_term.get_phase_summaries()) == 1


def test_maybe_compress_skips_other_iterations(tmp_path):
    sm = SessionManager(_config(tmp_path))
    for i in range(5):
        sm.record_iteration(_record(i))
    sm.state.iteration = 5
    assert sm.maybe_compress() is False


def test_advance_phase_a_to_b(tmp_path):
    sm = SessionManager(_config(tmp_path))
    new_phase = sm.advance_phase()
    assert new_phase == "B"
    assert sm.state.phase == "B"


def test_advance_phase_b_to_c(tmp_path):
    sm = SessionManager(_config(tmp_path))
    sm.state.phase = "B"
    assert sm.advance_phase() == "C"


def test_advance_phase_c_raises(tmp_path):
    sm = SessionManager(_config(tmp_path))
    sm.state.phase = "C"
    with pytest.raises(ValueError):
        sm.advance_phase()


def test_should_advance_flat_scores(tmp_path):
    cfg = _config(tmp_path)
    sm = SessionManager(cfg)
    for i in range(10):
        sm.record_iteration(_record(i, score=0.55))
    assert sm.should_advance_phase(last_n=10) is True


def test_should_advance_improving_scores(tmp_path):
    cfg = _config(tmp_path)
    sm = SessionManager(cfg)
    for i in range(10):
        sm.record_iteration(_record(i, score=0.4 + i * 0.05))
    assert sm.should_advance_phase(last_n=10) is False


def test_thinker_context_keys(tmp_path):
    sm = SessionManager(_config(tmp_path))
    ctx = sm.thinker_context()
    assert "recent" in ctx
    assert "learned" in ctx
    assert "blocked" in ctx
    assert "current_phase" in ctx
    assert "best_metrics" in ctx
