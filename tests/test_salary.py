import pathlib
import sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.load_salary import _detect_columns, _parse_week_number, _pick_week_file

def test_detect_columns_variant():
    df = pd.DataFrame({
        'Player Name': ['Doe, John'],
        'Pos': ['QB'],
        'NFL Team': ['NE'],
        'Cost': [1000],
    })
    cols = _detect_columns(df)
    assert cols == ('Player Name', 'Pos', 'NFL Team', 'Cost')


def test_parse_week_number_variants():
    assert _parse_week_number(pathlib.Path('2025_01_Salary.xlsx')) == 1
    assert _parse_week_number(pathlib.Path('wk7-salaries.xlsx')) == 7
    assert _parse_week_number(pathlib.Path('Salary.xlsx')) is None


def test_pick_week_file_selection(tmp_path):
    files = [
        tmp_path / '2025_01_Salary.xlsx',
        tmp_path / '2025_03_Salary.xlsx',
        tmp_path / '2025_05_Salary.xlsx',
    ]
    for fp in files:
        fp.write_text('stub')

    pattern = str(tmp_path / '*.xlsx')

    exact = _pick_week_file(pattern, week=3)
    assert exact and exact.name == '2025_03_Salary.xlsx'

    prior = _pick_week_file(pattern, week=4)
    assert prior and prior.name == '2025_03_Salary.xlsx'

    future = _pick_week_file(pattern, week=8)
    assert future and future.name == '2025_05_Salary.xlsx'
