# Data Dictionary - SMARD CNN-LSTM Electricity Price Forecasting Project

## 1. Project purpose

This dataset is used for a CNN-LSTM day-ahead electricity-price forecasting
project focused on the Germany/Luxembourg bidding zone.

The cleaned dataset combines:

- Germany/Luxembourg day-ahead electricity price
- Actual German grid load
- Forecast German grid load

on one continuous hourly UTC timeline.

The primary operational forecasting task will predict future
Germany/Luxembourg day-ahead electricity prices using historical price
information, historical/forecast load information, and later engineered
calendar/lag features.

Notebook responsible for this stage:

`notebooks/01_smard_cleaning.ipynb`

Processed output:

`data/processed/smard_hourly_clean.parquet`

Kaggle working output during development:

`/kaggle/working/smard_hourly_clean.parquet`

---

## 2. Data source

Source:

SMARD - German Federal Network Agency (Bundesnetzagentur)

SMARD market-data download center:

https://www.smard.de/en/downloadcenter/download-market-data/

Requested download period used for this implementation:

- Start selection: 2022-09-01
- End selection: 2024-09-01
- Resolution: Calculated hourly resolution
- Raw rows observed in each export: 17,568

Raw files are stored unchanged under:

`data/raw/smard/`

The raw CSV files must remain untouched so the complete preprocessing
pipeline can be reproduced from the original SMARD exports.

---

## 3. Raw datasets

### 3.1 Day-ahead electricity-price dataset

Purpose:

Contains day-ahead wholesale electricity prices for Germany/Luxembourg
and several other European bidding zones.

Raw columns observed:

- `Start date`
- `End date`
- `Germany/Luxembourg [€/MWh] Calculated resolutions`
- `∅ DE/LU neighbours [€/MWh] Calculated resolutions`
- `Belgium [€/MWh] Calculated resolutions`
- `Denmark 1 [€/MWh] Calculated resolutions`
- `Denmark 2 [€/MWh] Calculated resolutions`
- `France [€/MWh] Calculated resolutions`
- `Netherlands [€/MWh] Calculated resolutions`
- `Norway 2 [€/MWh] Calculated resolutions`
- `Austria [€/MWh] Calculated resolutions`
- `Poland [€/MWh] Calculated resolutions`
- `Sweden 4 [€/MWh] Calculated resolutions`
- `Switzerland [€/MWh] Calculated resolutions`
- `Czech Republic [€/MWh] Calculated resolutions`
- `DE/AT/LU [€/MWh] Calculated resolutions`
- `Northern Italy [€/MWh] Calculated resolutions`
- `Slovenia [€/MWh] Calculated resolutions`
- `Hungary [€/MWh] Calculated resolutions`

Target raw column used in the main project:

`Germany/Luxembourg [€/MWh] Calculated resolutions`

Cleaned column name:

`price_eur_mwh`

Unit:

EUR/MWh

Role:

- Main forecasting target.
- Historical values will later be used for autoregressive lag and rolling
  features.
- Future price values are never used as predictors.

Other European price columns:

The other bidding-zone price columns remain in the untouched raw CSV but
are excluded from the primary processed dataset.

They may later be evaluated as optional cross-market exogenous variables
in a separate experiment, provided forecast-time information availability
is respected.

Data-quality rules:

- Negative electricity prices are valid market observations and must not
  be removed merely because they are negative.
- Genuine electricity-price spikes are retained.
- Price spikes are not winsorized in the primary experiment.

---

### 3.2 Actual electricity-consumption dataset

Purpose:

Contains observed German electricity-consumption/load variables.

Raw columns observed:

- `Start date`
- `End date`
- `grid load [MWh] Calculated resolutions`
- `Grid load incl. hydro pumped storage [MWh] Calculated resolutions`
- `Hydro pumped storage [MWh] Calculated resolutions`
- `Residual load [MWh] Calculated resolutions`

Raw column used:

`grid load [MWh] Calculated resolutions`

Cleaned column name:

`load_actual_mwh`

Unit:

MWh

Role:

- Historical observed demand/load information.
- Can be used for historical model inputs.
- Can be used in paper-style diagnostic/reproduction experiments.
- Future actual load is not considered operationally available at
  forecast issue time.
- Therefore future actual load must not be used as a future exogenous
  predictor in the operational day-ahead model.

Missing values after numeric cleaning:

0 known missing observations.

---

### 3.3 Forecast electricity-consumption dataset

Purpose:

Contains forecast German load information intended to represent load
information available before delivery.

Raw columns observed:

- `Start date`
- `End date`
- `grid load [MWh] Calculated resolutions`
- `Residual load [MWh] Calculated resolutions`

Raw column used:

`grid load [MWh] Calculated resolutions`

Cleaned column name:

`load_forecast_mwh`

Unit:

MWh

Role:

Preferred future exogenous load variable for the operational forecasting
model because forecasted load is designed to be available before the
delivery period.

Raw numeric representation:

Values can appear as strings with comma thousands separators and a period
decimal separator.

Example:

`52,143.25`

Interpretation:

- `,` = thousands separator
- `.` = decimal separator

Conversion rule:

- Remove comma thousands separators.
- Preserve the decimal period.
- Convert the resulting string to numeric/float.

Example:

`52,143.25`

becomes:

`52143.25`

Missing-value representation in the raw file:

`-`

The literal dash is a textual missing-value marker.

It is converted to:

`NaN`

before/while numeric conversion.

Known missing observations:

97 total missing forecast-load observations.

Missing-run structure:

- 1 run of 1 consecutive hour = 1 missing observation
- 2 runs of 24 consecutive hours = 48 missing observations
- 1 run of 48 consecutive hours = 48 missing observations

Total:

97 missing observations.

Notebook 01 policy:

All 97 missing forecast-load values are retained as `NaN` in the cleaned
dataset.

No long-gap imputation is performed during raw-data cleaning.

Planned downstream treatment:

- The isolated 1-hour missing value may be handled in feature engineering
  using a documented past-only method.
- Windows crossing the 24-hour or 48-hour gaps should normally be excluded
  instead of fabricating long stretches of forecast-load values.

---

## 4. Column-label cleaning

The first raw column initially contained a UTF-8 byte-order mark (BOM):

`\ufeffStart date`

During cleaning, the BOM and surrounding column-name whitespace are
removed so the column becomes:

`Start date`

This changes only the representation of the column label and does not
alter any observation values.

---

## 5. Timestamp format and parsing

Observed raw timestamp style:

`Aug 31, 2022 9:00 PM`

Explicit pandas parsing format:

`%b %d, %Y %I:%M %p`

Meaning:

- `%b` = abbreviated month name, such as `Aug`
- `%d` = day of month
- `%Y` = four-digit year
- `%I` = hour using a 12-hour clock
- `%M` = minute
- `%p` = AM/PM marker

Both `Start date` and `End date` are parsed into pandas datetime values
for inspection and auditing.

The canonical model timestamp is derived from:

`Start date`

---

## 6. Time zone and daylight-saving-time handling

Source local-time interpretation:

`Europe/Berlin`

Canonical processed timezone:

`UTC`

Reason:

Germany uses daylight-saving time, so local civil time is not a uniformly
spaced timeline throughout the year.

Continuous CNN/LSTM hourly windows must represent real elapsed time.

Therefore local timestamps are interpreted using `Europe/Berlin` and
converted to UTC before merging and model-window construction.

### 6.1 Spring DST transition

Example observed around 2023-03-26:

- `01:00 -> 02:00`
- the next row begins at `03:00 -> 04:00`

The local 02:00 start hour is absent because clocks move forward.

This is valid daylight-saving-time behavior and is not treated as a
missing physical hour after conversion to UTC.

### 6.2 Autumn DST transition

Example observed around 2022-10-30:

Two rows contain the local start timestamp:

`2022-10-30 02:00:00`

These are not erroneous duplicates.

They represent two different real hours because clocks move backward and
the local clock reads 02:00 twice.

Handling rule:

- Sort observations by local `Start date`.
- Localize naive timestamps to `Europe/Berlin`.
- Resolve repeated autumn timestamps using ordered inference:
  `ambiguous="infer"`.
- Convert localized timestamps to UTC.
- Do not delete the repeated autumn hour.
- Do not fabricate the nonexistent spring local hour.

Canonical timestamp column:

`timestamp`

The raw `End date` is retained for auditing when required but is not
needed as the model index.

If a normalized end timestamp is required, it can be created after UTC
conversion as:

`timestamp + 1 hour`

---

## 7. Cleaned merged dataset schema

The processed dataset contains one row per real hourly timestamp and three
modeling variables.

Index:

`timestamp`

Index properties:

- Timezone-aware
- UTC
- Sorted in ascending chronological order
- Intended to contain no duplicate UTC timestamps
- Intended to progress in one-hour increments except where a genuine
  source gap exists

Columns:

| Column | Type | Unit | Description |
|---|---|---|---|
| `price_eur_mwh` | numeric/float | EUR/MWh | Germany/Luxembourg day-ahead wholesale electricity price |
| `load_actual_mwh` | numeric/float | MWh | Observed German grid load |
| `load_forecast_mwh` | numeric/float | MWh | Forecast German grid load; 97 known NaN observations remain |

Merge method:

Inner join on the canonical UTC timestamp index.

Reason:

Every retained row must correspond to the same real hourly instant across:

- price
- actual load
- forecast load

Timestamp alignment is therefore used instead of assuming that equal row
positions represent equal times.

---

## 8. Missing-value policy

### 8.1 Price

No known semantic missing markers were identified during completed raw
inspection.

Negative electricity prices are valid and are not considered missing.

### 8.2 Actual load

No known missing observations after numeric conversion.

### 8.3 Forecast load

97 known missing observations exist after converting raw `-` markers to
`NaN`.

Notebook 01 does not impute these values.

Missing-value handling required specifically for model construction is
deliberately deferred to the feature/window-building stage so that this
processed dataset remains faithful to the source.

---

## 9. Validation checks

The cleaned dataset is validated using the following checks:

1. Confirm expected columns and numeric dtypes.
2. Confirm the UTC timestamp index is sorted.
3. Count duplicate UTC timestamps.
4. Calculate consecutive timestamp differences.
5. Verify expected one-hour UTC continuity.
6. Compare source and merged row counts.
7. Count missing values per column.
8. Inspect descriptive statistics for price and load.
9. Inspect negative and zero electricity-price observations without
   automatically removing them.
10. Plot actual versus forecast load as a scale/alignment sanity check.
11. Plot Germany/Luxembourg day-ahead price for visual validation.
12. Analyze forecast-load missing values by consecutive run length.

---

## 10. Leakage and information-availability rules

The operational model must obey forecast-time information availability.

Allowed later:

- Historical Germany/Luxembourg electricity prices
- Historical actual load
- Day-ahead forecasted load for future delivery hours when genuinely
  available at forecast issue time
- Deterministic calendar variables
- Past-only price lag features
- Past-only rolling statistics

Not allowed in the operational model:

- Future actual load for hours being predicted
- Future realized electricity prices
- Rolling statistics containing the current or future target
- Any scaler fitted using validation or test-period information

Future actual load may only be used in a clearly labeled paper-style
diagnostic/reproduction experiment when that experimental setup is being
intentionally reproduced.

---

## 11. Raw versus processed data policy

Raw layer:

`data/raw/smard/`

Contains untouched SMARD exports.

Raw files are never overwritten by preprocessing.

Processed layer:

`data/processed/smard_hourly_clean.parquet`

Contains:

- standardized column names
- numeric values
- UTC timestamp alignment
- documented missing observations

Feature/model datasets are created later from this processed layer.

They must not overwrite the clean base dataset.

---

## 12. Why Parquet is the preferred processed format

Primary processed format:

Parquet (`.parquet`)

Reasons:

- Preserves numeric dtypes better than CSV.
- Preserves timezone-aware datetime information more reliably.
- Uses compact columnar storage.
- Loads efficiently for repeated experiments.
- Avoids reparsing datetime and numeric strings whenever a new notebook
  starts.

CSV may also be exported for human inspection, but Parquet is the
canonical notebook-to-notebook hand-off format.

---

## 13. Notebook boundary

`01_smard_cleaning.ipynb` ends after the cleaned merged dataset has been
validated and persisted.

It does not create:

- calendar sin/cos features
- lag features
- rolling-price features
- train/validation/test splits
- scalers
- 168-hour input windows
- 24-hour prediction targets
- LSTM models
- CNN-LSTM models

Those tasks begin in later notebooks, starting with:

`02_features.ipynb`

---

## 14. Reproducibility notes

- The raw data should be reloadable into a fresh Kaggle session and
  produce the same cleaned output without relying on hidden notebook
  state.
- Exact SMARD source files must remain archived under `data/raw/smard/`.
- The SMARD date selection, resolution, bidding zone, units, timezone
  treatment, and missing-value decisions are documented here.
- Kaggle notebook output should be persisted using Save Version /
  Save & Run All before starting the next notebook.

---

## 15. Final Notebook 01 state

At completion of `01_smard_cleaning.ipynb`:

- Germany/Luxembourg day-ahead electricity price is selected.
- Actual grid load is selected and converted to numeric float values.
- Forecast grid load is selected and converted to numeric float values.
- Local German timestamps are correctly interpreted across DST
  transitions.
- The canonical timestamp is converted to UTC.
- Price, actual load, and forecast load are merged on UTC timestamps.
- The cleaned dataset contains:
  - `price_eur_mwh`
  - `load_actual_mwh`
  - `load_forecast_mwh`
- 97 known forecast-load values remain missing as `NaN`.
- These 97 values are intentionally not filled in Notebook 01.
- The cleaned dataset is saved as:
  `smard_hourly_clean.parquet`
- The saved Parquet dataset becomes the input to:
  `02_features.ipynb`