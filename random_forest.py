# randomforest.py
"""
RandomForest-based multi-target forecaster.

This module provides two functions:

- boot_train(csv_path, ...):
    Reads the *last N rows* of data.csv (default 200), builds supervised samples using a
    sliding window (default 45 rows) and horizon (default 15 rows ahead), trains a
    RandomForestRegressor, and saves the trained model in the same directory as the
    *main script* (the script that launched Python).

- rf_predict(csv_path, ...):
    Loads the saved model and predicts targets horizon-steps ahead using the most recent
    continuous segment with at least `window` rows.

Targets (default):
  - iaq
  - temperature
  - eCO2
  - co
  - pm2_5

Assumptions / notes:
- Your timestamps are *HKT* (Hong Kong Time). The CSV stores timestamps with no timezone
  suffix, so we explicitly interpret them as Asia/Hong_Kong (UTC+08:00, no DST).
- We do NOT cap data.csv size; we always tail-read for training/inference.
- We avoid creating training windows that cross large time gaps (default > 10 minutes),
  and we optionally treat cycle resets as session breaks.

Dependencies:
- pandas, numpy
- scikit-learn
- joblib
"""

from __future__ import annotations

import io
import json
import os
import sys
import math
import time
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union, Any

import numpy as np
import pandas as pd

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from joblib import dump, load
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


# -----------------------------
# Defaults / constants
# -----------------------------

DEFAULT_TZ_NAME = "Asia/Hong_Kong"
DEFAULT_MODEL_FILENAME = "rf_model.joblib"
DEFAULT_META_FILENAME = "rf_meta.json"

# Columns expected in CSV (status is optional and ignored for modeling)
TIMESTAMP_COL = "timestamp"
STATUS_COL = "status"

# Default targets (multi-output)
DEFAULT_TARGET_COLS: List[str] = ["iaq", "temperature", "eCO2", "co", "pm2_5"]

# Optional aliases to tolerate common column naming differences.
# If you want to be strict, you can remove this and require exact names.
TARGET_ALIASES: Dict[str, List[str]] = {
    "eCO2": ["eCO2", "eco2", "e_co2", "eCO₂"],
    "pm2_5": ["pm2_5", "pm2.5", "pm25", "pm_2_5", "PM2_5", "PM2.5", "PM25"],
    "iaq": ["iaq", "IAQ"],
    "temperature": ["temperature", "temp", "Temp", "Temperature"],
    "co": ["co", "CO"],
}


# -----------------------------
# Helper utilities
# -----------------------------

def _default_save_dir() -> Path:
    """
    Save in the same directory as the *main* script that launched Python.
    """
    try:
        argv0 = sys.argv[0]
        if argv0:
            return Path(argv0).resolve().parent
    except Exception:
        pass
    return Path.cwd()


def _tail_csv(csv_path: Union[str, Path], n_rows: int) -> pd.DataFrame:
    """
    Efficient-ish tail reader: returns a DataFrame containing the header + last n_rows.
    """
    csv_path = Path(csv_path)

    if n_rows <= 0:
        raise ValueError("n_rows must be > 0")

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with csv_path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        if file_size == 0:
            return pd.DataFrame()

        # header
        f.seek(0)
        header = f.readline().decode("utf-8", errors="replace").strip("\n\r")
        if not header:
            return pd.DataFrame()

        block_size = 64 * 1024
        blocks: List[bytes] = []
        newlines = 0
        pos = file_size
        target_newlines = n_rows + 2

        while pos > 0 and newlines < target_newlines:
            read_size = min(block_size, pos)
            pos -= read_size
            f.seek(pos)
            data = f.read(read_size)
            blocks.append(data)
            newlines += data.count(b"\n")

        tail_bytes = b"".join(reversed(blocks))
        lines = tail_bytes.splitlines()

        decoded = [ln.decode("utf-8", errors="replace") for ln in lines if ln.strip() != b""]
        if not decoded:
            return pd.DataFrame(columns=header.split(","))

        decoded = [ln for ln in decoded if ln.strip() != header.strip()]
        tail_lines = decoded[-n_rows:] if len(decoded) > n_rows else decoded
        csv_text = header + "\n" + "\n".join(tail_lines)
        print(tail_lines)

    return pd.read_csv(io.StringIO(csv_text))


def _ensure_tzinfo(tz_name: str) -> Any:
    if ZoneInfo is None:
        raise RuntimeError(
            "zoneinfo is unavailable on this Python. "
            "Use Python 3.9+ or install backports.zoneinfo (not handled here)."
        )
    return ZoneInfo(tz_name)


def _parse_and_clean(
    df: pd.DataFrame,
    tz_name: str = DEFAULT_TZ_NAME,
    drop_status: bool = True,
) -> pd.DataFrame:
    """
    - Parses timestamp (naive) and localizes as HKT (Asia/Hong_Kong) then converts to UTC.
    - Coerces numeric columns to floats.
    - Sorts by time.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if TIMESTAMP_COL not in df.columns:
        raise ValueError(f"CSV missing required column: {TIMESTAMP_COL}")

    df = df.copy()

    # Drop status by default (often derived from IAQ -> leakage risk)
    if drop_status and STATUS_COL in df.columns:
        df = df.drop(columns=[STATUS_COL])

    tz = _ensure_tzinfo(tz_name)
    ts = pd.to_datetime(df[TIMESTAMP_COL], errors="coerce")
    df = df.loc[~ts.isna()].copy()
    ts = ts.loc[~ts.isna()]

    ts_hkt = ts.dt.tz_localize(tz)
    ts_utc = ts_hkt.dt.tz_convert("UTC")
    df["timestamp_hkt"] = ts_hkt
    df["timestamp_utc"] = ts_utc

    # Coerce all non-timestamp columns to numeric
    for c in df.columns:
        if c in (TIMESTAMP_COL, "timestamp_hkt", "timestamp_utc"):
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.sort_values("timestamp_utc").reset_index(drop=True)

    # dt_seconds feature
    df["dt_seconds"] = df["timestamp_utc"].diff().dt.total_seconds()
    df["dt_seconds"] = df["dt_seconds"].fillna(0.0).clip(lower=0.0)

    # cyclical time features in HKT
    h = df["timestamp_hkt"].dt.hour.astype(float)
    dow = df["timestamp_hkt"].dt.dayofweek.astype(float)
    df["hour_sin"] = np.sin(2.0 * np.pi * h / 24.0)
    df["hour_cos"] = np.cos(2.0 * np.pi * h / 24.0)
    df["dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    df["dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)

    return df


def _segment_continuous(
    df: pd.DataFrame,
    max_gap_seconds: float = 600.0,
    break_on_cycle_reset: bool = True,
    cycle_col: str = "cycle",
) -> pd.DataFrame:
    """
    Creates a segment_id that increases when:
    - dt_seconds > max_gap_seconds, or
    - cycle decreases (reset) if break_on_cycle_reset is True.
    """
    if df.empty:
        return df

    df = df.copy()
    gap_break = df["dt_seconds"] > float(max_gap_seconds)

    if break_on_cycle_reset and cycle_col in df.columns:
        cycle_diff = df[cycle_col].diff()
        cycle_break = (cycle_diff < 0).fillna(False)
    else:
        cycle_break = pd.Series(False, index=df.index)

    first = pd.Series(False, index=df.index)
    first.iloc[0] = True

    breaks = first | gap_break | cycle_break
    df["segment_id"] = breaks.cumsum().astype(int)

    return df


def _resolve_target_cols(
    df: pd.DataFrame,
    requested: Sequence[str],
) -> List[str]:
    """
    Resolves requested target names against df.columns, using TARGET_ALIASES.
    Returns the *actual column names* that will be used (and saved in the model bundle).
    """
    cols = set(df.columns)
    resolved: List[str] = []

    for name in requested:
        if name in cols:
            resolved.append(name)
            continue

        # try aliases
        aliases = TARGET_ALIASES.get(name, [])
        hit = None
        for a in aliases:
            if a in cols:
                hit = a
                break

        if hit is None:
            raise ValueError(
                f"Target column '{name}' not found in CSV. "
                f"Tried aliases: {aliases}. Available columns: {sorted(df.columns)}"
            )
        resolved.append(hit)

    # keep order, ensure uniqueness
    out: List[str] = []
    seen = set()
    for c in resolved:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out


@dataclass
class SupervisedData:
    X: np.ndarray
    y: np.ndarray  # shape: (n_samples, n_targets)
    feature_names: List[str]
    target_cols: List[str]
    sample_times_utc: np.ndarray  # datetime64[ns] (tz-naive but UTC-based values)


def _build_supervised(
    df: pd.DataFrame,
    window: int,
    horizon: int,
    feature_cols: Sequence[str],
    target_cols: Sequence[str],
) -> SupervisedData:
    """
    Builds supervised samples (multi-output):

      X[t] = flattened features for rows (t-window+1 ... t)
      y[t] = targets at row (t + horizon)  -> vector length n_targets

    Only within each segment_id.
    """
    target_cols = list(target_cols)

    if df.empty:
        return SupervisedData(
            X=np.zeros((0, 0), dtype=np.float32),
            y=np.zeros((0, len(target_cols)), dtype=np.float32),
            feature_names=[],
            target_cols=target_cols,
            sample_times_utc=np.array([], dtype="datetime64[ns]"),
        )

    if "segment_id" not in df.columns:
        raise ValueError("df must have segment_id column (call _segment_continuous first).")

    window = int(window)
    horizon = int(horizon)
    if window <= 0 or horizon <= 0:
        raise ValueError("window and horizon must be > 0")

    # Ensure required columns exist
    missing_feat = [c for c in feature_cols if c not in df.columns]
    if missing_feat:
        raise ValueError(f"Missing feature columns in data: {missing_feat}")

    missing_tgt = [c for c in target_cols if c not in df.columns]
    if missing_tgt:
        raise ValueError(f"Missing target columns in data: {missing_tgt}")

    # Feature names: lag 0 = most recent row (t)
    feature_names: List[str] = []
    for lag in range(window - 1, -1, -1):
        for c in feature_cols:
            feature_names.append(f"{c}_lag{lag}")

    X_list: List[np.ndarray] = []
    y_list: List[np.ndarray] = []
    t_list: List[np.datetime64] = []

    for _, seg in df.groupby("segment_id", sort=True):
        seg = seg.copy()

        # Forward fill numeric cols; do not fill timestamps
        fill_cols = [c for c in seg.columns if c not in (TIMESTAMP_COL, "timestamp_hkt", "timestamp_utc")]
        seg[fill_cols] = seg[fill_cols].ffill()

        if len(seg) < window + horizon:
            continue

        seg_feat = seg.loc[:, feature_cols].to_numpy(dtype=np.float32, copy=False)          # (n, n_feat)
        seg_targets = seg.loc[:, target_cols].to_numpy(dtype=np.float32, copy=False)       # (n, n_tgt)
        seg_time = seg["timestamp_utc"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()

        for end_idx in range(window - 1, len(seg) - horizon):
            start_idx = end_idx - window + 1
            window_block = seg_feat[start_idx : end_idx + 1]  # (window, n_feat)

            if np.isnan(window_block).any():
                continue

            y_vec = seg_targets[end_idx + horizon]  # (n_tgt,)
            if np.isnan(y_vec).any():
                continue

            x = window_block.reshape(-1)  # (window * n_feat,)
            X_list.append(x)
            y_list.append(y_vec.astype(np.float32, copy=False))
            t_list.append(seg_time[end_idx])

    if not X_list:
        return SupervisedData(
            X=np.zeros((0, len(feature_names)), dtype=np.float32),
            y=np.zeros((0, len(target_cols)), dtype=np.float32),
            feature_names=feature_names,
            target_cols=target_cols,
            sample_times_utc=np.array([], dtype="datetime64[ns]"),
        )

    X = np.vstack(X_list).astype(np.float32, copy=False)
    y = np.vstack(y_list).astype(np.float32, copy=False)
    sample_times_utc = np.array(t_list, dtype="datetime64[ns]")

    order = np.argsort(sample_times_utc)
    X = X[order]
    y = y[order]
    sample_times_utc = sample_times_utc[order]

    return SupervisedData(
        X=X,
        y=y,
        feature_names=feature_names,
        target_cols=target_cols,
        sample_times_utc=sample_times_utc,
    )


def _pick_feature_cols(df: pd.DataFrame) -> List[str]:
    """
    Picks numeric feature columns to use for modeling.

    We exclude:
    - raw 'timestamp' string column
    - timestamp_hkt / timestamp_utc (not numeric)
    - segment_id
    """
    exclude = {TIMESTAMP_COL, "timestamp_hkt", "timestamp_utc", "segment_id"}
    cols: List[str] = []
    for c in df.columns:
        if c in exclude:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)

    cols = sorted(cols)  # deterministic
    return cols


def _train_val_split_time(
    X: np.ndarray,
    y: np.ndarray,
    val_fraction: float = 0.2,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if X.shape[0] != y.shape[0]:
        raise ValueError("X and y length mismatch")
    n = X.shape[0]
    if n < 5:
        # too small; treat all as train
        if y.ndim == 1:
            y_empty = np.zeros((0,), dtype=y.dtype)
        else:
            y_empty = np.zeros((0, y.shape[1]), dtype=y.dtype)
        return X, np.zeros((0, X.shape[1]), dtype=X.dtype), y, y_empty

    split = int(max(1, min(n - 1, round(n * (1.0 - val_fraction)))))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]
    return X_train, X_val, y_train, y_val


def _metrics_multioutput(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_cols: Sequence[str],
) -> Dict[str, Any]:
    """
    Returns per-target MAE/RMSE and macro-averages.
    Avoids mean_squared_error(..., squared=False) for sklearn compatibility.
    """
    target_cols = list(target_cols)
    k = y_true.shape[1]

    mae_by: Dict[str, float] = {}
    rmse_by: Dict[str, float] = {}

    for j in range(k):
        yt = y_true[:, j]
        yp = y_pred[:, j]
        mae = float(mean_absolute_error(yt, yp))
        mse = mean_squared_error(yt, yp)  # no squared kwarg
        rmse = float(np.sqrt(mse))
        mae_by[target_cols[j]] = mae
        rmse_by[target_cols[j]] = rmse

    mae_macro = float(np.mean(list(mae_by.values()))) if mae_by else float("nan")
    rmse_macro = float(np.mean(list(rmse_by.values()))) if rmse_by else float("nan")

    return {
        "val_mae_macro": mae_macro,
        "val_rmse_macro": rmse_macro,
        "val_mae_by_target": mae_by,
        "val_rmse_by_target": rmse_by,
    }


# -----------------------------
# Public API
# -----------------------------

def boot_train(
    csv_path: Union[str, Path],
    *,
    n_rows: int = 1000,
    window: int = 60,
    horizon: int = 30,
    tz_name: str = DEFAULT_TZ_NAME,
    max_gap_seconds: float = 1200.0,
    break_on_cycle_reset: bool = True,
    model_filename: str = DEFAULT_MODEL_FILENAME,
    meta_filename: str = DEFAULT_META_FILENAME,
    save_dir: Optional[Union[str, Path]] = None,
    target_cols: Optional[Sequence[str]] = None,
    # RF hyperparams
    n_estimators: int = 300,
    random_state: int = 42,
    n_jobs: int = -1,
    min_samples_leaf: int = 3,
    max_features: Union[str, float, int, None] = "sqrt",
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Boot-trains a RandomForestRegressor using the *last n_rows* from csv_path.

    The saved model predicts multiple targets at (t + horizon) using features from last `window` rows.
    """
    t0 = time.time()

    if save_dir is None:
        save_dir_path = _default_save_dir()
    else:
        save_dir_path = Path(save_dir).expanduser().resolve()

    save_dir_path.mkdir(parents=True, exist_ok=True)
    model_path = save_dir_path / model_filename
    meta_path = save_dir_path / meta_filename

    raw = _tail_csv(csv_path, n_rows=n_rows)
    df = _parse_and_clean(raw, tz_name=tz_name, drop_status=True)

    if df.empty:
        raise ValueError("No usable rows after parsing timestamps.")

    df = _segment_continuous(
        df,
        max_gap_seconds=max_gap_seconds,
        break_on_cycle_reset=break_on_cycle_reset,
        cycle_col="cycle",
    )

    feature_cols = _pick_feature_cols(df)

    requested_targets = list(target_cols) if target_cols is not None else list(DEFAULT_TARGET_COLS)
    resolved_targets = _resolve_target_cols(df, requested_targets)

    if verbose:
        print(f"[boot_train] Rows (tail): {len(raw)} | usable: {len(df)}")
        print(f"[boot_train] Feature cols ({len(feature_cols)}): {feature_cols}")
        print(f"[boot_train] Targets (requested): {requested_targets}")
        print(f"[boot_train] Targets (resolved):  {resolved_targets}")

    sd = _build_supervised(
        df=df,
        window=window,
        horizon=horizon,
        feature_cols=feature_cols,
        target_cols=resolved_targets,
    )

    if sd.X.shape[0] < 10:
        raise ValueError(
            f"Not enough training samples built (got {sd.X.shape[0]}). "
            f"Need more continuous data. Try increasing n_rows or lowering window/horizon."
        )

    X_train, X_val, y_train, y_val = _train_val_split_time(sd.X, sd.y, val_fraction=0.2)

    rf = RandomForestRegressor(
        n_estimators=int(n_estimators),
        random_state=int(random_state),
        n_jobs=int(n_jobs),
        min_samples_leaf=int(min_samples_leaf),
        max_features=max_features,
    )
    rf.fit(X_train, y_train)

    metrics: Dict[str, Any]
    if X_val.shape[0] > 0:
        pred_val = rf.predict(X_val)
        metrics = {
            "val_n": int(X_val.shape[0]),
            **_metrics_multioutput(y_val, pred_val, target_cols=sd.target_cols),
        }
    else:
        metrics = {
            "val_n": 0,
            "val_mae_macro": None,
            "val_rmse_macro": None,
            "val_mae_by_target": None,
            "val_rmse_by_target": None,
        }

    rf_final = RandomForestRegressor(
        n_estimators=int(n_estimators),
        random_state=int(random_state),
        n_jobs=int(n_jobs),
        min_samples_leaf=int(min_samples_leaf),
        max_features=max_features,
    )
    rf_final.fit(sd.X, sd.y)

    bundle = {
        "model": rf_final,
        "feature_names": sd.feature_names,
        "feature_cols": list(feature_cols),
        "window": int(window),
        "horizon": int(horizon),
        "tz_name": tz_name,
        "max_gap_seconds": float(max_gap_seconds),
        "break_on_cycle_reset": bool(break_on_cycle_reset),
        "target_cols": list(sd.target_cols),  # NEW (multi-target)
        "trained_at_utc": pd.Timestamp.utcnow().isoformat(),
    }
    dump(bundle, model_path)

    meta = {
        "model_path": str(model_path),
        "meta_path": str(meta_path),
        "trained_at_utc": bundle["trained_at_utc"],
        "csv_path": str(Path(csv_path).resolve()),
        "tail_rows_used": int(n_rows),
        "usable_rows": int(len(df)),
        "samples": int(sd.X.shape[0]),
        "features_per_step": int(len(feature_cols)),
        "window": int(window),
        "horizon": int(horizon),
        "target_cols": list(sd.target_cols),
        "targets_n": int(len(sd.target_cols)),
        "tz_name": tz_name,
        "max_gap_seconds": float(max_gap_seconds),
        "break_on_cycle_reset": bool(break_on_cycle_reset),
        "rf_params": {
            "n_estimators": int(n_estimators),
            "random_state": int(random_state),
            "n_jobs": int(n_jobs),
            "min_samples_leaf": int(min_samples_leaf),
            "max_features": max_features,
        },
        "validation": metrics,
        "environment": {
            "python": sys.version.replace("\n", " "),
            "platform": platform.platform(),
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    meta["elapsed_seconds"] = float(elapsed)

    if verbose:
        print(f"[boot_train] Saved model to: {model_path}")
        print(f"[boot_train] Saved meta  to: {meta_path}")
        print(f"[boot_train] Metrics: {metrics}")
        print(f"[boot_train] Elapsed: {elapsed:.2f}s")

    return meta


def rf_predict(
    csv_path: Union[str, Path],
    *,
    model_path: Optional[Union[str, Path]] = None,
    meta_path: Optional[Union[str, Path]] = None,
    n_rows: int = 60,
    tz_name: str = DEFAULT_TZ_NAME,
    max_gap_seconds: float = 800.0,
    break_on_cycle_reset: bool = True,
    return_debug: bool = False,
    verbose: bool = False,
) -> Union[float, Dict[str, Any]]:
    """
    Predicts targets at (t + horizon) using the most recent continuous data.

    Returns:
      - If model has 1 target and return_debug=False: float (backward compatible)
      - Otherwise: dict {target_name: prediction}
      - If return_debug=True: dict with predictions + debug info
    """
    save_dir = _default_save_dir()

    if model_path is None:
        model_path = save_dir / DEFAULT_MODEL_FILENAME
    else:
        model_path = Path(model_path).expanduser().resolve()

    if meta_path is None:
        meta_path = save_dir / DEFAULT_META_FILENAME
    else:
        meta_path = Path(meta_path).expanduser().resolve()

    if not Path(model_path).exists():
        raise FileNotFoundError(f"Model not found: {model_path} (run boot_train first)")

    bundle = load(model_path)
    model = bundle["model"]
    window = int(bundle["window"])
    horizon = int(bundle["horizon"])
    feature_cols = list(bundle["feature_cols"])
    feature_names = list(bundle["feature_names"])

    # Backward compatibility: old bundles used "target_col"
    if "target_cols" in bundle and bundle["target_cols"] is not None:
        target_cols = list(bundle["target_cols"])
    else:
        target_cols = [str(bundle.get("target_col", "iaq"))]

    raw = _tail_csv(csv_path, n_rows=n_rows)
    df = _parse_and_clean(raw, tz_name=tz_name, drop_status=True)

    if df.empty:
        raise ValueError("No usable rows after parsing timestamps for prediction.")

    df = _segment_continuous(
        df,
        max_gap_seconds=max_gap_seconds,
        break_on_cycle_reset=break_on_cycle_reset,
        cycle_col="cycle",
    )

    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Prediction data is missing feature columns used during training: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    seg_ids = df["segment_id"].unique().tolist()
    seg_ids.sort()
    chosen_seg_id = None
    chosen_seg = None
    for sid in reversed(seg_ids):
        seg = df[df["segment_id"] == sid].copy()
        if len(seg) >= window:
            chosen_seg_id = int(sid)
            chosen_seg = seg
            break

    if chosen_seg is None:
        raise ValueError(
            f"Not enough recent continuous rows to predict. Need at least window={window} rows "
            f"in one segment, but none found in last n_rows={n_rows}."
        )

    fill_cols = [c for c in chosen_seg.columns if c not in (TIMESTAMP_COL, "timestamp_hkt", "timestamp_utc")]
    chosen_seg[fill_cols] = chosen_seg[fill_cols].ffill()

    last_block = chosen_seg.iloc[-window:].copy()
    feat_mat = last_block.loc[:, feature_cols].to_numpy(dtype=np.float32, copy=False)
    if np.isnan(feat_mat).any():
        raise ValueError("Recent window contains NaNs even after forward-fill; cannot predict reliably.")

    x = feat_mat.reshape(-1).astype(np.float32, copy=False)

    expected_len = len(feature_names)
    if x.shape[0] != expected_len:
        raise RuntimeError(
            f"Feature length mismatch: got {x.shape[0]} but model expects {expected_len}. "
            f"(window={window}, n_features_per_step={len(feature_cols)})"
        )

    pred_arr = model.predict(x.reshape(1, -1))
    # pred_arr: shape (1, k) for multioutput, or (1,) / (1,1) depending on sklearn/version
    pred_vec = np.asarray(pred_arr).reshape(1, -1)[0]

    predictions: Dict[str, float] = {}
    if len(target_cols) == pred_vec.shape[0]:
        for i, name in enumerate(target_cols):
            predictions[name] = float(pred_vec[i])
    else:
        # Fallback if model reports a different shape than expected
        # (should not happen if trained with this module)
        predictions = {"prediction": float(pred_vec[0])}

    if verbose:
        last_ts_hkt = last_block["timestamp_hkt"].iloc[-1]
        print(f"[rf_predict] Using segment_id={chosen_seg_id} with {len(chosen_seg)} rows.")
        print(f"[rf_predict] Last timestamp (HKT): {last_ts_hkt}")
        print(f"[rf_predict] Predicting at horizon={horizon} steps ahead: {predictions}")

    if not return_debug:
        # Back-compat: if single target, return float like the old version did
        if len(predictions) == 1 and len(target_cols) == 1:
            return float(next(iter(predictions.values())))
        return predictions

    debug = {
        "predictions": predictions,
        "target_cols": target_cols,
        "window": window,
        "horizon": horizon,
        "tz_name": tz_name,
        "max_gap_seconds": float(max_gap_seconds),
        "break_on_cycle_reset": bool(break_on_cycle_reset),
        "model_path": str(Path(model_path).resolve()),
        "meta_path": str(Path(meta_path).resolve()) if Path(meta_path).exists() else None,
        "tail_rows_read": int(n_rows),
        "chosen_segment_id": chosen_seg_id,
        "chosen_segment_rows": int(len(chosen_seg)),
        "window_last_timestamp_hkt": str(last_block["timestamp_hkt"].iloc[-1]),
        "window_last_timestamp_utc": str(last_block["timestamp_utc"].iloc[-1]),
    }
    return debug


# -----------------------------
# Optional CLI
# -----------------------------
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="RandomForest multi-target forecaster (boot_train / rf_predict).")
    p.add_argument("csv", help="Path to data.csv")
    p.add_argument("--train", action="store_true", help="Run boot_train")
    p.add_argument("--predict", action="store_true", help="Run rf_predict")
    p.add_argument("--verbose", action="store_true", help="Verbose output")
    args = p.parse_args()

    if not args.train and not args.predict:
        p.error("Choose --train and/or --predict")

    if args.train:
        info = boot_train(args.csv, verbose=args.verbose)
        print(json.dumps(info, indent=2))

    if args.predict:
        pred = rf_predict(args.csv, return_debug=True, verbose=args.verbose)
        print(json.dumps(pred, indent=2))