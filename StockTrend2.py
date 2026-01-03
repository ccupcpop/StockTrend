import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sqlite3

# ==============================
# 🔧 【可控制的參數設定】
# ==============================
# 條件開關
FLAG_VOLUME_SPIKE = False   # 爆量
FLAG_RED_THREE = True      # 紅三兵
FLAG_NET_BUY = True        # 三大法人：3天中至少2天淨買超 > 0

# 資料夾路徑
FOLDER_PATH = "stock_data"
OUTPUT_CHARTS_FOLDER = "output_charts"

# 資料庫路徑
DB_TSE_PATH = "stock_data/stock_tse_all.db"  # 上市股票資料庫
DB_OTC_PATH = "stock_data/stock_otc_all.db"  # 上櫃股票資料庫

# 爆量參數
VOL_LOOKBACK = 4           # 回看天數
VOL_MULTIPLE = 1.2         # 倍數（相對於前期最高量）
MIN_VOLUME_THRESHOLD = 5000  # 最近一天成交量最低門檻（張數）

# 紅三兵參數
PRICE_LOOKBACK = 3         # 回看天數

# ==============================
# 📊 資料庫讀取函數
# ==============================
def read_stock_from_db(stock_code):
    """從資料庫讀取指定股票的資料"""
    df = None
    
    # 先從上市資料庫查詢
    if Path(DB_TSE_PATH).exists():
        try:
            conn = sqlite3.connect(DB_TSE_PATH)
            query = f"SELECT * FROM stock_data WHERE 股票代碼 = '{stock_code}' ORDER BY 日期"
            df = pd.read_sql_query(query, conn)
            conn.close()
            if len(df) > 0:
                return df
        except:
            pass
    
    # 如果上市找不到，從上櫃資料庫查詢
    if Path(DB_OTC_PATH).exists():
        try:
            conn = sqlite3.connect(DB_OTC_PATH)
            query = f"SELECT * FROM stock_data WHERE 股票代碼 = '{stock_code}' ORDER BY 日期"
            df = pd.read_sql_query(query, conn)
            conn.close()
            if len(df) > 0:
                return df
        except:
            pass
    
    return None

def get_all_stock_codes():
    """從資料庫獲取所有股票代碼"""
    codes = set()
    
    if Path(DB_TSE_PATH).exists():
        try:
            conn = sqlite3.connect(DB_TSE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT 股票代碼 FROM stock_data")
            codes.update([str(row[0]) for row in cursor.fetchall()])
            conn.close()
        except:
            pass
    
    if Path(DB_OTC_PATH).exists():
        try:
            conn = sqlite3.connect(DB_OTC_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT 股票代碼 FROM stock_data")
            codes.update([str(row[0]) for row in cursor.fetchall()])
            conn.close()
        except:
            pass
    
    return sorted(list(codes))

# ==============================
# 📈 量價戰法分析引擎
# ==============================
def analyze_volume_price_pattern(df):
    """
    量價戰法分析引擎
    根據量價關係、K線型態、趨勢判斷給出操作建議
    
    返回: {
        'signals': [],  # 信號列表
        'action': '',   # 操作建議: '上車'/'重倉'/'減倉'/'清倉'/'觀望'
        'risk_level': '', # 風險等級: '低'/'中'/'高'
        'summary': ''   # 綜合分析
    }
    """
    if len(df) < 10:
        return {'signals': [], 'action': '觀望', 'risk_level': '中', 'summary': '資料不足'}
    
    signals = []
    action_score = 0  # 正分=看多，負分=看空，0=觀望
    risk_factors = []
    
    # 取最近資料
    recent = df.tail(10).copy()
    latest = recent.iloc[-1]
    prev_1 = recent.iloc[-2] if len(recent) >= 2 else latest
    prev_2 = recent.iloc[-3] if len(recent) >= 3 else latest
    prev_3 = recent.iloc[-4] if len(recent) >= 4 else latest
    
    # ===== 1. 高量判斷 =====
    is_high_volume = False
    high_volume_day = 0
    
    if '成交張數' in recent.columns:
        last_vol = latest['成交張數']
        prev_3_vols = recent.iloc[-4:-1]['成交張數'].values if len(recent) >= 4 else []
        
        if len(prev_3_vols) > 0 and last_vol > max(prev_3_vols):
            is_high_volume = True
            high_volume_day = 1
            signals.append("🔥 高量第1天（觀察）")
            action_score += 0  # 觀望
        
        # 檢查是否為高量第2-3天
        if len(recent) >= 5:
            for i in range(1, 3):
                day_vol = recent.iloc[-(i+1)]['成交張數']
                before_vols = recent.iloc[-(i+4):-(i+1)]['成交張數'].values
                if len(before_vols) > 0 and day_vol > max(before_vols):
                    high_volume_day = i + 1
                    break
    
    # ===== 2. 支撐壓力判斷 =====
    support_price = None
    resistance_price = None
    
    if '收盤價' in recent.columns and '開盤價' in recent.columns:
        # 找高量K棒的實體低點作為支撐
        if is_high_volume:
            support_price = min(latest['開盤價'], latest['收盤價'])
        
        # 找過往高點作為壓力
        resistance_price = recent['最高價'].max() if '最高價' in recent.columns else recent['收盤價'].max()
        
        # 判斷目前位置
        current_price = latest['收盤價']
        if support_price and current_price > support_price:
            signals.append(f"✓ 在支撐線上方 (支撐:{support_price:.2f})")
            action_score += 2
        elif support_price and current_price < support_price:
            signals.append(f"✗ 跌破支撐線 (支撐:{support_price:.2f})")
            risk_factors.append("破支撐")
            action_score -= 5
    
    # ===== 3. K線型態判斷 =====
    # 紅三兵 / 綠三兵
    if len(recent) >= 3:
        last_3_closes = recent.tail(3)['收盤價'].values
        if all(last_3_closes[i] < last_3_closes[i+1] for i in range(2)):
            if support_price and latest['收盤價'] > support_price:
                signals.append("🚀 支撐線上方紅三兵（上車）")
                action_score += 5
            else:
                signals.append("📈 紅三兵")
                action_score += 2
        elif all(last_3_closes[i] > last_3_closes[i+1] for i in range(2)):
            if resistance_price and latest['收盤價'] < resistance_price:
                signals.append("📉 壓力線下方綠三兵（減倉）")
                action_score -= 4
                risk_factors.append("綠三兵")
            else:
                signals.append("📉 綠三兵")
                action_score -= 2
    
    # 底分型 / 頂分型（簡化判斷：最近3天中間那天最低/最高）
    if len(recent) >= 3:
        last_3 = recent.tail(3)
        lows = last_3['最低價'].values if '最低價' in last_3.columns else last_3['收盤價'].values
        highs = last_3['最高價'].values if '最高價' in last_3.columns else last_3['收盤價'].values
        
        # 底分型：第2天最低
        if lows[1] < lows[0] and lows[1] < lows[2]:
            if support_price and latest['收盤價'] > support_price:
                signals.append("🎯 支撐線上方底分型（上車）")
                action_score += 4
        
        # 頂分型：第2天最高
        if highs[1] > highs[0] and highs[1] > highs[2]:
            if resistance_price and latest['收盤價'] < resistance_price:
                signals.append("⚠️ 壓力線下方頂分型（減倉）")
                action_score -= 4
                risk_factors.append("頂分型")
    
    # ===== 4. 影線判斷 =====
    if '最高價' in latest and '最低價' in latest and '開盤價' in latest:
        body_top = max(latest['開盤價'], latest['收盤價'])
        body_bottom = min(latest['開盤價'], latest['收盤價'])
        upper_shadow = latest['最高價'] - body_top
        lower_shadow = body_bottom - latest['最低價']
        body_size = body_top - body_bottom
        
        # 上影線過長（弱勢）
        if body_size > 0 and upper_shadow > body_size * 1.5:
            signals.append("⚠️ 長上影線（賣壓重）")
            action_score -= 2
            risk_factors.append("長上影線")
        
        # 下影線過長（支撐）
        if body_size > 0 and lower_shadow > body_size * 1.5:
            if support_price and latest['收盤價'] > support_price:
                signals.append("✓ 長下影線（支撐強）")
                action_score += 2
    
    # ===== 5. 高量後第2-3天判斷 =====
    if high_volume_day == 2:
        # 高量第2天
        if latest['收盤價'] > prev_1['收盤價']:
            if support_price and latest['收盤價'] > support_price:
                signals.append("🚀 高量第2天收紅站上支撐（上車）")
                action_score += 6
            else:
                signals.append("📈 高量第2天收紅（偏多）")
                action_score += 3
        else:
            signals.append("⚠️ 高量第2天收黑（弱勢）")
            action_score -= 3
            risk_factors.append("高量第2天收黑")
    
    elif high_volume_day == 3:
        # 高量第3天
        if latest['收盤價'] > prev_1['收盤價'] > prev_2['收盤價']:
            if support_price and latest['收盤價'] > support_price:
                signals.append("🚀 高量第3天三連紅（重倉）")
                action_score += 8
            else:
                signals.append("🔥 高量第3天三連紅（偏多）")
                action_score += 5
        elif latest['收盤價'] < prev_1['收盤價']:
            signals.append("⚠️ 高量第3天收黑（回檔）")
            action_score -= 2
    
    # ===== 6. 綜合判斷 =====
    # 操作建議
    if action_score >= 8:
        action = "重倉"
    elif action_score >= 4:
        action = "上車"
    elif action_score >= 0:
        action = "觀望"
    elif action_score >= -4:
        action = "減倉"
    else:
        action = "清倉"
    
    # 風險等級
    if len(risk_factors) == 0:
        risk_level = "低"
    elif len(risk_factors) <= 2:
        risk_level = "中"
    else:
        risk_level = "高"
    
    # 綜合分析
    summary_parts = []
    if is_high_volume:
        summary_parts.append(f"高量第{high_volume_day}天")
    if support_price:
        if latest['收盤價'] > support_price:
            summary_parts.append(f"站上支撐{support_price:.2f}")
        else:
            summary_parts.append(f"跌破支撐{support_price:.2f}")
    if action_score > 0:
        summary_parts.append("偏多")
    elif action_score < 0:
        summary_parts.append("偏空")
    else:
        summary_parts.append("中性")
    
    summary = "，".join(summary_parts) if summary_parts else "資料不足"
    
    return {
        'signals': signals,
        'action': action,
        'risk_level': risk_level,
        'summary': summary,
        'action_score': action_score
    }

# ==============================
# 🏢 讀取公司資訊
# ==============================
def load_company_info():
    """從資料庫讀取所有股票的公司資訊（名稱、產業別）"""
    company_info = {}
    
    # 從上市資料庫讀取
    if Path(DB_TSE_PATH).exists():
        try:
            conn = sqlite3.connect(DB_TSE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT 股票代碼, 股票名稱, 產業別 FROM stock_data")
            for row in cursor.fetchall():
                code = str(row[0])
                if code not in company_info:
                    company_info[code] = {
                        'name': row[1] if row[1] else '未知',
                        'sector': row[2] if row[2] else '未知',
                        'type': '上市'
                    }
            conn.close()
        except:
            pass
    
    # 從上櫃資料庫讀取
    if Path(DB_OTC_PATH).exists():
        try:
            conn = sqlite3.connect(DB_OTC_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT 股票代碼, 股票名稱, 產業別 FROM stock_data")
            for row in cursor.fetchall():
                code = str(row[0])
                if code not in company_info:
                    company_info[code] = {
                        'name': row[1] if row[1] else '未知',
                        'sector': row[2] if row[2] else '未知',
                        'type': '上櫃'
                    }
            conn.close()
        except:
            pass
    
    return company_info

# 在程式啟動時讀取公司資訊
company_info = load_company_info()

# ==============================
# 📊 篩選條件檢查
# ==============================
def analyze_stock(stock_code, vol_lookback=None, vol_multiple=None, min_volume_threshold=None):
    """
    分析單一股票是否符合條件
    
    返回：
    - None: 不符合條件
    - dict: 符合條件時返回相關資訊
    """
    df = read_stock_from_db(stock_code)
    if df is None or len(df) < 10:
        return None
    
    # 使用傳入的參數，若無則使用全域設定
    lookback = vol_lookback if vol_lookback is not None else VOL_LOOKBACK
    multiple = vol_multiple if vol_multiple is not None else VOL_MULTIPLE
    min_vol = min_volume_threshold if min_volume_threshold is not None else MIN_VOLUME_THRESHOLD
    
    # 資料預處理
    df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
    
    for col in ['成交張數', '收盤價', '開盤價', '最高價', '最低價']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(',', '', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df.dropna(subset=['日期'], inplace=True)
    df.sort_values('日期', inplace=True)
    
    if len(df) < max(lookback + 1, PRICE_LOOKBACK):
        return None
    
    # 取最近的資料
    recent_df = df.tail(max(lookback + 1, PRICE_LOOKBACK, 10))
    
    # 檢查條件
    passes = []
    
    # 1) 爆量條件
    volume_pass = False
    if FLAG_VOLUME_SPIKE and '成交張數' in recent_df.columns:
        last_volume = recent_df['成交張數'].iloc[-1]
        
        if pd.isna(last_volume) or last_volume < min_vol:
            volume_pass = False
        else:
            prev_volumes = recent_df['成交張數'].iloc[-(lookback+1):-1]
            prev_volumes_clean = prev_volumes.dropna()
            
            if len(prev_volumes_clean) > 0:
                max_prev = prev_volumes_clean.max()
                if last_volume > max_prev * multiple:
                    volume_pass = True
    
    if FLAG_VOLUME_SPIKE:
        if not volume_pass:
            return None
        passes.append('volume')
    
    # 2) 紅三兵條件
    red_three_pass = False
    closes_list = None
    if FLAG_RED_THREE and '收盤價' in recent_df.columns:
        closes = recent_df['收盤價'].tail(PRICE_LOOKBACK).dropna()
        if len(closes) >= PRICE_LOOKBACK:
            closes_list = closes.tolist()
            if all(closes_list[i] < closes_list[i+1] for i in range(len(closes_list)-1)):
                red_three_pass = True
    
    if FLAG_RED_THREE:
        if not red_three_pass:
            return None
        passes.append('red_three')
    
    # 3) 三大法人淨買超條件
    net_buy_pass = False
    net_summary = None
    if FLAG_NET_BUY:
        required_cols = ['外資買賣超', '投信買賣超', '自營商買賣超']
        if all(c in recent_df.columns for c in required_cols):
            last_3 = recent_df.tail(3)
            
            details = []
            for _, row in last_3.iterrows():
                f_val = row['外資買賣超']
                t_val = row['投信買賣超']
                d_val = row['自營商買賣超']
                
                f_num = pd.to_numeric(f_val, errors='coerce')
                t_num = pd.to_numeric(t_val, errors='coerce')
                d_num = pd.to_numeric(d_val, errors='coerce')
                
                if pd.isna(f_num): f_num = 0
                if pd.isna(t_num): t_num = 0
                if pd.isna(d_num): d_num = 0
                
                total = f_num + t_num + d_num
                details.append((f_num, t_num, d_num, total))
            
            positive_count = sum(1 for (_, _, _, total) in details if total > 0)
            
            if positive_count >= 2:
                net_buy_pass = True
                net_summary = {
                    'details': details,
                    'positive_days': positive_count
                }
    
    if FLAG_NET_BUY:
        if not net_buy_pass:
            return None
        passes.append('net_buy')
    
    # 如果所有啟用條件都通過，返回資訊
    latest_row = recent_df.iloc[-1]
    result = {
        'code': stock_code,
        'latest_date': latest_row['日期'].strftime('%Y-%m-%d'),
        'latest_close': latest_row['收盤價'],
        'passes': passes
    }
    
    if FLAG_VOLUME_SPIKE and volume_pass:
        result['last_volume'] = recent_df['成交張數'].iloc[-1]
        prev_vols = recent_df['成交張數'].iloc[-(lookback+1):-1].dropna()
        result['max_prev_volume'] = prev_vols.max() if len(prev_vols) > 0 else 0
        result['multiple'] = f"{result['last_volume'] / result['max_prev_volume']:.2f}" if result['max_prev_volume'] > 0 else "N/A"
    
    if FLAG_RED_THREE and red_three_pass and closes_list:
        result['closes'] = closes_list
    
    if FLAG_NET_BUY and net_buy_pass and net_summary:
        result['net_summary'] = net_summary
    
    return result

# ==============================
# 📈 生成 Plotly K線圖（改進版）
# ==============================
def generate_stock_chart(code, name, df=None, output_folder=None, type_str='未知', sector='未知', industry_category=None):
    """
    生成股票 K線圖（含三大法人買賣超與成交量）
    
    Args:
        code: 股票代碼
        name: 股票名稱
        df: 股票資料（若為None則從資料庫讀取）
        output_folder: 輸出資料夾路徑（若為None則使用OUTPUT_CHARTS_FOLDER）
        type_str: 市場類型（上市/上櫃）
        sector: 產業別
        industry_category: 產業分類（用於概念股模式）
    
    Returns:
        bool: 成功返回True，失敗返回False
    """
    try:
        # 若未提供df，從資料庫讀取
        if df is None:
            df = read_stock_from_db(code)
            if df is None or len(df) == 0:
                print(f"    ⚠️ 無法讀取 {code} 的資料")
                return False
        
        # 資料預處理
        df = df.copy()
        df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        
        for col in ['開盤價', '最高價', '最低價', '收盤價', '成交張數']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        for col in ['外資買賣超', '投信買賣超', '自營商買賣超']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(subset=['日期'], inplace=True)
        df.sort_values('日期', inplace=True)
        
        if len(df) < 2:
            print(f"    ⚠️ {code} 資料點不足")
            return False
        
        # 計算三大法人合計
        if all(col in df.columns for col in ['外資買賣超', '投信買賣超', '自營商買賣超']):
            df['三大法人合計'] = df['外資買賣超'].fillna(0) + df['投信買賣超'].fillna(0) + df['自營商買賣超'].fillna(0)
        
        # 取最近60天
        plot_df = df.tail(60)
        
        # 執行量價分析
        analysis = analyze_volume_price_pattern(plot_df)
        
        # 建立子圖（K線 + 成交量 + 法人買賣超）
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.5, 0.25, 0.25],
            subplot_titles=(
                f"{code} {name} ({type_str} | {sector})" + (f" | {industry_category}" if industry_category else ""),
                "成交量（張）",
                "三大法人買賣超（張）"
            )
        )
        
        # K線圖
        fig.add_trace(
            go.Candlestick(
                x=plot_df['日期'],
                open=plot_df['開盤價'],
                high=plot_df['最高價'],
                low=plot_df['最低價'],
                close=plot_df['收盤價'],
                name='K線',
                increasing_line_color='red',
                decreasing_line_color='green'
            ),
            row=1, col=1
        )
        
        # 成交量
        colors = ['red' if row['收盤價'] >= row['開盤價'] else 'green' 
                  for _, row in plot_df.iterrows()]
        
        fig.add_trace(
            go.Bar(
                x=plot_df['日期'],
                y=plot_df['成交張數'],
                name='成交量',
                marker_color=colors,
                showlegend=False
            ),
            row=2, col=1
        )
        
        # 三大法人買賣超
        if all(col in plot_df.columns for col in ['外資買賣超', '投信買賣超', '自營商買賣超', '三大法人合計']):
            fig.add_trace(
                go.Bar(x=plot_df['日期'], y=plot_df['外資買賣超'], name='外資',
                       marker_color='rgba(255,0,0,0.6)'),
                row=3, col=1
            )
            fig.add_trace(
                go.Bar(x=plot_df['日期'], y=plot_df['投信買賣超'], name='投信',
                       marker_color='rgba(0,255,0,0.6)'),
                row=3, col=1
            )
            fig.add_trace(
                go.Bar(x=plot_df['日期'], y=plot_df['自營商買賣超'], name='自營',
                       marker_color='rgba(0,0,255,0.6)'),
                row=3, col=1
            )
            fig.add_trace(
                go.Scatter(x=plot_df['日期'], y=plot_df['三大法人合計'], 
                          name='三大法人合計',
                          line=dict(color='black', width=2)),
                row=3, col=1
            )
        
        # 添加分析結果註解
        latest = plot_df.iloc[-1]
        annotation_text = f"<b>量價分析</b><br>"
        annotation_text += f"操作建議: {analysis['action']}<br>"
        annotation_text += f"風險等級: {analysis['risk_level']}<br>"
        annotation_text += f"綜合分析: {analysis['summary']}<br>"
        if analysis['signals']:
            annotation_text += "<br>".join(analysis['signals'])
        
        fig.add_annotation(
            text=annotation_text,
            xref="paper", yref="paper",
            x=0.02, y=0.98,
            xanchor='left', yanchor='top',
            showarrow=False,
            bgcolor="rgba(255, 255, 255, 0.8)",
            bordercolor="black",
            borderwidth=1,
            font=dict(size=10)
        )
        
        # 設定布局
        fig.update_layout(
            height=900,
            xaxis_rangeslider_visible=False,
            hovermode='x unified',
            font=dict(family="Microsoft JhengHei, Arial", size=12)
        )
        
        fig.update_xaxes(title_text="日期", row=3, col=1)
        fig.update_yaxes(title_text="價格", row=1, col=1)
        fig.update_yaxes(title_text="張數", row=2, col=1)
        fig.update_yaxes(title_text="張數", row=3, col=1)
        
        # 儲存檔案
        if output_folder is None:
            output_folder = Path(OUTPUT_CHARTS_FOLDER)
        else:
            output_folder = Path(output_folder)
        
        output_folder.mkdir(exist_ok=True, parents=True)
        
        html_path = output_folder / f"{code}_{name}.html"
        fig.write_html(str(html_path))
        
        return True
        
    except Exception as e:
        print(f"    ❌ 生成圖表失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==============================
# 🎯 主程式
# ==============================
def main():
    """主程式：掃描所有股票並根據條件篩選"""
    base_output_folder = Path(OUTPUT_CHARTS_FOLDER)
    base_output_folder.mkdir(exist_ok=True)
    
    # 從資料庫獲取所有股票代碼
    stock_codes = get_all_stock_codes()
    if not stock_codes:
        print(f"📁 資料庫中沒有股票資料！")
        return
    
    # 從資料庫讀取最新日期
    latest_date_str = None
    try:
        if Path(DB_TSE_PATH).exists():
            conn = sqlite3.connect(DB_TSE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(日期) FROM stock_data")
            result = cursor.fetchone()
            if result and result[0]:
                latest_date = pd.to_datetime(result[0])
                latest_date_str = latest_date.strftime('%Y.%m.%d')
            conn.close()
        
        if latest_date_str:
            print(f"📅 最新資料日期: {latest_date_str}")
        else:
            from datetime import datetime
            latest_date_str = datetime.now().strftime('%Y.%m.%d')
    except Exception as e:
        print(f"⚠️ 無法讀取日期，使用當前日期: {e}")
        from datetime import datetime
        latest_date_str = datetime.now().strftime('%Y.%m.%d')
    
    # 建立以日期命名的子資料夾
    output_folder = base_output_folder / latest_date_str
    output_folder.mkdir(exist_ok=True)
    print(f"📁 輸出資料夾: {output_folder}\n")

    enabled = []
    if FLAG_VOLUME_SPIKE: enabled.append("爆量")
    if FLAG_RED_THREE: enabled.append("紅三兵")
    if FLAG_NET_BUY: enabled.append("三大法人≥2天淨買超")
    
    print(f"🔍 掃描 {len(stock_codes)} 檔股票...")
    print(f"   • 啟用條件: {' + '.join(enabled) if enabled else '無'}\n")

    # 篩選符合條件的股票
    results = []
    for stock_code in stock_codes:
        res = analyze_stock(stock_code)
        if res:
            results.append(res)

    if FLAG_VOLUME_SPIKE:
        results.sort(key=lambda x: x.get('last_volume', 0), reverse=True)

    print("=" * 70)
    if results:
        print(f"✅ 找到 {len(results)} 檔符合條件：\n")
        
        chart_count = 0
        for r in results:
            code = r['code']
            info = company_info.get(code, {})
            name = info.get('name', '未知')
            type_str = info.get('type', '未知')
            sector = info.get('sector', '未知')

            print(f"{code} | {name} | {type_str} | {sector} | 日期: {r['latest_date']} | 收盤: {r['latest_close']:.2f}")
            if 'last_volume' in r:
                print(f"    ▲ 成交量: {r['last_volume']:,} 張 (前高 {r['max_prev_volume']:,}, {r['multiple']}x)")
            if 'closes' in r:
                c = r['closes']
                print(f"    📈 紅三兵: {c[0]} → {c[1]} → {c[2]}")
            if 'net_summary' in r:
                summary = r['net_summary']
                print(f"    💰 三大法人合計買超（外/投/自 → 合計）：")
                for i, (f, t, d, total) in enumerate(summary['details'], start=1):
                    sign = "🔴" if total <= 0 else "🟢"
                    print(f"        第{i}天： {int(f):>3} / {int(t):>3} / {int(d):>3} → {int(total):>+6} 張 {sign}")
                print(f"        ▸ 合計 >0 天數：{summary['positive_days']}/3")
            
            # 生成圖表
            print(f"    🎨 生成圖表...")
            if generate_stock_chart(code, name, None, output_folder, type_str, sector):
                chart_count += 1
            
            print()
        
        print("=" * 70)
        print(f"✅ 成功生成 {chart_count} 個圖表到 {output_folder} 資料夾")
    else:
        print("❌ 未找到符合所有啟用條件的股票")

if __name__ == "__main__":
    main()
