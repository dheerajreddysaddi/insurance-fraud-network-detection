# Source manifest

## Data
All records are synthetic, generated locally by `src/data_generator.py` with seed `20261022`. No external dataset, web scraping
or real personal data is used, so no third-party data licence applies. Names come from short lists written into the generator;
phone numbers use the fictional `+000` prefix; emails use the reserved `.test` domain; addresses are invented.
Public reference data was not fetched, not even for schema inspiration.

## Software dependencies (pinned in `requirements.txt`)
Streamlit, pandas, NumPy, pyarrow, NetworkX, Plotly, SQLAlchemy, psycopg2-binary, python-dotenv, PyYAML, pytest. They are
installed from PyPI; check each package's published licence before redistributing a bundled copy.

## Generated files
`data/generated/` (CSV, JSON, SQL) is reproducible and not committed. `data/ground_truth/*.csv` is committed so the hosted
Evaluation page works; it is synthetic and never read by the detector.