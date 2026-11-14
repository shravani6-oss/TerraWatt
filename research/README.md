# Original research pipeline (GreenAI)

The original academic project: an end-to-end ML study (classification, regression, clustering) on the Kaggle sustainable-energy dataset, with plots and written reports (`REPORT.md`, `VIVA.md`, `DEMO_SCRIPT.md`).
It is preserved unchanged for reference and reproducibility. The production models used by the app live in `backend/app/ml/` (leaner, leakage-safe protocols, no plotting).

    pip install -r research/requirements.txt   # includes matplotlib/seaborn/streamlit used by the original
    cd research && python train.py             # reads research/data, writes research/models|plots|results
