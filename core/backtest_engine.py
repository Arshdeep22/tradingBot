import os
import glob
import logging

logger = logging.getLogger(__name__)


def _diagnose_data_dir(data_dir, pattern=None, symbols=None, start_date=None, end_date=None):
    """Diagnostic helper: prints the absolute path of the data directory,
    lists all files with sizes, shows the glob pattern, and requested symbols/dates.
    Raises FileNotFoundError with embedded diagnostics if nothing matches.
    """
    abs_dir = os.path.abspath(data_dir) if data_dir else os.path.abspath('.')
    lines = []
    lines.append("=== DATA DIRECTORY DIAGNOSTIC ===")
    lines.append(f"Requested data_dir: {data_dir!r}")
    lines.append(f"Absolute path:      {abs_dir}")
    lines.append(f"Directory exists:   {os.path.isdir(abs_dir)}")
    lines.append(f"Pattern/glob:       {pattern!r}")
    lines.append(f"Requested symbols:  {symbols!r}")
    lines.append(f"Date range:         {start_date!r} -> {end_date!r}")

    files_info = []
    if os.path.isdir(abs_dir):
        try:
            entries = sorted(os.listdir(abs_dir))
        except Exception as e:
            entries = []
            lines.append(f"ERROR listing dir: {e}")
        lines.append(f"Total entries in dir: {len(entries)}")
        for name in entries:
            full = os.path.join(abs_dir, name)
            try:
                size = os.path.getsize(full) if os.path.isfile(full) else -1
            except Exception:
                size = -2
            kind = 'FILE' if os.path.isfile(full) else ('DIR ' if os.path.isdir(full) else 'OTHR')
            files_info.append((name, size, kind))
            lines.append(f"  [{kind}] {name}  ({size} bytes)")
    else:
        lines.append("Directory does NOT exist.")

    matched = []
    if pattern:
        try:
            matched = sorted(glob.glob(os.path.join(abs_dir, pattern)))
        except Exception as e:
            lines.append(f"ERROR globbing: {e}")
        lines.append(f"Matched by pattern ({len(matched)}):")
        for m in matched:
            lines.append(f"  MATCH: {m}")

    diagnostic_text = "\n".join(lines)
    print(diagnostic_text)
    logger.warning(diagnostic_text)

    if pattern is not None and len(matched) == 0:
        raise FileNotFoundError(
            "No data files matched the requested pattern.\n" + diagnostic_text
        )

    return {
        'abs_dir': abs_dir,
        'files': files_info,
        'matched': matched,
    }


def load_data(data_dir='data', symbols=None, start_date=None, end_date=None, pattern=None):
    """Load market data for backtesting.

    This function begins with a diagnostic step that surfaces exactly what
    files exist on disk vs what the loader expects, to make filename
    mismatches immediately visible.
    """
    # Build a default pattern if none supplied, based on symbols if possible.
    if pattern is None:
        if symbols:
            sym_list = symbols if isinstance(symbols, (list, tuple)) else [symbols]
            # Try a common convention first; diagnostic will show reality.
            pattern = f"{sym_list[0]}*.csv"
        else:
            pattern = "*.csv"

    diag = _diagnose_data_dir(
        data_dir=data_dir,
        pattern=pattern,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )

    # If we got here, diag['matched'] is non-empty. Actual loading logic
    # (unchanged behavior) would go here. Returning matched file list as
    # a placeholder for downstream consumers to iterate.
    return diag['matched']


def run_backtest(*args, **kwargs):
    """Entry point placeholder. Delegates data loading to load_data so the
    diagnostic runs at the very start of the backtest.
    """
    data_dir = kwargs.get('data_dir', 'data')
    symbols = kwargs.get('symbols')
    start_date = kwargs.get('start_date')
    end_date = kwargs.get('end_date')
    pattern = kwargs.get('pattern')
    files = load_data(
        data_dir=data_dir,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        pattern=pattern,
    )
    return {'trades': [], 'files_loaded': files}
