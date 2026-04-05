"""
ボートレース住之江 完全自動予想システム
Streamlit Cloud アプリ
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
import json
import time

import scraper
import scorer
import sheets

st.set_page_config(
    page_title="🚤 ボートレース住之江 予想",
    page_icon="🚤",
    layout="wide",
    initial_sidebar_state="expanded",
)

@st.cache_resource
def get_config():
    try:
        creds = dict(st.secrets["google_service_account"])
        sheet_id = st.secrets["sheet_id"]
        return creds, sheet_id, True
    except Exception:
        return None, None, False

CREDS, SHEET_ID, HAS_SHEETS = get_config()

if "weights" not in st.session_state:
    st.session_state.weights = dict(course=30, st=25, motor=20, local=15, national=10)
if "predictions" not in st.session_state:
    st.session_state.predictions = {}

with st.sidebar:
    st.title("⚙️ 設定")
    st.subheader("📅 日付")
    sel_date = st.date_input("対象日", value=date.today())
    date_str  = sel_date.strftime("%Y%m%d")
    st.subheader("🔢 重み設定（合計=100）")
    w = st.session_state.weights
    w_course   = st.slider("コース有利",    0, 50, w["course"],   step=5)
    w_st       = st.slider("ST速度",        0, 50, w["st"],       step=5)
    w_motor    = st.slider("モーター2連率",  0, 50, w["motor"],    step=5)
    w_local    = st.slider("住之江勝率",     0, 30, w["local"],    step=5)
    w_national = st.slider("全国勝率",       0, 30, w["national"], step=5)
    total_w = w_course + w_st + w_motor + w_local + w_national
    if total_w != 100:
        st.warning(f"⚠️ 合計: {total_w}（100にしてください）")
    else:
        st.success(f"✅ 合計: {total_w}")
        st.session_state.weights = dict(course=w_course, st=w_st, motor=w_motor, local=w_local, national=w_national)
    st.divider()
    if HAS_SHEETS:
        st.success("✅ Google Sheets 接続済み")
    else:
        st.warning("⚠️ Google Sheets 未設定")
        st.caption("Streamlit Secrets に設定してください")

tab1, tab2, tab3 = st.tabs(["🔮 今日の予想", "🏁 結果を記録", "📈 精度分析"])

with tab1:
    st.header(f"🚤 ボートレース住之江　{sel_date.strftime('%Y年%m月%d日')} 予想")
    col_btn1, col_btn2 = st.columns([2, 2])
    with col_btn1:
        race_all = st.button("⚡ 全レース予想を実行", type="primary", use_container_width=True)
    with col_btn2:
        race_no_single = st.number_input("レース番号指定", min_value=1, max_value=12, value=6)
        race_single = st.button(f"🎯 {race_no_single}Rのみ予想", use_container_width=True)

    if race_all:
        progress = st.progress(0, text="データ取得中...")
        max_race = scraper.get_today_race_count(date_str)
        results_summary = []
        for i, rno in enumerate(range(1, max_race + 1)):
            progress.progress((i) / max_race, text=f"第{rno}R データ取得中...")
            boats = scraper.fetch_racelist(date_str, rno)
            if not boats:
                continue
            boats = scraper.fetch_beforeinfo(date_str, rno, boats)
            boats = scorer.score(boats, st.session_state.weights)
            st.session_state.predictions[(date_str, rno)] = boats
            b1, b2, b3 = scorer.top3(boats)
            gap = scorer.score_gap(boats)
            if HAS_SHEETS:
                try:
                    sheets.save_prediction(SHEET_ID, CREDS, date_str, rno, boats, st.session_state.weights)
                except Exception as e:
                    st.warning(f"Sheets保存エラー (R{rno}): {e}")
            results_summary.append({
                "R": rno,
                "本命": f"{b1.get('boat_no','')}号 {b1.get('name','')}",
                "確率": f"{b1.get('prob', 0):.1f}%",
                "対抗": f"{b2.get('boat_no','')}号 {b2.get('name','')}",
                "穴": f"{b3.get('boat_no','')}号 {b3.get('name','')}",
                "スコア差": gap,
                "自信": "🔥高" if gap >= 10 else ("📊中" if gap >= 5 else "⚠️低"),
            })
            time.sleep(0.5)
        progress.empty()
        if results_summary:
            st.success(f"✅ {len(results_summary)}レースの予想が完了しました！")
            if HAS_SHEETS:
                st.info(f"📊 Google Sheetsに保存しました")
            df_sum = pd.DataFrame(results_summary)
            st.dataframe(df_sum, use_container_width=True, hide_index=True)
        else:
            st.error("データを取得できませんでした。開催日か確認してください。")

    if race_single:
        with st.spinner(f"第{race_no_single}R データ取得中..."):
            boats = scraper.fetch_racelist(date_str, race_no_single)
        if not boats:
            st.error("データを取得できませんでした")
        else:
            with st.spinner("直前情報を取得中..."):
                boats = scraper.fetch_beforeinfo(date_str, race_no_single, boats)
            boats = scorer.score(boats, st.session_state.weights)
            st.session_state.predictions[(date_str, race_no_single)] = boats
            if HAS_SHEETS:
                try:
                    sheets.save_prediction(SHEET_ID, CREDS, date_str, race_no_single, boats, st.session_state.weights)
                    st.success("✅ Google Sheets に保存しました")
                except Exception as e:
                    st.warning(f"Sheets保存エラー: {e}")

    pred_keys = [k for k in st.session_state.predictions if k[0] == date_str]
    if pred_keys:
        st.divider()
        sel_race = st.selectbox("詳細を見るレース", sorted([k[1] for k in pred_keys]), format_func=lambda x: f"第{x}R")
        boats = st.session_state.predictions.get((date_str, sel_race), [])
        if boats:
            b1, b2, b3 = scorer.top3(boats)
            gap = scorer.score_gap(boats)
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🥇 本命", f"{b1.get('boat_no','')}号 {b1.get('name','')}", f"{b1.get('prob',0):.1f}%")
            with col2:
                st.metric("🥈 対抗", f"{b2.get('boat_no','')}号 {b2.get('name','')}", f"{b2.get('prob',0):.1f}%")
            with col3:
                st.metric("🥉 穴", f"{b3.get('boat_no','')}号 {b3.get('name','')}", f"{b3.get('prob',0):.1f}%")
            with col4:
                conf = "🔥 高" if gap >= 10 else ("📊 中" if gap >= 5 else "⚠️ 低")
                st.metric("自信度", conf, f"スコア差 {gap}")
            st.info(f"💰 推奨買い目　単勝: **{b1.get('boat_no','')}号**　2連単: **{b1.get('boat_no','')}-{b2.get('boat_no','')}**　3連単: **{b1.get('boat_no','')}-{b2.get('boat_no','')}-{b3.get('boat_no','')}**")
            df_boats = pd.DataFrame([{"艇番": f"{b['boat_no']}号", "選手名": b["name"], "級別": b.get("grade",""), "コース": b.get("course",b["boat_no"]), "ST": b.get("st_avg",0.18), "モーター%": b.get("motor_rate",0), "住之江勝率": b.get("local_win",0), "全国勝率": b.get("national_win",0), "合計スコア": b["score"], "確率": f"{b['prob']:.1f}%", "予想": ["🥇","🥈","🥉","4番","5番","6番"][b.get("rank",6)-1]} for b in boats])
            st.dataframe(df_boats.sort_values("合計スコア", ascending=False), use_container_width=True, hide_index=True)
            fig = go.Figure()
            colors = ["#FF0000","#333333","#CCCCCC","#3355FF","#FFCC00","#33AA33"]
            for b in sorted(boats, key=lambda x: x["score"], reverse=True):
                fig.add_trace(go.Bar(name=f"{b['boat_no']}号 {b['name']}", x=["コース","ST","モーター","住之江","全国"], y=[b["s_course"],b["s_st"],b["s_motor"],b["s_local"],b["s_national"]], marker_color=colors[b["boat_no"]-1]))
            fig.update_layout(barmode="group", title=f"第{sel_race}R スコア内訳", height=350, margin=dict(t=40,b=20))
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.header("🏁 レース結果を記録")
    col_r1, col_r2 = st.columns([2, 2])
    with col_r1:
        result_all = st.button("⚡ 本日の全結果を自動取得", type="primary", use_container_width=True)
    with col_r2:
        result_rno = st.number_input("結果取得レース番号", min_value=1, max_value=12, value=6, key="result_rno")
        result_single = st.button(f"🎯 {result_rno}Rの結果を取得", use_container_width=True)

    if result_all:
        prog = st.progress(0)
        max_r = scraper.get_today_race_count(date_str)
        rows = []
        for i, rno in enumerate(range(1, max_r + 1)):
            prog.progress(i / max_r, text=f"第{rno}R 結果取得中...")
            result = scraper.fetch_result(date_str, rno)
            if not result:
                continue
            boats = st.session_state.predictions.get((date_str, rno))
            if boats:
                b1, b2, b3 = scorer.top3(boats)
                pred_data = dict(honmei_no=b1.get("boat_no",0), taiko_no=b2.get("boat_no",0), ana_no=b3.get("boat_no",0))
                hit = scorer.judge_hit(pred_data, result)
                if HAS_SHEETS:
                    try:
                        sheets.save_result(SHEET_ID, CREDS, date_str, rno, result, hit)
                    except Exception:
                        pass
            else:
                hit = {}
            r = result["rank"]
            rows.append({"R": rno, "1着": f"{r.get(1,'')}号", "2着": f"{r.get(2,'')}号", "3着": f"{r.get(3,'')}号", "単勝": hit.get("tansho","-"), "2連単": hit.get("rentan","-"), "3連単": hit.get("santan","-")})
            time.sleep(0.5)
        prog.empty()
        if rows:
            st.success(f"✅ {len(rows)}レースの結果を記録しました")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if result_single:
        with st.spinner(f"第{result_rno}R 結果取得中..."):
            result = scraper.fetch_result(date_str, result_rno)
        if result and result.get("rank"):
            r = result["rank"]
            st.success(f"結果: " + "　".join(f"{k}着 {r[k]}号" for k in sorted(r.keys())))
            boats = st.session_state.predictions.get((date_str, result_rno))
            if boats:
                b1, b2, b3 = scorer.top3(boats)
                hit = scorer.judge_hit(dict(honmei_no=b1.get("boat_no",0), taiko_no=b2.get("boat_no",0), ana_no=b3.get("boat_no",0)), result)
                cols = st.columns(3)
                cols[0].metric("単勝", hit["tansho"])
                cols[1].metric("2連単", hit["rentan"])
                cols[2].metric("3連単", hit["santan"])
                if HAS_SHEETS:
                    sheets.save_result(SHEET_ID, CREDS, date_str, result_rno, result, hit)
                    st.success("✅ Google Sheets に保存しました")
            else:
                st.warning("予想データがありません（先に予想を実行してください）")
        else:
            st.error("結果を取得できませんでした")

    with st.expander("✏️ 結果を手動入力する"):
        st.caption("自動取得できなかった場合に使ってください")
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            m_rno = st.number_input("レース番号", 1, 12, 6, key="m_rno")
        with mc2:
            m1st = st.selectbox("1着", range(1, 7), key="m1st")
        with mc3:
            m2nd = st.selectbox("2着", range(1, 7), index=1, key="m2nd")
        m3rd = st.selectbox("3着", range(1, 7), index=2, key="m3rd")
        if st.button("手動で記録する"):
            manual_result = {"rank": {1: m1st, 2: m2nd, 3: m3rd}}
            boats = st.session_state.predictions.get((date_str, m_rno))
            if boats:
                b1, b2, b3 = scorer.top3(boats)
                hit = scorer.judge_hit(dict(honmei_no=b1.get("boat_no",0), taiko_no=b2.get("boat_no",0), ana_no=b3.get("boat_no",0)), manual_result)
                if HAS_SHEETS:
                    sheets.save_result(SHEET_ID, CREDS, date_str, m_rno, manual_result, hit)
                st.success(f"記録完了: 単勝{hit['tansho']} 2連単{hit['rentan']} 3連単{hit['santan']}")
            else:
                st.warning("予想データがありません")

with tab3:
    st.header("📈 予想精度分析")
    if not HAS_SHEETS:
        st.warning("Google Sheets が設定されていません。設定後にご利用ください。")
        st.stop()
    refresh = st.button("🔄 データを最新に更新")
    if refresh or "analysis_df" not in st.session_state:
        with st.spinner("データ読み込み中..."):
            df_merged = sheets.load_merged(SHEET_ID, CREDS)
            st.session_state.analysis_df = df_merged
    else:
        df_merged = st.session_state.get("analysis_df", pd.DataFrame())
    if df_merged.empty:
        st.info("まだデータがありません。予想・結果を記録すると分析できます。")
        st.stop()
    n = len(df_merged)
    has_result = df_merged.dropna(subset=["単勝的中"]) if "単勝的中" in df_merged.columns else pd.DataFrame()
    n_result = len(has_result)
    st.subheader("📊 的中率サマリー")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総レース数", n)
    c2.metric("結果記録済み", n_result)
    if n_result > 0 and "単勝的中" in has_result.columns:
        t_ok = (has_result["単勝的中"] == "○").sum()
        r_ok = (has_result["2連単的中"] == "○").sum() if "2連単的中" in has_result.columns else 0
        s_ok = (has_result["3連単的中"] == "○").sum() if "3連単的中" in has_result.columns else 0
        c3.metric("単勝的中率", f"{t_ok/n_result*100:.1f}%", f"{t_ok}/{n_result}")
        c4.metric("2連単的中率", f"{r_ok/n_result*100:.1f}%", f"{r_ok}/{n_result}")
        st.subheader("📉 的中率の推移")
        has_result = has_result.copy()
        has_result["単勝_bin"] = (has_result["単勝的中"] == "○").astype(int)
        has_result["idx"] = range(1, len(has_result) + 1)
        has_result["累積単勝率"] = has_result["単勝_bin"].expanding().mean() * 100
        fig2 = px.line(has_result, x="idx", y="累積単勝率", title="単勝的中率の推移（累積）", labels={"idx":"レース数","累積単勝率":"的中率 (%)"}, markers=True)
        fig2.add_hline(y=50, line_dash="dash", line_color="red", annotation_text="目標50%")
        fig2.update_layout(height=300)
        st.plotly_chart(fig2, use_container_width=True)
        if "スコア差" in has_result.columns:
            st.subheader("🎯 スコア差（自信度）別 的中率")
            has_result["自信度"] = pd.cut(pd.to_numeric(has_result["スコア差"], errors="coerce"), bins=[-1,5,10,100], labels=["⚠️低 (0〜5)","📊中 (5〜10)","🔥高 (10〜)"])
            conf_group = has_result.groupby("自信度")["単勝_bin"].agg(["mean","count"])
            conf_group.columns = ["的中率","件数"]
            conf_group["的中率"] = (conf_group["的中率"] * 100).round(1)
            st.dataframe(conf_group, use_container_width=True)
        st.subheader("💡 重み改善提案")
        trate = t_ok / n_result
        if n_result < 20:
            st.info(f"あと {20 - n_result} 件記録すると詳細な提案が出ます（現在 {n_result} 件）")
        elif trate >= 0.55:
            st.success(f"✅ 単勝的中率 {trate*100:.0f}% は良好です！現在の重みを維持してください。")
        elif trate < 0.40:
            st.warning(f"単勝的中率が {trate*100:.0f}% と低めです。以下の調整を試してください：")
            curr_w = st.session_state.weights
            if curr_w["course"] < 35:
                st.write(f"→ コース重みを {curr_w['course']} → {curr_w['course']+5} に増やす")
            if curr_w["st"] < 30:
                st.write(f"→ ST重みを {curr_w['st']} → {curr_w['st']+5} に増やす")
            st.write("→ サイドバーのスライダーで調整できます")
        else:
            st.info(f"単勝的中率 {trate*100:.0f}%。50件以上記録すると傾向が見えてきます。")
    with st.expander("📋 全データを見る"):
        st.dataframe(df_merged, use_container_width=True, hide_index=True)
