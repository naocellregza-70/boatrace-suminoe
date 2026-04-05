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

# 全角数字 → 半角
_FW = {"１":1,"２":2,"３":3,"４":4,"５":5,"６":6}


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
        return float(re.search(r"[\d.]+", text.replace("F","").replace("L","")).group())
    except Exception:
        return default


def _to_boat_no(text: str):
    t = text.strip()
    if t in _FW:
        return _FW[t]
    if t.isdigit() and 1 <= int(t) <= 6:
        return int(t)
    return None


def fetch_racelist(date_str: str, race_no: int) -> list[dict]:
    """出走表を取得。戻り値: 艇ごとのdict リスト（最大6艇）"""
    url = f"{BASE}/racelist?rno={race_no}&jcd={VENUE}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return []

    boats = []
    for tbody in soup.find_all("tbody"):
        if "is-fs12" not in (tbody.get("class") or []):
            continue
        rows = tbody.find_all("tr")
        if not rows:
            continue
        tds = rows[0].find_all("td")
        if len(tds) < 6:
            continue

        boat_no = _to_boat_no(tds[0].get_text(strip=True))
        if not boat_no:
            continue

        # td[2]: "4044 / A1 湯川 浩司 大阪/大阪 46歳/51.5kg"
        td2 = tds[2].get_text(" ", strip=True) if len(tds) > 2 else ""
        grade = next((g for g in ["A1","A2","B1","B2"] if g in td2), "")
        name = ""
        m = re.search(r'[A-Z]\d\s+(.+?)\s+\S+/\S+\s+\d+歳', td2)
        if m:
            name = m.group(1).strip()

        # td[3]: "F0 L0 0.13" → 平均ST
        td3 = tds[3].get_text(" ", strip=True) if len(tds) > 3 else ""
        nums3 = re.findall(r'[\d.]+', td3.replace("F","").replace("L",""))
        st_avg = float(nums3[-1]) if nums3 else 0.18

        # td[4]: "7.19 50.44 69.03" → 全国勝率
        nums4 = re.findall(r'\d+\.\d+', tds[4].get_text() if len(tds) > 4 else "")
        national_win = float(nums4[0]) if nums4 else 0.0

        # td[5]: "6.61 47.71 59.63" → 当地勝率
        nums5 = re.findall(r'\d+\.\d+', tds[5].get_text() if len(tds) > 5 else "")
        local_win = float(nums5[0]) if nums5 else 0.0

        # td[6]: "51 50.00 50.00" → モーター2連率
        nums6 = re.findall(r'\d+\.\d+', tds[6].get_text() if len(tds) > 6 else "")
        motor_rate = float(nums6[0]) if nums6 else 0.0

        boats.append(dict(
            boat_no=boat_no, name=name or f"選手{boat_no}", grade=grade,
            course=boat_no, national_win=national_win, national_rate=0.0,
            local_win=local_win, local_rate=0.0, motor_rate=motor_rate,
            st_avg=st_avg, ex_time=0.0, ex_st=st_avg,
        ))

    # フォールバック: 旧構造
    if not boats:
        for n in range(1, 7):
            tbody = soup.find("tbody", class_=f"is-boatColor{n}")
            if not tbody:
                continue
            rows = tbody.find_all("tr")
            if not rows:
                continue
            tds = rows[0].find_all("td")
            data = _parse_tds_legacy(n, tds)
            if data:
                boats.append(data)

    return sorted(boats, key=lambda x: x["boat_no"])


def _parse_tds_legacy(boat_no: int, tds) -> dict | None:
    try:
        name = ""
        for td in tds:
            a = td.find("a")
            if a:
                t = a.get_text(strip=True)
                if len(t) >= 3 and not t.isdigit():
                    name = t
                    break
        nums = []
        for td in tds:
            t = td.get_text(strip=True)
            if re.match(r"^\d+\.\d{2}$", t):
                nums.append(float(t))
        st_avg = nums[10] if len(nums) > 10 else 0.18
        if st_avg > 1.0:
            st_avg = 0.18
        grade = next((td.get_text(strip=True) for td in tds if td.get_text(strip=True) in ["A1","A2","B1","B2"]), "")
        return dict(
            boat_no=boat_no, name=name or f"選手{boat_no}", grade=grade,
            course=boat_no, national_win=nums[0] if nums else 0.0, national_rate=0.0,
            local_win=nums[3] if len(nums)>3 else 0.0, local_rate=0.0,
            motor_rate=nums[6] if len(nums)>6 else 0.0,
            st_avg=st_avg, ex_time=0.0, ex_st=st_avg,
        )
    except Exception:
        return None


def fetch_beforeinfo(date_str: str, race_no: int, boats: list[dict]) -> list[dict]:
    """直前情報（展示タイム・展示ST）でboatsを更新"""
    url = f"{BASE}/beforeinfo?rno={race_no}&jcd={VENUE}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return boats

    ex_times = {}
    for tbody in soup.find_all("tbody"):
        if "is-fs12" not in (tbody.get("class") or []):
            continue
        tds = tbody.find_all("td")
        if len(tds) < 5:
            continue
        boat_no = _to_boat_no(tds[0].get_text(strip=True))
        if not boat_no:
            continue
        ex_t = _safe_float(tds[4].get_text(strip=True))
        if 5.0 <= ex_t <= 9.0:
            ex_times[boat_no] = ex_t

    ex_sts = {}
    p10 = soup.find("tbody", class_="is-p10-0")
    if p10:
        for td in p10.find_all("td"):
            txt = td.get_text(strip=True)
            m = re.match(r"([1-6])\s+F?([\d.]+)", txt)
            if m:
                course = int(m.group(1))
                st_val = _safe_float(m.group(2))
                if 0.0 <= st_val <= 0.99:
                    ex_sts[course] = st_val

    for b in boats:
        bn = b["boat_no"]
        if bn in ex_times:
            b["ex_time"] = ex_times[bn]
        course = b.get("course", bn)
        if course in ex_sts:
            b["ex_st"] = ex_sts[course]
            b["st_avg"] = ex_sts[course]

    return boats


def fetch_result(date_str: str, race_no: int) -> dict | None:
    """レース結果を取得。戻り値: {"rank": {1: 艇番, 2: 艇番, 3: 艇番}}"""
    url = f"{BASE}/raceresult?rno={race_no}&jcd={VENUE}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return None
    rank_map = {}
    for tbody in soup.find_all("tbody"):
        if "is-fs12" not in (tbody.get("class") or []):
            continue
        tds = tbody.find_all("td")
        if not tds:
            continue
        rank_text = tds[0].get_text(strip=True)
        if rank_text in ["1", "2", "3"]:
            for td in tds[1:]:
                t = td.get_text(strip=True)
                if t.isdigit() and 1 <= int(t) <= 6:
                    rank_map[int(rank_text)] = int(t)
                    break
    if not rank_map:
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
                rt = tds[0].get_text(strip=True)
                if rt in ["1", "2", "3"]:
                    for td in tds[1:]:
                        t = td.get_text(strip=True)
                        if t.isdigit() and 1 <= int(t) <= 6:
                            rank_map[int(rt)] = int(t)
                            break
    return {"rank": rank_map} if rank_map else None


def get_today_race_count(date_str: str) -> int:
    url = f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={VENUE}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return 12
    links = soup.find_all("a", href=re.compile(r"rno=\d+"))
    nos = {int(re.search(r"rno=(\d+)", lnk["href"]).group(1)) for lnk in links if re.search(r"rno=(\d+)", lnk["href"])}
    return max(nos) if nos else 12
