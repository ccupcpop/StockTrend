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

# 概念股模式
IS_CONCEPT_STOCK = True   # 是否使用概念股模式

# 資料庫路徑
DB_TSE_PATH = "stock_data/stock_tse.db"  # 上市股票資料庫
DB_OTC_PATH = "stock_data/stock_otc.db"  # 上櫃股票資料庫
OUTPUT_CHARTS_FOLDER = "output_charts"
CONCEPT_STOCKS_CSV = "concept_stocks.csv"  # 概念股清單檔案

# 爆量參數（一般模式）
VOL_LOOKBACK = 7           # 回看天數
VOL_MULTIPLE = 1.5         # 倍數（相對於前期最高量）
MIN_VOLUME_THRESHOLD = 5000  # 最近一天成交量最低門檻（張數）

# 爆量參數（概念股模式）- 當 IS_CONCEPT_STOCK = True 且 FLAG_VOLUME_SPIKE = True 時使用
VOL_CONCEPT_LOOKBACK = 4           # 回看天數
VOL_CONCEPT_MULTIPLE = 1.2         # 倍數（相對於前期最高量）
MIN_VOLUME_CONCEPT_THRESHOLD = 5000  # 最近一天成交量最低門檻（張數）
MAX_PRICE_CONCEPT_THRESHOLD = 50   # 最新收盤價最高門檻（元）- 高於此價格的股票會被過濾

# 紅三兵參數
PRICE_LOOKBACK = 3         # 回看天數

# ==============================
# 📊 資料庫讀取函數
# ==============================
def read_stock_from_db(stock_code):
    """
    從資料庫讀取指定股票的資料
    
    Args:
        stock_code: 股票代碼
    
    Returns:
        DataFrame 或 None
    """
    # 先從上市資料庫查詢
    df = None
    db_path = None
    
    if Path(DB_TSE_PATH).exists():
        try:
            conn = sqlite3.connect(DB_TSE_PATH)
            query = f"SELECT * FROM stock_data WHERE 股票代碼 = '{stock_code}' ORDER BY 日期"
            df = pd.read_sql_query(query, conn)
            conn.close()
            if len(df) > 0:
                db_path = DB_TSE_PATH
        except Exception as e:
            print(f"⚠️ 從 {DB_TSE_PATH} 讀取失敗: {e}")
    
    # 如果上市找不到，從上櫃資料庫查詢
    if df is None or len(df) == 0:
        if Path(DB_OTC_PATH).exists():
            try:
                conn = sqlite3.connect(DB_OTC_PATH)
                query = f"SELECT * FROM stock_data WHERE 股票代碼 = '{stock_code}' ORDER BY 日期"
                df = pd.read_sql_query(query, conn)
                conn.close()
                if len(df) > 0:
                    db_path = DB_OTC_PATH
            except Exception as e:
                print(f"⚠️ 從 {DB_OTC_PATH} 讀取失敗: {e}")
    
    if df is None or len(df) == 0:
        return None
    
    # 資料清理和轉換
    df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
    
    # 轉換數值欄位（移除千分位符號）
    numeric_columns = ['開盤價', '最高價', '最低價', '收盤價', '成交金額']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(',', '', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 成交張數已經是INTEGER，但可能需要確保是數值型態
    if '成交張數' in df.columns:
        df['成交張數'] = pd.to_numeric(df['成交張數'], errors='coerce')
    
    # 法人資料已經是REAL型態
    institutional_columns = ['外陸資買賣超張數', '投信買賣超張數', '自營商買賣超張數']
    for col in institutional_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 移除無效資料
    df.dropna(subset=['日期'], inplace=True)
    df.sort_values('日期', inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    return df

def get_all_stock_codes():
    """
    從資料庫獲取所有股票代碼
    
    Returns:
        list: 股票代碼列表
    """
    codes = set()
    
    # 從上市資料庫讀取
    if Path(DB_TSE_PATH).exists():
        try:
            conn = sqlite3.connect(DB_TSE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT 股票代碼 FROM stock_data")
            tse_codes = [row[0] for row in cursor.fetchall()]
            codes.update(tse_codes)
            conn.close()
        except Exception as e:
            print(f"⚠️ 從 {DB_TSE_PATH} 讀取股票代碼失敗: {e}")
    
    # 從上櫃資料庫讀取
    if Path(DB_OTC_PATH).exists():
        try:
            conn = sqlite3.connect(DB_OTC_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT 股票代碼 FROM stock_data")
            otc_codes = [str(row[0]) for row in cursor.fetchall()]
            codes.update(otc_codes)
            conn.close()
        except Exception as e:
            print(f"⚠️ 從 {DB_OTC_PATH} 讀取股票代碼失敗: {e}")
    
    return sorted(list(codes))

def get_latest_date_from_db():
    """
    從資料庫獲取最新的日期
    
    Returns:
        str: 最新日期字串 (YYYY.MM.DD)
    """
    latest_date = None
    
    # 從上市資料庫查詢
    if Path(DB_TSE_PATH).exists():
        try:
            conn = sqlite3.connect(DB_TSE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(日期) FROM stock_data")
            result = cursor.fetchone()
            if result and result[0]:
                latest_date = pd.to_datetime(result[0]).strftime('%Y.%m.%d')
            conn.close()
        except Exception as e:
            print(f"⚠️ 從 {DB_TSE_PATH} 讀取最新日期失敗: {e}")
    
    if latest_date is None:
        from datetime import datetime
        latest_date = datetime.now().strftime('%Y.%m.%d')
    
    return latest_date

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
    if '最高價' in latest and '最低價' in latest and '開盤價' in latest and '收盤價' in latest:
        body_high = max(latest['開盤價'], latest['收盤價'])
        body_low = min(latest['開盤價'], latest['收盤價'])
        body_size = abs(latest['收盤價'] - latest['開盤價'])
        
        upper_shadow = latest['最高價'] - body_high
        lower_shadow = body_low - latest['最低價']
        
        # 上天入地（影線是實體2倍）
        if upper_shadow > body_size * 2 or lower_shadow > body_size * 2:
            signals.append("⚡ 上天入地（觀望）")
            action_score = 0
            risk_factors.append("劇烈波動")
        
        # 下影線
        if lower_shadow > body_size * 0.5:
            if is_high_volume:
                signals.append("💡 高量下影線（機會）")
                action_score += 3
            else:
                signals.append("⚠️ 非高量下影線（風險）")
                action_score -= 2
                risk_factors.append("非高量下影線")
        
        # 上影線碰壓力
        if resistance_price and latest['最高價'] >= resistance_price * 0.98:
            if latest['收盤價'] < body_high:
                signals.append("⚠️ 上影線碰壓力過不去（減倉）")
                action_score -= 3
                risk_factors.append("遇阻回落")
    
    # ===== 5. 趨勢判斷 =====
    # 連續三天高低點下移 = 下跌趨勢
    if len(recent) >= 3:
        last_3 = recent.tail(3)
        if '最高價' in last_3.columns and '最低價' in last_3.columns:
            highs = last_3['最高價'].values
            lows = last_3['最低價'].values
            
            if all(highs[i] > highs[i+1] for i in range(2)) and all(lows[i] > lows[i+1] for i in range(2)):
                signals.append("📉 下跌趨勢確立")
                action_score -= 3
                risk_factors.append("下跌趨勢")
    
    # ===== 6. 量能型態 =====
    if '成交張數' in recent.columns and len(recent) >= 4:
        vols = recent.tail(4)['成交張數'].values
        
        # 梯量判斷
        if all(vols[i] < vols[i+1] for i in range(3)):
            # 上漲梯量
            if latest['收盤價'] > prev_3['收盤價']:
                signals.append("⚠️ 上漲梯量（風險）")
                action_score -= 3
                risk_factors.append("上漲梯量")
        elif all(vols[i] > vols[i+1] for i in range(3)):
            # 下跌梯量（縮量）
            if latest['收盤價'] < prev_3['收盤價']:
                signals.append("✓ 下跌縮量（機會）")
                action_score += 2
    
    # ===== 7. 法人動向 =====
    if all(col in latest for col in ['外陸資買賣超張數', '投信買賣超張數', '自營商買賣超張數']):
        foreign = latest['外陸資買賣超張數']
        trust = latest['投信買賣超張數']
        dealer = latest['自營商買賣超張數']
        total_inst = foreign + trust + dealer
        
        if total_inst > 0:
            if abs(total_inst) > 1000:
                signals.append(f"💰 法人大買：{int(total_inst):,}張")
                action_score += 3
            else:
                signals.append(f"💵 法人買超：{int(total_inst):,}張")
                action_score += 1
        elif total_inst < 0:
            if abs(total_inst) > 1000:
                signals.append(f"📤 法人大賣：{int(total_inst):,}張")
                action_score -= 3
                risk_factors.append("法人大賣")
            else:
                signals.append(f"📤 法人賣超：{int(total_inst):,}張")
                action_score -= 1
    
    # ===== 最終判斷 =====
    if action_score >= 8:
        action = '重倉'
        risk_level = '中'
    elif action_score >= 4:
        action = '上車'
        risk_level = '低'
    elif action_score <= -6:
        action = '清倉'
        risk_level = '高'
    elif action_score <= -3:
        action = '減倉'
        risk_level = '中'
    else:
        action = '觀望'
        risk_level = '中'
    
    # 風險調整
    if len(risk_factors) >= 2:
        risk_level = '高'
        if action in ['重倉', '上車']:
            action = '觀望'
    
    # 生成摘要
    summary_parts = []
    if signals:
        summary_parts.append(f"{len(signals)}個信號")
    if risk_factors:
        summary_parts.append(f"風險點:{','.join(risk_factors)}")
    summary = ' | '.join(summary_parts) if summary_parts else '正常'
    
    return {
        'signals': signals,
        'action': action,
        'risk_level': risk_level,
        'summary': summary
    }

# ==============================
# 📊 公司資訊（類型/產業）
# ==============================
company_info = {}

def load_company_info():
    """
    從資料庫載入公司資訊（股票名稱）
    """
    global company_info
    
    # 從上市資料庫讀取
    if Path(DB_TSE_PATH).exists():
        try:
            conn = sqlite3.connect(DB_TSE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT 股票代碼, 股票名稱 FROM stock_data")
            for row in cursor.fetchall():
                code, name = str(row[0]), row[1]
                company_info[code] = {
                    'name': name,
                    'type': '上市',
                    'sector': '未知'
                }
            conn.close()
        except Exception as e:
            print(f"⚠️ 從 {DB_TSE_PATH} 讀取公司資訊失敗: {e}")
    
    # 從上櫃資料庫讀取
    if Path(DB_OTC_PATH).exists():
        try:
            conn = sqlite3.connect(DB_OTC_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT 股票代碼, 股票名稱 FROM stock_data")
            for row in cursor.fetchall():
                code, name = str(row[0]), row[1]
                if code not in company_info:  # 優先保留上市資訊
                    company_info[code] = {
                        'name': name,
                        'type': '上櫃',
                        'sector': '未知'
                    }
            conn.close()
        except Exception as e:
            print(f"⚠️ 從 {DB_OTC_PATH} 讀取公司資訊失敗: {e}")

# ==============================
# 📊 股票篩選 - 爆量檢測
# ==============================
def check_volume_spike(df, lookback=VOL_LOOKBACK, multiple=VOL_MULTIPLE, min_threshold=MIN_VOLUME_THRESHOLD):
    """檢查是否符合爆量條件"""
    if '成交張數' not in df.columns or len(df) < lookback + 1:
        return None
    
    last_volume = df['成交張數'].iloc[-1]
    if pd.isna(last_volume) or last_volume < min_threshold:
        return None
    
    prev_volumes = df['成交張數'].iloc[-(lookback+1):-1]
    prev_volumes = prev_volumes[prev_volumes.notna()]
    
    if len(prev_volumes) == 0:
        return None
    
    max_prev_volume = prev_volumes.max()
    if last_volume >= max_prev_volume * multiple:
        return {
            'last_volume': int(last_volume),
            'max_prev_volume': int(max_prev_volume),
            'multiple': f"{last_volume / max_prev_volume:.2f}"
        }
    return None

# ==============================
# 📊 股票篩選 - 紅三兵檢測
# ==============================
def check_red_three(df, lookback=PRICE_LOOKBACK):
    """檢查是否為紅三兵"""
    if '收盤價' not in df.columns or len(df) < lookback:
        return None
    
    closes = df['收盤價'].iloc[-lookback:].values
    if any(pd.isna(closes)):
        return None
    
    if all(closes[i] < closes[i+1] for i in range(lookback - 1)):
        return {'closes': [f"{c:.2f}" for c in closes]}
    return None

# ==============================
# 📊 股票篩選 - 法人淨買超檢測
# ==============================
def check_net_buy(df, lookback=PRICE_LOOKBACK):
    """檢查3天中至少2天法人總和淨買超 > 0"""
    required_cols = ['外陸資買賣超張數', '投信買賣超張數', '自營商買賣超張數']
    if not all(c in df.columns for c in required_cols) or len(df) < lookback:
        return None
    
    last_n = df[required_cols].iloc[-lookback:]
    
    details = []
    positive_count = 0
    for _, row in last_n.iterrows():
        foreign = row['外陸資買賣超張數'] if not pd.isna(row['外陸資買賣超張數']) else 0
        trust = row['投信買賣超張數'] if not pd.isna(row['投信買賣超張數']) else 0
        dealer = row['自營商買賣超張數'] if not pd.isna(row['自營商買賣超張數']) else 0
        total = foreign + trust + dealer
        if total > 0:
            positive_count += 1
        details.append((foreign, trust, dealer, total))
    
    if positive_count >= 2:
        return {
            'positive_days': positive_count,
            'details': details
        }
    return None

# ==============================
# 📈 主篩選函數
# ==============================
def analyze_stock(stock_code_or_df, vol_lookback=VOL_LOOKBACK, vol_multiple=VOL_MULTIPLE, min_volume_threshold=MIN_VOLUME_THRESHOLD):
    """
    分析單一股票
    
    Args:
        stock_code_or_df: 股票代碼(str) 或 DataFrame
        vol_lookback: 爆量回看天數
        vol_multiple: 爆量倍數
        min_volume_threshold: 最低成交量門檻
    
    Returns:
        dict 或 None
    """
    # 讀取資料
    if isinstance(stock_code_or_df, str):
        df = read_stock_from_db(stock_code_or_df)
        stock_code = stock_code_or_df
    elif isinstance(stock_code_or_df, pd.DataFrame):
        df = stock_code_or_df
        stock_code = df['股票代碼'].iloc[0] if '股票代碼' in df.columns else 'unknown'
    else:
        return None
    
    if df is None or len(df) < 5:
        return None
    
    result = {'code': str(stock_code)}
    
    # 獲取最新日期和收盤價
    if '日期' in df.columns:
        result['latest_date'] = df['日期'].iloc[-1].strftime('%Y-%m-%d')
    if '收盤價' in df.columns:
        result['latest_close'] = df['收盤價'].iloc[-1]
    
    # 檢查各項條件
    passes = True
    
    if FLAG_VOLUME_SPIKE:
        vol_result = check_volume_spike(df, vol_lookback, vol_multiple, min_volume_threshold)
        if vol_result:
            result.update(vol_result)
        else:
            passes = False
    
    if FLAG_RED_THREE and passes:
        red_result = check_red_three(df)
        if red_result:
            result.update(red_result)
        else:
            passes = False
    
    if FLAG_NET_BUY and passes:
        net_result = check_net_buy(df)
        if net_result:
            result['net_summary'] = net_result
        else:
            passes = False
    
    return result if passes else None

# ==============================
# 🎨 圖表生成函數
# ==============================
def generate_stock_chart(code, name, stock_df_or_code, output_folder, type_str='', sector='', industry_category=None):
    """
    生成股票K線圖（含量價戰法分析）
    
    Args:
        code: 股票代碼
        name: 股票名稱
        stock_df_or_code: DataFrame 或股票代碼
        output_folder: 輸出資料夾
        type_str: 類型（上市/上櫃）
        sector: 產業類別
        industry_category: 概念股產業分類
    
    Returns:
        bool: 是否成功生成
    """
    try:
        # 讀取資料
        if isinstance(stock_df_or_code, pd.DataFrame):
            df = stock_df_or_code.copy()
        else:
            df = read_stock_from_db(stock_df_or_code)
        
        if df is None or len(df) < 20:
            print(f"        ⚠️ {code} {name} 資料不足，無法生成圖表")
            return False
        
        # 確保資料按日期排序
        df = df.sort_values('日期').reset_index(drop=True)
        
        # 取最近60天資料（如果有的話）
        df_chart = df.tail(60).copy()
        
        # 執行量價戰法分析
        analysis = analyze_volume_price_pattern(df_chart)
        
        # 建立圖表
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
            subplot_titles=(f'{code} {name} - K線圖 【{analysis["action"]}】風險:{analysis["risk_level"]}', '成交量')
        )
        
        # K線圖
        fig.add_trace(
            go.Candlestick(
                x=df_chart['日期'],
                open=df_chart['開盤價'],
                high=df_chart['最高價'],
                low=df_chart['最低價'],
                close=df_chart['收盤價'],
                name='K線',
                increasing_line_color='red',
                decreasing_line_color='green'
            ),
            row=1, col=1
        )
        
        # 成交量柱狀圖
        colors = ['red' if df_chart['收盤價'].iloc[i] >= df_chart['開盤價'].iloc[i] else 'green'
                  for i in range(len(df_chart))]
        
        fig.add_trace(
            go.Bar(
                x=df_chart['日期'],
                y=df_chart['成交張數'],
                name='成交量',
                marker_color=colors,
                showlegend=False
            ),
            row=2, col=1
        )
        
        # 更新佈局
        title_parts = [f'{code} {name}']
        if type_str:
            title_parts.append(f'[{type_str}]')
        if sector and sector != '未知':
            title_parts.append(f'{sector}')
        if industry_category:
            title_parts.append(f'【{industry_category}】')
        
        title_parts.append(f'<br>操作建議: <b>{analysis["action"]}</b>')
        title_parts.append(f'風險等級: {analysis["risk_level"]}')
        
        if analysis['signals']:
            signals_text = '<br>' + '<br>'.join(analysis['signals'][:5])  # 最多顯示5個信號
            title_parts.append(signals_text)
        
        fig.update_layout(
            title=' '.join(title_parts),
            xaxis_rangeslider_visible=False,
            height=800,
            showlegend=True,
            hovermode='x unified'
        )
        
        fig.update_xaxes(title_text="日期", row=2, col=1)
        fig.update_yaxes(title_text="價格", row=1, col=1)
        fig.update_yaxes(title_text="張數", row=2, col=1)
        
        # 儲存圖表
        output_path = Path(output_folder) / f"{code}_{name}.html"
        fig.write_html(str(output_path))
        
        return True
        
    except Exception as e:
        print(f"        ❌ 生成圖表失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==============================
# 🚀 主函數
# ==============================
def main():
    """主程式進入點"""
    print("=" * 70)
    print("🔍 台股趨勢掃描器 - 從資料庫讀取版本")
    print("=" * 70)
    
    # 檢查資料庫檔案是否存在
    if not Path(DB_TSE_PATH).exists() and not Path(DB_OTC_PATH).exists():
        print(f"❌ 找不到資料庫檔案：{DB_TSE_PATH} 或 {DB_OTC_PATH}")
        return
    
    # 載入公司資訊
    print("📂 載入公司資訊...")
    load_company_info()
    print(f"   ✓ 已載入 {len(company_info)} 家公司資訊\n")
    
    # 建立輸出資料夾
    base_output_folder = Path(OUTPUT_CHARTS_FOLDER)
    base_output_folder.mkdir(exist_ok=True)
    
    # ==========================================
    # 概念股模式
    # ==========================================
    if IS_CONCEPT_STOCK:
        print("📊 模式：概念股掃描")
        print(f"   • 資料庫: {DB_TSE_PATH}, {DB_OTC_PATH}")
        
        enabled = []
        if FLAG_VOLUME_SPIKE:
            enabled.append(f"爆量(回看{VOL_CONCEPT_LOOKBACK}天, {VOL_CONCEPT_MULTIPLE}x)")
        if FLAG_RED_THREE:
            enabled.append("紅三兵")
        if FLAG_NET_BUY:
            enabled.append("法人買超")
        
        print(f"   • 啟用條件: {' + '.join(enabled) if enabled else '無'}")
        print(f"   • 收盤價門檻: ≤ {MAX_PRICE_CONCEPT_THRESHOLD} 元")
        
        if FLAG_VOLUME_SPIKE:
            print(f"   • 爆量條件: 回看{VOL_CONCEPT_LOOKBACK}天, 倍數{VOL_CONCEPT_MULTIPLE}x, 最低門檻{MIN_VOLUME_CONCEPT_THRESHOLD:,}張")
        
        # 獲取最新日期
        latest_date_str = get_latest_date_from_db()
        print(f"📅 最新資料日期: {latest_date_str}")
        
        # 建立以日期_All命名的子資料夾
        output_folder = base_output_folder / f"{latest_date_str}_All"
        output_folder.mkdir(exist_ok=True)
        print(f"📁 輸出資料夾: {output_folder}\n")
        
        # 讀取概念股清單
        concept_csv_path = Path(CONCEPT_STOCKS_CSV)
        if not concept_csv_path.exists():
            print(f"❌ 概念股清單檔案 '{CONCEPT_STOCKS_CSV}' 不存在！")
            return
        
        try:
            concept_df = pd.read_csv(concept_csv_path, encoding='utf-8')
            print(f"📋 讀取到 {len(concept_df)} 檔概念股\n")
            
            chart_count = 0
            filtered_count = 0
            for idx, row in concept_df.iterrows():
                industry = row['產業分類']
                code = str(row['股票代碼'])
                name = row['股票名稱']
                
                # 從資料庫讀取股票資料
                df = read_stock_from_db(code)
                if df is None or len(df) == 0:
                    print(f"⚠️  [{idx+1}/{len(concept_df)}] {industry} | {code} {name} - 資料庫中無資料")
                    continue
                
                # 檢查最新收盤價是否符合門檻
                try:
                    latest_close = df['收盤價'].iloc[-1]
                    
                    if pd.isna(latest_close):
                        print(f"⚠️  [{idx+1}/{len(concept_df)}] {industry} | {code} {name} - 無有效收盤價")
                        continue
                    
                    if latest_close > MAX_PRICE_CONCEPT_THRESHOLD:
                        print(f"⏭️  [{idx+1}/{len(concept_df)}] {industry} | {code} {name} - 收盤價 {latest_close:.2f} 高於門檻 {MAX_PRICE_CONCEPT_THRESHOLD}")
                        continue
                except Exception as e:
                    print(f"⚠️  [{idx+1}/{len(concept_df)}] {industry} | {code} {name} - 讀取數據失敗: {e}")
                    continue
                
                # 如果啟用爆量過濾，則檢查是否符合條件
                if FLAG_VOLUME_SPIKE:
                    stock_result = analyze_stock(
                        df,
                        vol_lookback=VOL_CONCEPT_LOOKBACK,
                        vol_multiple=VOL_CONCEPT_MULTIPLE,
                        min_volume_threshold=MIN_VOLUME_CONCEPT_THRESHOLD
                    )
                    if stock_result is None:
                        print(f"⏭️  [{idx+1}/{len(concept_df)}] {industry} | {code} {name} - 不符合爆量條件")
                        continue
                    
                    # 符合爆量條件，顯示詳細資訊
                    print(f"📊 [{idx+1}/{len(concept_df)}] {industry} | {code} {name}")
                    if 'last_volume' in stock_result:
                        print(f"    ▲ 成交量: {stock_result['last_volume']:,} 張 (前高 {stock_result['max_prev_volume']:,}, {stock_result['multiple']}x)")
                    filtered_count += 1
                else:
                    print(f"📊 [{idx+1}/{len(concept_df)}] {industry} | {code} {name}")
                
                # 生成圖表（存到日期_All資料夾）
                type_str = company_info.get(code, {}).get('type', '未知')
                sector = company_info.get(code, {}).get('sector', '未知')
                
                if generate_stock_chart(code, name, df, output_folder, type_str, sector, industry_category=industry):
                    chart_count += 1
                
                print()
            
            print("=" * 70)
            print(f"✅ 概念股掃描完成：")
            print(f"   • 總概念股數: {len(concept_df)}")
            if FLAG_VOLUME_SPIKE:
                print(f"   • 符合過濾條件（收盤價≤{MAX_PRICE_CONCEPT_THRESHOLD} 且爆量）: {filtered_count}")
            else:
                print(f"   • 符合收盤價門檻（≤{MAX_PRICE_CONCEPT_THRESHOLD}）: {chart_count}")
            print(f"   • 成功生成圖表: {chart_count}")
            print(f"   • 輸出資料夾: {output_folder}")
            
        except Exception as e:
            print(f"❌ 讀取概念股清單失敗: {e}")
            import traceback
            traceback.print_exc()
        
        return
    
    # ==========================================
    # 一般模式（原有邏輯）
    # ==========================================
    print("📊 模式：一般掃描")
    print(f"   • 資料庫: {DB_TSE_PATH}, {DB_OTC_PATH}")
    
    # 獲取所有股票代碼
    stock_codes = get_all_stock_codes()
    if not stock_codes:
        print(f"❌ 資料庫中沒有股票資料！")
        return
    
    # 獲取最新日期
    latest_date_str = get_latest_date_from_db()
    print(f"📅 最新資料日期: {latest_date_str}")
    
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
            df = read_stock_from_db(code)
            
            print(f"    🎨 生成圖表...")
            if generate_stock_chart(code, name, df, output_folder, type_str, sector):
                chart_count += 1
            
            print()
        
        print("=" * 70)
        print(f"✅ 成功生成 {chart_count} 個圖表到 {OUTPUT_CHARTS_FOLDER} 資料夾")
    else:
        print("❌ 未找到符合所有啟用條件的股票")

if __name__ == "__main__":
    main()
