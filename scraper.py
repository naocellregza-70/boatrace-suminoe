"""
boatrace.jp スクレイパー
出走表・直前情報・レース結果を取得する
"""
import requests
from bs4 import BeautifulSoup
import re
import time

VENUE = "12"  # 住之江
BASE  = "https://www.boatrace.jp/owpc/pc/race"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.7",
}

def _get(url: str) -> BeautifulSoup | None:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.encoding = "utf-8"
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser")
        except Exception:
            time.sleep(2)
    return None

def _safe_float(text: str, default=0.0) -> float:
    try:
        return float(re.search(r"[\d.]+", text.replace("F", "").replace("L", "")).group())
    except Exception:
        return default

def fetch_racelist(date_str: str, race_no: int) -> list[dict]:
    """出走表を取得。戻り値: 艇ごとのdict リスト（6艇）"""
    url = f"{BASE}/racelist?rno={race_no}&jcd={VENUE}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return []

    boats = []

    # --- 戦略1: tbody.is-boatColor{N} ---
    for n in range(1, 7):
        tbody = soup.find("tbody", class_=f"is-boatColor{n}")
        if not tbody:
            continue
        rows = tbody.find_all("tr")
        if not rows:
            continue
        tds = rows[0].find_all("td")
        data = _parse_tds(n, tds)
        if data:
            boats.append(data)

    # --- 戦略2: 全テーブルを行番号で走査 ---
    if not boats:
        for tbl in soup.find_all("table"):
            for row in tbl.find_all("tr"):
                tds = row.find_all("td")
                if not tds:
                    continue
                first = tds[0].get_text(strip=True)
                if first in [str(i) for i in range(1, 7)] and len(tds) >= 8:
                    n = int(first)
                    data = _parse_tds(n, tds)
                    if data and not any(b["boat_no"] == n for b in boats):
                        boats.append(data)

    return sorted(boats, key=lambda x: x["boat_no"])


def _parse_tds(boat_no: int, tds) -> dict | None:
    try:
        name = ""
        for td in tds:
            a = td.find("a")
            if a:
                t = a.get_text(strip=True)
                if len(t) >= 3 and not t.isdigit():
                    name = t
                    break
        if not name:
            for td in tds[1:5]:
                t = td.get_text(strip=True)
                if len(t) >= 3 and not t.isdigit() and "." not in t:
                    name = t
                    break

        nums = []
        for td in tds:
            t = td.get_text(strip=True)
            if re.match(r"^\d+\.\d{2}$", t):
                nums.append(float(t))

        national_win  = nums[0]  if len(nums) > 0  else 0.0
        national_rate = nums[1]  if len(nums) > 1  else 0.0
        local_win     = nums[3]  if len(nums) > 3  else 0.0
        local_rate    = nums[4]  if len(nums) > 4  else 0.0
        motor_rate    = nums[6]  if len(nums) > 6  else 0.0
        st_avg        = nums[10] if len(nums) > 10 else 0.18
        if st_avg > 1.0:
            st_avg = 0.18

        grade = ""
        for td in tds:
            t = td.get_text(strip=True)
            if t in ["A1", "A2", "B1", "B2"]:
                grade = t
                break

        return dict(
            boat_no=boat_no, name=name or f"選手{boat_no}",
            grade=grade, course=boat_no,
            national_win=national_win, national_rate=national_rate,
            local_win=local_win, local_rate=local_rate,
            motor_rate=motor_rate, st_avg=st_avg,
            ex_time=0.0, ex_st=st_avg,
        )
    except Exception:
        return None


def fetch_beforeinfo(date_str: str, race_no: int, boats: list[dict]) -> list[dict]:
    """直前情報（展示ST・展示タイム・進入コース）でboatsを更新"""
    url = f"{BASE}/beforeinfo?rno={race_no}&jcd={VENUE}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return boats

    ex = {}
    for n in range(1, 7):
        tbody = soup.find("tbody", class_=f"is-boatColor{n}")
        if not tbody:
            continue
        tds = tbody.find_all("td")
        ex_time, ex_st, course = 0.0, 0.18, n
        for td in tds:
            t = td.get_text(strip=True)
            v = _safe_float(t)
            if 5.0 <= v <= 9.0:
                ex_time = v
            elif 0.05 <= v <= 0.30:
                ex_st = v
            elif t.isdigit() and 1 <= int(t) <= 6:
                course = int(t)
        ex[n] = dict(ex_time=ex_time, ex_st=ex_st, course=course)

    for b in boats:
        bn = b["boat_no"]
        if bn in ex:
            b["course"]  = ex[bn]["course"]
            b["ex_time"] = ex[bn]["ex_time"]
            b["ex_st"]   = ex[bn]["ex_st"]
            if ex[bn]["ex_st"] > 0:
                b["st_avg"] = ex[bn]["ex_st"]
    return boats


def fetch_result(date_str: str, race_no: int) -> dict | None:
    """レース結果を取得。戻り値: {"rank": {1: 艇番, 2: 艇番, 3: 艇番}}"""
    url = f"{BASE}/raceresult?rno={race_no}&jcd={VENUE}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return None

    rank_map = {}

    for n in range(1, 7):
        tbody = soup.find("tbody", class_=f"is-boatColor{n}")
        if not tbody:
            continue
        for td in tbody.find_all("td"):
            t = td.get_text(strip=True)
            if t in ["1", "2", "3"]:
                rank_map[int(t)] = n
                break

    if not rank_map:
        for tbl in soup.find_all("table"):
            for row in tbl.find_all("tr"):
                tds = row.find_all("td")
                if not tds:
                    continue
                rank_text = tds[0].get_text(strip=True)
                if rank_text in ["1", "2", "3"]:
                    for td in tds[1:]:
                        t = td.get_text(strip=True)
                        if t.isdigit() and 1 <= int(t) <= 6:
                            rank_map[int(rank_text)] = int(t)
                            break

    return {"rank": rank_map} if rank_map else None


def get_today_race_count(date_str: str) -> int:
    """その日の最終レース番号を推定（通常12R）"""
    url = f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={VENUE}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return 12
    links = soup.find_all("a", href=re.compile(r"rno=\d+"))
    nos = set()
    for lnk in links:
        m = re.search(r"rno=(\d+)", lnk["href"])
        if m:
            nos.add(int(m.group(1)))
    return max(nos) if nos else 12
