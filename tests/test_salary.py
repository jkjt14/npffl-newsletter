import pathlib
import sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.load_salary import _detect_columns

def test_detect_columns_variant():
    df = pd.DataFrame({
        'Player Name': ['Doe, John'],
        'Pos': ['QB'],
        'NFL Team': ['NE'],
        'Cost': [1000],
    })
    cols = _detect_columns(df)
    assert cols == ('Player Name', 'Pos', 'NFL Team', 'Cost')
