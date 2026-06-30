from datetime import datetime
from math import cos, pi, sin
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


APP_VERSION = "backend-demo-0.1.0"

app = FastAPI(title="Gravity Storage Dispatch Showcase API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5174", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LABELS = [f"{hour:02d}:00" for hour in range(24)]
QUARTER_LABELS = [f"{8 + idx // 4:02d}:{(idx % 4) * 15:02d}" for idx in range(16)]

DEFAULT_SCENARIO = {
    "application": "风光峰谷蓄调",
    "season": "夏季",
    "building": "园区综合能源站",
    "layers": 35,
    "columns": 33,
    "blockMass": 25,
    "efficiency": 0.85,
    "maxPower": 25.92,
    "initialSoc": 62,
}

DEFAULT_PLANNING = {
    "capacityBoundary": 100,
    "switchLimit": 7,
    "rollingCycle": 15,
    "seasonReserve": 18,
}

DEFAULT_OPTIMIZATION = {
    "soc": 62,
    "revenueWeight": 0.45,
    "peakWeight": 0.35,
    "switchWeight": 0.2,
    "popSize": 80,
    "generations": 120,
    "exportPareto": True,
}

DEFAULT_CONTROL = {
    "model": "TCN-VAE + 改进 NSGA-II",
    "horizon": "未来 4 小时",
    "deviation": 8.4,
    "mode": "人工确认",
}


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def round_to(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def merge(defaults: dict[str, Any], values: dict[str, Any] | None) -> dict[str, Any]:
    merged = defaults.copy()
    if values:
        merged.update({key: value for key, value in values.items() if value is not None})
    return merged


def wave(index: int, phase: float, amp: float = 1) -> float:
    return sin((index + phase) / 24 * pi * 2) * amp + sin((index + phase) / 24 * pi * 6) * amp * 0.2


def season_factor(season: str) -> float:
    return {"春季": 0.94, "夏季": 1.12, "秋季": 0.98, "冬季": 1.08}.get(season, 1)


def building_factor(building: str) -> float:
    return {"办公建筑": 0.92, "酒店建筑": 1.02, "园区综合能源站": 1.12}.get(building, 1)


def simulate_scenario(scenario_values: dict[str, Any] | None) -> dict[str, Any]:
    scenario = merge(DEFAULT_SCENARIO, scenario_values)
    sf = season_factor(str(scenario["season"]))
    bf = building_factor(str(scenario["building"]))
    application = str(scenario["application"])
    season = str(scenario["season"])

    rows: list[dict[str, Any]] = []
    for idx, time in enumerate(LABELS):
        office_peak = 13 if 8 <= idx <= 19 else -5
        load = 78 * sf * bf + wave(idx, -7, 17) + office_peak
        wind = 22 + wave(idx, 5, 9) + (4 if "风" in application else 0)
        daylight = max(0, sin((idx - 6) / 13 * pi))
        solar = daylight * (43 if season == "夏季" else 33)
        price = 0.34 if idx in [0, 1, 2, 3, 4, 5, 6, 23] else 0.98 if idx in [8, 9, 10, 11, 17, 18, 19, 20] else 0.59
        rows.append(
            {
                "time": time,
                "load": round_to(load),
                "wind": round_to(wind),
                "solar": round_to(solar),
                "price": round_to(price),
                "netLoad": round_to(load - wind - solar),
            }
        )

    net_values = [row["netLoad"] for row in rows]
    capacity = (
        float(scenario["layers"])
        * float(scenario["columns"])
        * 48
        * float(scenario["blockMass"])
        * 9.8
        * 4
        * float(scenario["efficiency"])
        / 3600
    )
    peak_hour = max(rows, key=lambda row: row["netLoad"])
    valley_hour = min(rows, key=lambda row: row["netLoad"])
    stats = {
        "capacity": round_to(capacity, 1),
        "soc": float(scenario["initialSoc"]),
        "peakValley": round_to(max(net_values) - min(net_values)),
        "power": float(scenario["maxPower"]),
        "maxNet": round_to(max(net_values)),
        "minNet": round_to(min(net_values)),
        "avgNet": round_to(sum(net_values) / len(net_values)),
    }
    summary = {
        "peakHour": peak_hour,
        "valleyHour": valley_hour,
        "highPriceHours": len([row for row in rows if row["price"] >= 0.98]),
        "renewableTotal": round_to(sum(row["wind"] + row["solar"] for row in rows), 1),
    }
    return {"scenario": scenario, "series": rows, "stats": stats, "summary": summary}


def run_planning(payload: dict[str, Any]) -> dict[str, Any]:
    scenario_result = simulate_scenario(payload.get("scenario"))
    scenario = scenario_result["scenario"]
    stats = scenario_result["stats"]
    planning = merge(DEFAULT_PLANNING, payload.get("planning"))
    series = scenario_result["series"]

    rows = [
        {
            "scale": "中长期尺度",
            "objective": "容量配置与季节边界",
            "constraint": f"容量边界 {planning['capacityBoundary']} MWh，季节备用 {planning['seasonReserve']}%",
            "recommendedStrategy": f"当前峰谷差 {stats['peakValley']} MW，建议高负荷季保留足够可用容量",
            "riskNote": "容量边界满足当前场景" if stats["capacity"] >= float(planning["capacityBoundary"]) else "设备容量低于规划边界，需复核结构参数",
        },
        {
            "scale": "短期尺度",
            "objective": "启停频次与运行效率平衡",
            "constraint": f"日启停不超过 {planning['switchLimit']} 次",
            "recommendedStrategy": f"按{scenario['season']}{scenario['building']}净负荷曲线，优先削减早晚高峰",
            "riskNote": "启停约束可支撑日内两轮削峰" if int(planning["switchLimit"]) >= 6 else "启停限制偏紧，削峰效果会下降",
        },
        {
            "scale": "日内尺度",
            "objective": "削峰填谷与收益最大化",
            "constraint": f"{planning['rollingCycle']} 分钟滚动修正",
            "recommendedStrategy": "低价时段提升重力块，高价晚峰按 SOC 余量分段释放",
            "riskNote": "实时负荷偏差过大时需人工确认控制建议",
        },
    ]

    curves = []
    for idx, row in enumerate(series):
        base = row["netLoad"]
        day_ahead = base - (8 if 8 <= idx <= 11 else 14 if 17 <= idx <= 20 else -9 if idx <= 6 else 0)
        rolling = day_ahead + sin(idx * 1.7) * 2.2
        curves.append({"time": row["time"], "base": round_to(base), "dayAhead": round_to(day_ahead), "rolling": round_to(rolling)})

    summary = {
        "selectedScale": "日内尺度",
        "rollingCycle": int(planning["rollingCycle"]),
        "switchLimit": int(planning["switchLimit"]),
        "recommendedAction": "低价充电 · 高峰放电",
    }
    return {"planning": planning, "rows": rows, "curves": curves, "summary": summary}


def build_pareto(stats: dict[str, Any], scenario: dict[str, Any], selected_id: int = 2) -> list[dict[str, Any]]:
    pv = float(stats["peakValley"])
    max_power = float(scenario["maxPower"])
    base_revenue = 6.8 + max_power * 0.12 + (0.9 if scenario["season"] == "夏季" else 0.45)
    candidates = [
        {"id": 1, "revenue": base_revenue + 0.15, "peakValley": pv * 0.72, "switchCount": 4, "score": 82},
        {"id": 2, "revenue": base_revenue + 0.92, "peakValley": pv * 0.58, "switchCount": 6, "score": 92},
        {"id": 3, "revenue": base_revenue + 1.36, "peakValley": pv * 0.66, "switchCount": 8, "score": 88},
        {"id": 4, "revenue": base_revenue + 0.48, "peakValley": pv * 0.52, "switchCount": 7, "score": 90},
        {"id": 5, "revenue": base_revenue + 0.70, "peakValley": pv * 0.55, "switchCount": 5, "score": 91},
    ]
    return [
        {
            **item,
            "revenue": round_to(item["revenue"]),
            "peakValley": round_to(item["peakValley"], 1),
            "selected": item["id"] == selected_id,
        }
        for item in candidates
    ]


def run_optimization(payload: dict[str, Any]) -> dict[str, Any]:
    scenario_result = simulate_scenario(payload.get("scenario"))
    scenario = scenario_result["scenario"]
    stats = scenario_result["stats"]
    series = scenario_result["series"]
    optimization = merge(DEFAULT_OPTIMIZATION, payload.get("optimization"))
    selected_id = int(payload.get("selectedSolutionId") or 2)
    solutions = build_pareto(stats, scenario, selected_id)
    selected_solution = next((item for item in solutions if item["id"] == selected_id), solutions[1])

    high_line = stats["avgNet"] + stats["peakValley"] * 0.18
    low_line = stats["avgNet"] - stats["peakValley"] * 0.16
    max_power = float(scenario["maxPower"]) * (0.72 + selected_solution["score"] / 420)
    dispatch = []
    soc_trace = []
    soc = float(optimization["soc"])
    for idx, row in enumerate(series):
        before = row["netLoad"]
        price = row["price"]
        discharge_need = max(0, before - high_line) * (0.82 if price > 0.58 else 0.35)
        charge_need = max(0, low_line - before) * (0.78 if price < 0.6 else 0.25)
        scheduled_boost = 5.2 if 17 <= idx <= 20 else -4.8 if idx <= 6 or idx >= 22 else 0
        power = round_to(clamp(discharge_need - charge_need + scheduled_boost, -max_power, max_power))
        soc = clamp(soc - power * 0.31, 12, 88)
        after = round_to(before - power * 0.72)
        action = "放电" if power > 1 else "充电" if power < -1 else "待机"
        revenue = round_to(power * price * 0.1 if power > 0 else -abs(power) * price * 0.05)
        dispatch.append(
            {
                "time": row["time"],
                "action": action,
                "power": power,
                "soc": round_to(soc, 1),
                "netLoadBefore": before,
                "netLoadAfter": after,
                "price": price,
                "revenue": revenue,
            }
        )
        soc_trace.append(soc)

    before_values = [row["netLoadBefore"] for row in dispatch]
    after_values = [row["netLoadAfter"] for row in dispatch]
    switches = sum(1 for idx in range(1, len(dispatch)) if dispatch[idx]["action"] != dispatch[idx - 1]["action"])
    optimized_stats = {
        "beforePeakValley": round_to(max(before_values) - min(before_values), 1),
        "afterPeakValley": round_to(max(after_values) - min(after_values), 1),
        "revenue": round_to(sum(row["revenue"] for row in dispatch)),
        "switches": switches,
    }
    return {
        "optimization": optimization,
        "solutions": solutions,
        "selectedSolution": selected_solution,
        "dispatchRows": dispatch,
        "optimizedStats": optimized_stats,
    }


def run_control(payload: dict[str, Any]) -> dict[str, Any]:
    scenario_result = simulate_scenario(payload.get("scenario"))
    optimization_result = run_optimization(payload)
    control = merge(DEFAULT_CONTROL, payload.get("control"))
    series = scenario_result["series"]
    dispatch_rows = optimization_result["dispatchRows"]

    rows = []
    for idx, time in enumerate(QUARTER_LABELS):
        source_index = (8 + idx // 4) % 24
        source = series[source_index]
        dispatch = dispatch_rows[source_index]
        predicted_load = source["load"] + sin(idx / 2) * 4 + float(control["deviation"]) * 0.22
        predicted_wind = source["wind"] + cos(idx / 3) * 2
        predicted_solar = source["solar"] * (0.92 + sin(idx / 4) * 0.05)
        net = predicted_load - predicted_wind - predicted_solar + (dispatch["netLoadAfter"] - source["netLoad"]) * 0.18
        uncertainty = 3.6 + abs(float(control["deviation"])) * 0.16 + idx * 0.08
        suggested_action = "放电削峰" if net > 62 else "充电消纳" if net < 36 else "保持待机"
        command_power = min(25.92, (net - 55) * 0.7) if suggested_action == "放电削峰" else -min(18, (42 - net) * 0.65) if suggested_action == "充电消纳" else 0
        confidence = 92 - abs(idx - 5) * 1.8 - abs(float(control["deviation"])) * 0.4
        rows.append(
            {
                "time": time,
                "predictedLoad": round_to(predicted_load),
                "loadLower": round_to(predicted_load - uncertainty),
                "loadUpper": round_to(predicted_load + uncertainty),
                "predictedWind": round_to(predicted_wind),
                "predictedSolar": round_to(predicted_solar),
                "predictedNetLoad": round_to(net),
                "suggestedAction": suggested_action,
                "commandPower": round_to(command_power),
                "duration": 15,
                "confidence": round_to(confidence, 1),
            }
        )

    distribution = []
    for scene_idx in range(9):
        scene_values = []
        phase = scene_idx * 0.72
        bias = (scene_idx - 4) * 1.45
        for idx, row in enumerate(rows):
            spread = sin(idx * 0.85 + phase) * (2.2 + scene_idx * 0.18) + cos(idx * 0.33 + phase) * 1.5
            scene_values.append(
                {
                    "time": row["time"],
                    "netLoad": round_to(row["predictedNetLoad"] + bias + spread),
                }
            )
        distribution.append({"name": f"S{scene_idx + 1}", "values": scene_values})
    next_command = next((row for row in rows if row["suggestedAction"] != "保持待机"), rows[0])
    return {"control": control, "rows": rows, "nextCommand": next_command, "scenarioDistribution": distribution}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "algorithmVersion": APP_VERSION, "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    return {
        "demoAccount": {"account": "siat-admin", "password": "demo123456"},
        "options": {
            "applications": ["风光峰谷蓄调", "风电消纳", "光伏平滑", "园区削峰填谷"],
            "seasons": ["春季", "夏季", "秋季", "冬季"],
            "buildings": ["办公建筑", "酒店建筑", "园区综合能源站"],
        },
        "forms": {
            "scenario": DEFAULT_SCENARIO,
            "planning": DEFAULT_PLANNING,
            "optimization": DEFAULT_OPTIMIZATION,
            "control": DEFAULT_CONTROL,
        },
        "results": {},
    }


@app.post("/api/scenario/simulate")
def scenario_simulate(payload: dict[str, Any]) -> dict[str, Any]:
    return simulate_scenario(payload.get("scenario", payload))


@app.post("/api/planning/run")
def planning_run(payload: dict[str, Any]) -> dict[str, Any]:
    return run_planning(payload)


@app.post("/api/optimization/run")
def optimization_run(payload: dict[str, Any]) -> dict[str, Any]:
    return run_optimization(payload)


@app.post("/api/control/preview")
def control_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return run_control(payload)
