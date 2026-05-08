"""Stage 4: linear static solver tests.

The validation suite (V1–V9) lives in tests/validation/. Each case is a
(model.json, expected.json) pair. This file parametrizes over them.
"""

from pathlib import Path

import pytest

VALIDATION_DIR = Path(__file__).parent / "validation"


def _validation_cases():
    """Discover (model_path, expected_path) pairs in tests/validation/."""
    if not VALIDATION_DIR.exists():
        return []
    cases = []
    for model_path in sorted(VALIDATION_DIR.glob("V*_model.json")):
        expected_path = model_path.with_name(
            model_path.name.replace("_model.json", "_expected.json")
        )
        if expected_path.exists():
            cases.append(pytest.param(model_path, expected_path, id=model_path.stem.split("_")[0]))
    return cases


@pytest.mark.skip(reason="Stage 4 not yet implemented")
@pytest.mark.parametrize("model_path,expected_path", _validation_cases() or [pytest.param(None, None, id="no-cases")])
def test_validation_case(model_path, expected_path):
    """Solve the model, assert all checked quantities are within 0.01% of expected."""
    raise NotImplementedError
