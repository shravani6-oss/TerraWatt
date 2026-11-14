import numpy as np
from backend.app.services.forecast import f_damped, f_linear, f_naive


def test_forecast_primitives():
    y = np.arange(10, dtype=float)
    assert np.allclose(f_naive(y, 3), 9)
    assert np.allclose(f_linear(y, 3), [10, 11, 12])
    d = f_damped(y, 30)
    assert d[0] > 9 and d[-1] < 9 + 30        # damped trend flattens instead of growing linearly
    assert np.all(np.diff(d) > 0) and np.diff(d)[-1] < np.diff(d)[0]
