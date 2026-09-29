---
document_id: static_model_evaluation_v1
document_type: static_model_documentation
model_version: cnn_lstm_v1_frozen
dynamic_data: false
---

# Static Electricity Forecast Model Evaluation

## Document purpose

This document contains static historical information about the forecasting
models. It does not contain today's live forecast or yesterday's live
evaluation.

Dynamic production data must be retrieved separately from the backend.

## Production configuration

- Production model: CNN-LSTM
- Model version: cnn_lstm_v1_frozen
- Forecast origin: 12:00 UTC
- Forecast horizon: 24 consecutive hours
- Engineered input window: 168 hours
- Minimum raw history required: 336 hours
- Canonical storage timezone: UTC
- Display timezone: Europe/Berlin
- Automatic retraining: disabled
- Target unit: EUR/MWh

## CNN-LSTM architecture

- First Conv1D filters: 32
- First Conv1D kernel: 3
- Pool size: 2
- Second Conv1D filters: 32
- Second Conv1D kernel: 3
- LSTM units: 64
- LSTM dropout: 0.2
- Dense units: 64
- Dense dropout: 0.2
- Forecast outputs: 24

## Historical evaluation period

- First forecast origin: 2024-05-15T05:00:00+00:00
- Last forecast origin: 2024-08-31T19:00:00+00:00

These dates refer to historical offline evaluation and must not be interpreted
as current production dates.

## Full historical test metrics

| model        |     N |     MAE |    RMSE |   sMAPE |   MAPE_guarded |   MAPE_excluded |
|:-------------|------:|--------:|--------:|--------:|---------------:|----------------:|
| CNN-LSTM     | 62568 | 21.3673 | 28.6713 | 46.9909 |        109.399 |            3336 |
| LSTM         | 62568 | 22.4238 | 29.9138 | 46.8656 |        121.75  |            3336 |
| Weekly naive | 62568 | 27.3307 | 37.1858 | 62.3417 |        114.633 |            3336 |
| Daily naive  | 62568 | 27.3463 | 38.6098 | 60.7425 |        112.83  |            3336 |

These metrics use all available hourly forecast origins.

## Historical 12:00 UTC metrics

|   forecast_origin_hour_utc |   forecast_count | model        |    N |     MAE |    RMSE |   sMAPE |   MAPE_guarded |   MAPE_excluded |
|---------------------------:|-----------------:|:-------------|-----:|--------:|--------:|--------:|---------------:|----------------:|
|                         12 |              109 | CNN-LSTM     | 2616 | 21.0239 | 27.7876 | 48.0606 |        99.1261 |             140 |
|                         12 |              109 | LSTM         | 2616 | 22.2755 | 29.4323 | 48.0395 |       119.349  |             140 |
|                         12 |              109 | Daily naive  | 2616 | 27.3373 | 38.577  | 60.8443 |       112.758  |             140 |
|                         12 |              109 | Weekly naive | 2616 | 27.3965 | 37.2506 | 62.5679 |       115.5    |             140 |

These metrics only use forecasts issued at 12:00 UTC and therefore correspond
more closely to the planned deployment schedule.

## Historical subset evaluation

| subset                | model        |     N |     MAE |    RMSE |    sMAPE |   MAPE_guarded |   MAPE_excluded |
|:----------------------|:-------------|------:|--------:|--------:|---------:|---------------:|----------------:|
| All                   | Daily naive  | 62568 | 27.3463 | 38.6098 |  60.7425 |       112.83   |            3336 |
| All                   | Weekly naive | 62568 | 27.3307 | 37.1858 |  62.3417 |       114.633  |            3336 |
| All                   | LSTM         | 62568 | 22.4238 | 29.9138 |  46.8656 |       121.75   |            3336 |
| All                   | CNN-LSTM     | 62568 | 21.3673 | 28.6713 |  46.9909 |       109.399  |            3336 |
| Top 5% absolute price | Daily naive  |  3144 | 51.6175 | 66.0997 |  37.8617 |        29.5411 |               0 |
| Top 5% absolute price | Weekly naive |  3144 | 40.431  | 50.8534 |  26.072  |        22.5543 |               0 |
| Top 5% absolute price | LSTM         |  3144 | 42.5129 | 51.144  |  26.9565 |        22.9269 |               0 |
| Top 5% absolute price | CNN-LSTM     |  3144 | 48.1118 | 56.1645 |  31.3435 |        26.2273 |               0 |
| Negative price        | Daily naive  |  5763 | 34.0829 | 46.2662 | 167.941  |       525.629  |            2040 |
| Negative price        | Weekly naive |  5763 | 38.1427 | 49.5285 | 170.131  |       621.011  |            2040 |
| Negative price        | LSTM         |  5763 | 40.3715 | 46.5097 | 181.563  |       653.373  |            2040 |
| Negative price        | CNN-LSTM     |  5763 | 37.0958 | 43.2248 | 185.711  |       597.729  |            2040 |
| Weekday               | Daily naive  | 44484 | 26.3714 | 37.8976 |  52.3028 |        71.1728 |            1166 |
| Weekday               | Weekly naive | 44484 | 26.5593 | 36.1419 |  48.7772 |        80.0585 |            1166 |
| Weekday               | LSTM         | 44484 | 21.147  | 28.9387 |  33.2852 |        85.3811 |            1166 |
| Weekday               | CNN-LSTM     | 44484 | 20.047  | 27.7798 |  32.7623 |        79.9018 |            1166 |
| Weekend               | Daily naive  | 18084 | 29.7442 | 40.3081 |  81.5031 |       226.219  |            2170 |
| Weekend               | Weekly naive | 18084 | 29.2283 | 39.6367 |  95.7084 |       208.745  |            2170 |
| Weekend               | LSTM         | 18084 | 25.5646 | 32.1868 |  80.2716 |       220.748  |            2170 |
| Weekend               | CNN-LSTM     | 18084 | 24.6149 | 30.7546 |  81.9912 |       189.692  |            2170 |

## Metric definitions

MAE is the mean absolute error in EUR/MWh.

RMSE is the square root of mean squared error in EUR/MWh and gives additional
weight to large forecast errors.

sMAPE is the symmetric mean absolute percentage error.

Guarded MAPE excludes observations where the absolute actual price is below
1.0 EUR/MWh. The excluded observation count must always be
reported with guarded MAPE.

## Model-selection interpretation

CNN-LSTM has lower overall historical MAE and RMSE than the basic LSTM, but it
does not outperform the LSTM for every metric, forecast horizon or price
condition.

Its selection should be described as primarily based on validation performance,
overall MAE and overall RMSE.

## Input rules

The production model requires exactly 168 complete engineered hourly rows.

The raw-data pipeline requires at least 336 continuous hours because the
feature calculations require a 168-hour warm-up period.

The model uses historical actual load and historical forecast-load values. It
does not use future actual load.

Missing input values must cause the production prediction to fail safely.
The backend must not refit scalers or silently invent missing model inputs.

## Methodological limitations

The historical test period was inspected during model development and should
be described as a development evaluation rather than a fully untouched
publication-grade holdout.

Forecast windows near chronological split boundaries contain overlapping
24-hour target periods. Completely correcting the training boundary would
require a future retraining experiment.

Historical performance does not guarantee current performance. Production
performance must be recalculated daily using the previous scheduled forecast
and its corresponding 24 actual prices.

## Static and dynamic RAG separation

Static retrieval may use this document for:

- architecture questions
- feature questions
- historical model performance
- metric definitions
- model limitations

Dynamic questions must use the backend for:

- today's latest forecast
- yesterday's forecast
- yesterday's actual prices
- yesterday's MAE
- yesterday's RMSE
- yesterday's sMAPE
- yesterday's guarded MAPE
- evaluation availability status

Dynamic values must never be inferred from the historical example payload.
