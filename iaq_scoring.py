from __future__ import annotations

from math import isfinite
from typing import Dict, List, Tuple, Optional, Any

# ============================================================
# IAQ Scoring (AQI-style sub-index + "worst weighted wins")
#
# Overall IAQ = max( I_signal * weight_signal )
#
# Where I_signal is computed piecewise-linearly from breakpoints:
#   (C_lo, C_hi, I_lo, I_hi)
#
# Plus: a "lethal" override that bypasses scoring if any
# sensor exceeds hard thresholds.
# ============================================================

# A breakpoint segment:
# (C_lo, C_hi, I_lo, I_hi)
BP = Tuple[float, float, float, float]


# ----------------------------
# Option B weights (your choice)
# ----------------------------
WEIGHTS_OPTION_B: Dict[str, float] = {
    "co":   1.00,
    "co2":  0.98,
    "mq2":  0.95,
    "tvoc": 0.92,
    "pm25": 0.85,
    "pm10": 0.80,
    "pm1":  0.67,
}


# ============================================================
# Lethal override thresholds
# ============================================================
# IMPORTANT: These thresholds only make sense if your readings are in the
# expected units/scales:
#   - co: ppm
#   - co2: ppm
#   - tvoc: whatever unit your TVOC value uses (ppb placeholder in SPECS)
#   - mq2: whatever "mq2" means in your code (raw / RsR0 / ppm estimate)
#
# Condition requested: strictly ">" (not ">=").
LETHAL_THRESHOLDS: Dict[str, float] = {
    "co": 18000.0,
    "co2": 40000.0,
    "mq2": 7000.0,
    "tvoc": 35000.0,
}


# ============================================================
# Breakpoint tables
# ============================================================
SPECS: Dict[str, Dict[str, Any]] = {
    # CO (ppm) — example AQI-like breakpoints
    "co": {
        "unit": "ppm",
        "weight": WEIGHTS_OPTION_B["co"],
        "bp": [
            (0.0,  3500.4,   0,  50),
            (3500.4,  4500.4,  51, 100),
            (4500.4, 5200.4, 101, 150),
            (5200.4, 5500.4, 151, 200),
            (5500.4, 6000.4, 201, 300),
            (6000.4, 7000.4, 301, 400),
            (7000.4, 7500.4, 401, 500),
        ],
    },

    # CO2 (ppm) — placeholder mapping
    "co2": {
        "unit": "ppm",
        "weight": WEIGHTS_OPTION_B["co2"],
        "bp": [
            (1000,   3000,   0,  50),
            (3000,  4000,  51, 100),
            (4000, 5400, 101, 150),
            (5400, 6000, 151, 200),
            (6000, 7000, 201, 400),
            (7000, 8000,401, 500),
        ],
    },

    # MQ2 — placeholder mapping
    "mq2": {
        "unit": "raw",
        "weight": WEIGHTS_OPTION_B["mq2"],
        "bp": [
            (0,    700,   0,  50),
            (700,  800,  51, 100),
            (800,  900, 101, 200),
            (900,  1000, 201, 400),
            (1000, 2023, 401, 500),
        ],
    },

    # TVOC — placeholder mapping
    "tvoc": {
        "unit": "ppb",
        "weight": WEIGHTS_OPTION_B["tvoc"],
        "bp": [
            (0,     150,   0,  50),
            (150,   300,  51, 100),
            (300,   500, 101, 150),
            (500,  1000, 151, 200),
            (1000, 3000, 201, 400),
            (3000, 10000,401, 500),
        ],
    },

    # PM1 — placeholder mapping
    "pm1": {
        "unit": "µg/m³",
        "weight": WEIGHTS_OPTION_B["pm1"],
        "bp": [
            (0,   10,   0,  50),
            (10,  25,  51, 100),
            (25,  50, 101, 150),
            (50,  75, 151, 200),
            (75, 150, 201, 300),
            (150, 300, 301, 500),
        ],
    },

    # PM2.5 (µg/m³) — example AQI-like breakpoints
    "pm25": {
        "unit": "µg/m³",
        "weight": WEIGHTS_OPTION_B["pm25"],
        "bp": [
            (0.0,   12.0,   0,  50),
            (12.0,  35.4,  51, 100),
            (35.4,  55.4, 101, 150),
            (55.4, 150.4, 151, 200),
            (150.4,250.4, 201, 300),
            (250.4,350.4, 301, 400),
            (350.4,500.4, 401, 500),
        ],
    },

    # PM10 (µg/m³) — example AQI-like breakpoints
    "pm10": {
        "unit": "µg/m³",
        "weight": WEIGHTS_OPTION_B["pm10"],
        "bp": [
            (0,   54,   0,  50),
            (54,  154,  51, 100),
            (154, 254, 101, 150),
            (254, 354, 151, 200),
            (354, 424, 201, 300),
            (424, 504, 301, 400),
            (504, 604, 401, 500),
        ],
    },
}


# ============================================================
# Core helpers
# ============================================================

def _to_float_or_none(x) -> Optional[float]:
    try:
        v = float(x)
    except Exception:
        return None
    if not isfinite(v):
        return None
    return v


def _clamp(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _interp_index(C: float, seg: BP) -> float:
    C_lo, C_hi, I_lo, I_hi = seg
    if C_hi == C_lo:
        return float(I_hi)
    return ((I_hi - I_lo) / (C_hi - C_lo)) * (C - C_lo) + I_lo


def subindex_from_breakpoints(C: float, breakpoints: List[BP]) -> float:
    """
    Compute I for concentration C using ordered breakpoint segments.
    Robust behavior:
    - clamps below first segment to first I_lo
    - clamps above last segment to last I_hi
    - handles "gaps" at boundaries by clamping C into the segment chosen
      (the first segment whose C_hi is >= C).
    """
    if not breakpoints:
        return float("nan")

    # Below minimum: clamp to first I_lo
    first = breakpoints[0]
    if C <= first[0]:
        return float(first[2])

    # Main: choose first segment where C <= C_hi
    for seg in breakpoints:
        C_lo, C_hi, I_lo, I_hi = seg
        if C <= C_hi:
            C_used = _clamp(C, C_lo, C_hi)
            return float(_interp_index(C_used, seg))

    # Above maximum: clamp to last I_hi
    last = breakpoints[-1]
    return float(last[3])


# ============================================================
# Lethal override logic
# ============================================================

def lethal_triggers(readings: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    Returns a list of triggers exceeded, like:
      [{"signal":"co","value":401.0,"threshold":400.0}, ...]
    Empty list means "not lethal".
    """
    hits: List[Dict[str, Any]] = []
    for sig, thr in LETHAL_THRESHOLDS.items():
        v = _to_float_or_none(readings.get(sig))
        if v is None:
            continue
        if v > float(thr):  # strictly greater, per your request
            hits.append({"signal": sig, "value": float(v), "threshold": float(thr)})
    return hits


# ============================================================
# Bucketing (4 parts) + lethal bucket handled in iaq_index()
# ============================================================

def iaq_bucket_from_float(iaq: float) -> str:
    """
    Bucket an IAQ float into 4 categories:
      0–50 excellent
      51–100 moderate
      101–200 suboptimal
      201–500 severe
    """
    x = float(iaq)
    if x <= 100.0:
        return "excellent"
    if x <= 250.0:
        return "moderate"
    if x <= 400.0:
        return "suboptimal"
    return "severe"


# ============================================================
# Scoring functions
# ============================================================

def compute_subindices(readings: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    Returns list of sub-index dicts, sorted worst-first by weighted index.

    Each element:
      {
        signal, value, unit,
        I, weight, I_weighted
      }
    """
    subs: List[Dict[str, Any]] = []

    for signal, spec in SPECS.items():
        v = _to_float_or_none(readings.get(signal))
        if v is None:
            continue

        bp = spec.get("bp", [])
        I = subindex_from_breakpoints(v, bp)

        w = float(spec.get("weight", 1.0))
        Iw = float(I) * w

        subs.append({
            "signal": signal,
            "value": float(v),
            "unit": spec.get("unit", ""),
            "I": float(I),
            "weight": float(w),
            "I_weighted": float(Iw),
        })

    subs.sort(key=lambda x: x["I_weighted"], reverse=True)
    return subs


def iaq_index(
    readings: Dict[str, float],
    cap: Optional[float] = 500.0,
) -> Dict[str, Any]:
    """
    Overall IAQ (your rule):
      IAQ = max(I_weighted)

    Plus lethal override:
      If any lethal threshold is exceeded, return bucket="lethal" and iaq=None.

    Normal return includes:
      - iaq: float|None
      - bucket: str|None  (excellent/moderate/suboptimal/severe/lethal)
      - driver: dict|None
      - subs: [...]
    """
    # 1) Lethal short-circuit
    hits = lethal_triggers(readings)
    if hits:
        return {
            "iaq": None,
            "bucket": "lethal",
            "driver": None,
            "subs": [],
            "lethal_triggers": hits,
            "note": "Lethal threshold exceeded; IAQ score bypassed.",
        }

    # 2) Usual scoring
    subs = compute_subindices(readings)

    if not subs:
        return {
            "iaq": None,
            "bucket": None,
            "driver": None,
            "subs": [],
            "note": "No valid readings to score.",
        }

    driver = subs[0]
    overall = float(driver["I_weighted"])

    if cap is not None:
        overall = _clamp(overall, 0.0, float(cap))

    return {
        "iaq": float(overall),
        "bucket": iaq_bucket_from_float(overall),
        "driver": {
            "signal": driver["signal"],
            "value": driver["value"],
            "unit": driver["unit"],
            "I": driver["I"],
            "weight": driver["weight"],
            "I_weighted": driver["I_weighted"],
        },
        "subs": subs,
    }


# ============================================================
# Optional: quick config sanity checks (runs only if you call it)
# ============================================================

def validate_specs() -> List[str]:
    """
    Returns a list of human-readable issues found in SPECS.
    Doesn't raise.
    """
    issues: List[str] = []

    for sig, spec in SPECS.items():
        bp = spec.get("bp")
        if not isinstance(bp, list) or len(bp) == 0:
            issues.append(f"{sig}: missing/empty bp list")
            continue

        # Check ordering and structure
        prev_hi = None
        for i, seg in enumerate(bp):
            if not (isinstance(seg, tuple) or isinstance(seg, list)) or len(seg) != 4:
                issues.append(f"{sig}: bp[{i}] is not a 4-tuple (C_lo,C_hi,I_lo,I_hi)")
                continue

            C_lo, C_hi, I_lo, I_hi = seg
            try:
                C_lo = float(C_lo); C_hi = float(C_hi)
                I_lo = float(I_lo); I_hi = float(I_hi)
            except Exception:
                issues.append(f"{sig}: bp[{i}] contains non-numeric values")
                continue

            if C_hi < C_lo:
                issues.append(f"{sig}: bp[{i}] has C_hi < C_lo ({C_hi} < {C_lo})")

            if prev_hi is not None and C_hi < prev_hi:
                issues.append(f"{sig}: bp[{i}] C_hi is decreasing (not ordered)")
            prev_hi = C_hi

        w = spec.get("weight", 1.0)
        try:
            w = float(w)
        except Exception:
            issues.append(f"{sig}: weight is not numeric")
            continue
        if w < 0:
            issues.append(f"{sig}: weight is negative ({w})")

    # Check lethal thresholds numeric
    for sig, thr in LETHAL_THRESHOLDS.items():
        try:
            _ = float(thr)
        except Exception:
            issues.append(f"LETHAL_THRESHOLDS[{sig}] is not numeric")

    return issues


"""
Example run

if __name__ == "__main__":
    readings_example = {
        "co": 2.2,
        "co2": 1100,
        "mq2": 250,
        "tvoc": 420,
        "pm1": 8,
        "pm25": 18,
        "pm10": 40,
    }

    result = iaq_index(readings_example, cap=500.0)
    print("IAQ:", result["iaq"])
    print("Bucket:", result.get("bucket"))
    print("Driver:", result["driver"])
    print("Top 3 (weighted worst-first):")
    for s in result["subs"][:3]:
        print(
            f"  {s['signal']}: I={s['I']:.1f}, w={s['weight']:.2f}, "
            f"Iw={s['I_weighted']:.1f} ({s['value']} {s['unit']})"
        )

    readings_lethal = {
        "co": 401,      # > 400 triggers lethal
        "co2": 900,
        "mq2": 120,
        "tvoc": 180,
        "pm1": 6,
        "pm25": 8,
        "pm10": 15,
    }
    result2 = iaq_index(readings_lethal)
    print("\nLETHAL TEST:", result2)
"""
