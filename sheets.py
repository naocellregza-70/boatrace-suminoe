"""
Google Sheets 連携
予想・結果データを読み書きする
"""
import json
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SH_PRED   = "予想記録"
SH_RESULT = "結果記録"

PRED_HEADERS = [
    "日付", "レース", "本命艇番", "本命選手", "本命確率",
    "対抗艇番", "対抗選手", "対抗確率",
    "穴艇番", "穴選手", "穴確率",
    "スコア差",
    "コース重み", "ST重み", "モーター重み", "住之江重み", "全国重み",
    "記録日時",
]

RESULT_HEADERS = [
    "日付", "レース",
    "1着艇番", "2着艇番", "3着艇番",
    "単勝的中", "2連単的中", "3連単的中",
    "記録日時",
]


def _client(creds_dict: dict) -> gspread.Client:
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _ensure_sheet(spreadsheet, name: str, headers: list[str]):
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=1000, cols=len(headers))
        ws.append_row(headers)
    return ws


def get_spreadsheet(creds_dict: dict, sheet_id: str):
    gc = _client(creds_dict)
    return gc.open_by_key(sheet_id)


def save_prediction(sheet_id: str, creds_dict: dict,
                    date_str: str, race_no: int,
                    boats_scored: list[dict], weights: dict):
    from scorer import top3, score_gap as calc_gap

    sp = get_spreadsheet(creds_dict, sheet_id)
    ws = _ensure_sheet(sp, SH_PRED, PRED_HEADERS)

    b1, b2, b3 = top3(boats_scored)
    gap = calc_gap(boats_scored)
    now = datetime.now().strftime("%Y/%m/%d %H:%M")

    row = [
        f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}",
        race_no,
        b1.get("boat_no", ""), b1.get("name", ""), f"{b1.get('prob', 0):.1f}%",
        b2.get("boat_no", ""), b2.get("name", ""), f"{b2.get('prob', 0):.1f}%",
        b3.get("boat_no", ""), b3.get("name", ""), f"{b3.get('prob', 0):.1f}%",
        gap,
        weights.get("course", 30), weights.get("st", 25),
        weights.get("motor", 20),  weights.get("local", 15),
        weights.get("national", 10),
        now,
    ]
    ws.append_row(row)


def save_result(sheet_id: str, creds_dict: dict,
                date_str: str, race_no: int,
                result: dict, hit: dict):
    sp = get_spreadsheet(creds_dict, sheet_id)
    ws = _ensure_sheet(sp, SH_RESULT, RESULT_HEADERS)

    r = result.get("rank", {})
    now = datetime.now().strftime("%Y/%m/%d %H:%M")

    row = [
        f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}",
        race_no,
        r.get(1, ""), r.get(2, ""), r.get(3, ""),
        hit.get("tansho", ""), hit.get("rentan", ""), hit.get("santan", ""),
        now,
    ]
    ws.append_row(row)


def load_predictions(sheet_id: str, creds_dict: dict) -> pd.DataFrame:
    sp = get_spreadsheet(creds_dict, sheet_id)
    try:
        ws = sp.worksheet(SH_PRED)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def load_results(sheet_id: str, creds_dict: dict) -> pd.DataFrame:
    sp = get_spreadsheet(creds_dict, sheet_id)
    try:
        ws = sp.worksheet(SH_RESULT)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def load_merged(sheet_id: str, creds_dict: dict) -> pd.DataFrame:
    pred = load_predictions(sheet_id, creds_dict)
    res  = load_results(sheet_id, creds_dict)
    if pred.empty or res.empty:
        return pred
    merged = pred.merge(res, on=["日付", "レース"], how="left")
    return merged
