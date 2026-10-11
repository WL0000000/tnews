"""Rule-based read of what a release means for NQ.

The rules assume the current backdrop: the Fed is fighting inflation (it hiked in
September 2026), so hotter inflation or a stronger labour market means more hikes,
higher yields and weaker tech stocks. If the Fed switches to cutting because the
economy is weak, set regime = "growth" in config and weak data becomes the bad news.
"""
from __future__ import annotations

from dataclasses import dataclass

# +1 means "higher than forecast is good for NQ", -1 means "higher is bad for NQ"
INFLATION_REGIME = {
    "CPI m/m": (-1, 1.0), "Core CPI m/m": (-1, 2.0), "CPI y/y": (-1, 0.5), "Core CPI y/y": (-1, 0.5),
    "PPI m/m": (-1, 1.0), "PPI y/y": (-1, 0.3),
    "Non-Farm Employment Change": (-1, 1.0), "Unemployment Rate": (+1, 1.0),
    "Average Hourly Earnings m/m": (-1, 1.0),
}
GROWTH_REGIME = {
    **INFLATION_REGIME,
    "Non-Farm Employment Change": (+1, 1.5), "Unemployment Rate": (-1, 1.5),
}
# Size of a surprise that counts as one "unit"
UNIT = {"Non-Farm Employment Change": 50.0, "Unemployment Rate": 0.1}


@dataclass
class Verdict:
    label: str             # Negative / Neutral / Positive (for NQ)
    strength: str          # "", "mildly", "strongly"
    lines: list[str]       # one line per number: actual vs forecast
    reason: str

    def headline(self) -> str:
        if self.strength:
            return f"{self.strength.capitalize()} {self.label.lower()} for NQ"
        return f"{self.label} for NQ"


def judge_data(readings, forecasts: dict[str, float | None], regime: str = "inflation") -> Verdict:
    table = GROWTH_REGIME if regime == "growth" else INFLATION_REGIME
    score, lines, drivers = 0.0, [], []
    for r in readings:
        unit = "K" if r.unit == "K" else "%"
        fc = forecasts.get(r.label)
        if fc is not None and r.unit == "K":
            fc = fc / 1000.0            # calendar says 150K -> 150000; BLS gives thousands
        act = f"{r.value:+.0f}{unit}" if r.unit == "K" else f"{r.value:.1f}%"
        if fc is None:
            lines.append(f"{r.label}: {act} (no forecast)")
            continue
        fcs = f"{fc:+.0f}{unit}" if r.unit == "K" else f"{fc:.1f}%"
        diff = r.value - fc
        lines.append(f"{r.label}: {act} vs {fcs} expected")
        sign, w = table.get(r.label, (0, 0))
        u = UNIT.get(r.label, 0.1)
        units = round(diff / u, 6)
        if units and sign:
            score += sign * w * max(-3, min(3, units))
            drivers.append(f"{r.label} {'above' if diff > 0 else 'below'} forecast")
    if abs(score) < 0.75:
        label, strength = "Neutral", ""
    else:
        label = "Positive" if score > 0 else "Negative"
        strength = "strongly" if abs(score) >= 3 else "mildly"
    if not drivers:
        reason = "Numbers in line with forecasts."
    elif label == "Negative":
        reason = "; ".join(drivers) + ". Hotter data means more Fed hikes and higher yields, which hits tech."
    elif label == "Positive":
        reason = "; ".join(drivers) + ". Cooler data eases Fed hike fears and yields, which helps tech."
    else:
        reason = "; ".join(drivers) + ". Surprises are small or offset each other."
    return Verdict(label, strength, lines, reason)


def judge_fed(decision: str | None, upper: float | None, expected_upper: float | None,
              dissents: int, prev_upper: float | None = None) -> Verdict:
    lines = []
    if decision:
        lines.append(f"Decision: {decision}" + (f", upper bound {upper:.2f}%" if upper is not None else ""))
    if expected_upper is not None:
        lines.append(f"Expected upper bound: {expected_upper:.2f}%")
    if dissents:
        lines.append(f"Dissents: {dissents}")
    if upper is None or expected_upper is None:
        return Verdict("Neutral", "", lines, "Could not compare the decision with expectations; read the statement tone.")
    diff = round(upper - expected_upper, 4)
    if diff > 0:
        return Verdict("Negative", "strongly", lines, "The Fed hiked more than expected.")
    if diff < 0:
        return Verdict("Positive", "strongly", lines, "The Fed was easier than expected.")
    reason = "Decision matched expectations, so the wording and the press conference decide the move."
    return Verdict("Neutral", "", lines, reason)
