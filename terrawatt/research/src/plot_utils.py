"""Small helpers for saving figures."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .config import PLOTS_DIR


def save_fig(fig, name):
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PLOTS_DIR / f"{name}.png"
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return path
