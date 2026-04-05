"""
スコアリングエンジン
各艇にスコアを付けて予想順位・的中確率を計算する
"""

DEFAULT_WEIGHTS = {
    "course":   30,
    "st":       25,
    "motor":    20,
    "local":    15,
    "national": 10,
}

COURSE_COEF = {1: 1.00, 2: 0.75, 3: 0.55, 4: 0.40, 5: 0.25, 6: 0.15}


def score(boats: list[dict], weights: dict | None = None) -> list[dict]:
    """スコア計算してランク・確率を付けて返す"""
    w = weights or DEFAULT_WEIGHTS

    for b in boats:
        c  = b.get("course", b["boat_no"])
        st = b.get("st_avg", 0.18)
        m  = b.get("motor_rate", 0.0)
        lw = b.get("local_win", 0.0)
        nw = b.get("national_win", 0.0)

        s_course   = w["course"]   * COURSE_COEF.get(c, 0.15)
        s_st       = w["st"]       * max(0, (0.20 - st) / 0.10)
        s_motor    = w["motor"]    * (m / 50.0)
        s_local    = w["local"]    * (lw / 0.50)
        s_national = w["national"] * (nw / 0.50)
        total = s_course + s_st + s_motor + s_local + s_national

        b.update(
            s_course=round(s_course, 1),
            s_st=round(s_st, 1),
            s_motor=round(s_motor, 1),
            s_local=round(s_local, 1),
            s_national=round(s_national, 1),
            score=round(total, 1),
        )

    # 確率
    total_score = sum(b["score"] for b in boats) or 1
    for b in boats:
        b["prob"] = round(b["score"] / total_score * 100, 1)

    # ランク
    for rank, b in enumerate(sorted(boats, key=lambda x: x["score"], reverse=True), 1):
        b["rank"] = rank

    return sorted(boats, key=lambda x: x["boat_no"])


def top3(boats: list[dict]) -> tuple:
    """(本命, 対抗, 穴) の艇dictを返す"""
    ranked = sorted(boats, key=lambda x: x.get("rank", 9))
    return (
        ranked[0] if len(ranked) > 0 else {},
        ranked[1] if len(ranked) > 1 else {},
        ranked[2] if len(ranked) > 2 else {},
    )


def score_gap(boats: list[dict]) -> float:
    """本命と対抗のスコア差（大きいほど自信度高）"""
    ranked = sorted(boats, key=lambda x: x.get("score", 0), reverse=True)
    if len(ranked) >= 2:
        return round(ranked[0]["score"] - ranked[1]["score"], 1)
    return 0.0


def judge_hit(prediction: dict, result: dict) -> dict:
    """
    prediction: {honmei_no, taiko_no, ana_no}
    result:     {rank: {1: 艇番, 2: 艇番, 3: 艇番}}
    戻り値: {tansho, rentan, santan}  ○ or ✕
    """
    r = result.get("rank", {})
    h = prediction.get("honmei_no", 0)
    t = prediction.get("taiko_no", 0)
    a = prediction.get("ana_no", 0)

    tansho = "○" if r.get(1) == h else "✕"
    rentan = "○" if (r.get(1) == h and r.get(2) == t) else "✕"
    santan = "○" if (r.get(1) == h and r.get(2) == t and r.get(3) == a) else "✕"

    return dict(tansho=tansho, rentan=rentan, santan=santan)
