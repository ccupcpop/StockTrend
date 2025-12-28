import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# ==============================
# 🔧 【三個可控制的條件開關】
# ==============================
FLAG_FILTER = False         # 是否過濾條件（False=全部生成，True=條件過濾）
FLAG_VOLUME_SPIKE = True   # 爆量
FLAG_RED_THREE = True      # 紅三兵
FLAG_NET_BUY = True        # 三大法人：3天中至少2天淨買超 > 0

FOLDER_PATH = "stock_data"
VOL_LOOKBACK = 7
VOL_MULTIPLE = 1.5
PRICE_LOOKBACK = 3
OUTPUT_CHARTS_FOLDER = "output_charts"

# 概念股CSV檔案
TSE_CONCEPT_CSV = "tse_concept_stocks.csv"
OTC_CONCEPT_CSV = "otc_concept_stocks.csv"

# ==============================
# 📋 載入概念股清單
# ==============================
def load_concept_stocks():
    """從概念股CSV檔案載入股票代碼"""
    stock_codes = []
    
    if os.path.exists(TSE_CONCEPT_CSV):
        try:
            df = pd.read_csv(TSE_CONCEPT_CSV, encoding="utf-8-sig", 
                            header=None, names=["代號", "名稱", "概念股"])
            codes = df["代號"].astype(str).str.strip().tolist()
            stock_codes.extend(codes)
            print(f"✓ 載入上市概念股: {len(codes)} 檔")
        except Exception as e:
            print(f"⚠️ 載入上市概念股失敗: {e}")
    
    if os.path.exists(OTC_CONCEPT_CSV):
        try:
            df = pd.read_csv(OTC_CONCEPT_CSV, encoding="utf-8-sig", 
                            header=None, names=["代號", "名稱", "概念股"])
            codes = df["代號"].astype(str).str.strip().tolist()
            stock_codes.extend(codes)
            print(f"✓ 載入櫃買概念股: {len(codes)} 檔")
        except Exception as e:
            print(f"⚠️ 載入櫃買概念股失敗: {e}")
    
    return list(set(stock_codes))  # 去除重複

# ==============================
# 🔧 讀取公司清單（無標題列）
# ==============================
def load_company_lists():
    tse_path = Path("tse_concept_stocks.csv")
    otc_path = Path("otc_concept_stocks.csv")

    company_info = {}

    if tse_path.exists():
        tse_df = pd.read_csv(tse_path, header=None, dtype=str)
        for _, row in tse_df.iterrows():
            code = str(row[0]).strip()
            if len(code) == 4 and code.isdigit():
                name = str(row[1]).strip() if len(row) > 1 else '未知'
                sector = str(row[2]).strip() if len(row) > 2 else '未知'
                company_info[code] = {
                    'name': name,
                    'type': '上市',
                    'sector': sector
                }

    if otc_path.exists():
        otc_df = pd.read_csv(otc_path, header=None, dtype=str)
        for _, row in otc_df.iterrows():
            code = str(row[0]).strip()
            if len(code) == 4 and code.isdigit():
                name = str(row[1]).strip() if len(row) > 1 else '未知'
                sector = str(row[2]).strip() if len(row) > 2 else '未知'
                company_info[code] = {
                    'name': name,
                    'type': '上櫃',
                    'sector': sector
                }

    return company_info

# ==============================
# 📊 分析單檔股票
# ==============================
def analyze_stock(file_path):
    try:
        # 先讀取所有欄位
        df = pd.read_csv(file_path, encoding='utf-8')
        
        # 檢查必要欄位是否存在
        required_cols = ['日期', '成交張數', '收盤價']
        if not all(col in df.columns for col in required_cols):
            return None
        
        # 選取需要的欄位
        cols_to_use = ['日期', '成交張數', '收盤價']
        optional_cols = ['外陸資買賣超張數', '投信買賣超張數', '自營商買賣超張數']
        
        for col in optional_cols:
            if col in df.columns:
                cols_to_use.append(col)
        
        df = df[cols_to_use]

        df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        df['成交張數'] = pd.to_numeric(df['成交張數'], errors='coerce')
        df['收盤價'] = pd.to_numeric(df['收盤價'], errors='coerce')
        
        # 法人資料
        if '外陸資買賣超張數' in df.columns:
            df['外陸資買賣超張數'] = pd.to_numeric(df['外陸資買賣超張數'], errors='coerce')
        if '投信買賣超張數' in df.columns:
            df['投信買賣超張數'] = pd.to_numeric(df['投信買賣超張數'], errors='coerce')
        if '自營商買賣超張數' in df.columns:
            df['自營商買賣超張數'] = pd.to_numeric(df['自營商買賣超張數'], errors='coerce')

        df.dropna(subset=['日期', '成交張數', '收盤價'], inplace=True)
        df.sort_values('日期', inplace=True)
        df.reset_index(drop=True, inplace=True)

        # 資料長度檢查
        if FLAG_FILTER:
            if len(df) < max(VOL_LOOKBACK, PRICE_LOOKBACK):
                return None
        else:
            if len(df) < 2:
                return None

        latest_date = df['日期'].iloc[-1].strftime('%Y-%m-%d')
        latest_close = df['收盤價'].iloc[-1]

        # 條件 1：爆量
        meets_volume = True
        last_vol_val = None
        max_prev_vol = None
        multiple = None

        if FLAG_VOLUME_SPIKE:
            recent_vol = df.tail(VOL_LOOKBACK)
            vols = recent_vol['成交張數'].values
            last_vol_val = vols[-1]
            prev_vols = vols[:-1]

            if not (last_vol_val > 0 and all(v > 0 for v in prev_vols)):
                meets_volume = False
            elif not all(last_vol_val > v for v in prev_vols):
                meets_volume = False
            else:
                max_prev_vol = max(prev_vols)
                if max_prev_vol <= 0 or last_vol_val < max_prev_vol * VOL_MULTIPLE:
                    meets_volume = False
                else:
                    multiple = round(last_vol_val / max_prev_vol, 2)
        else:
            meets_volume = True

        # 條件 2 + 3：紅三兵 + 三大法人
        meets_red_three = True
        meets_net_buy = True
        closes = None
        net_summary = None

        if FLAG_RED_THREE or FLAG_NET_BUY:
            recent_df = df.tail(PRICE_LOOKBACK)
            if len(recent_df) != PRICE_LOOKBACK:
                meets_red_three = False
                meets_net_buy = False
            else:
                prices = recent_df['收盤價'].values
                c1, c2, c3 = prices[0], prices[1], prices[2]
                closes = (round(c1, 2), round(c2, 2), round(c3, 2))

                if FLAG_RED_THREE:
                    if not (c1 < c2 < c3):
                        meets_red_three = False
                else:
                    meets_red_three = True

                if FLAG_NET_BUY:
                    has_institution_data = all(col in df.columns for col in 
                        ['外陸資買賣超張數', '投信買賣超張數', '自營商買賣超張數'])
                    
                    if has_institution_data:
                        foreign = recent_df['外陸資買賣超張數'].fillna(0).values
                        trust = recent_df['投信買賣超張數'].fillna(0).values
                        dealer = recent_df['自營商買賣超張數'].fillna(0).values

                        positive_days = 0
                        details = []

                        for f, t, d in zip(foreign, trust, dealer):
                            total = f + t + d
                            if total > 0:
                                positive_days += 1
                            details.append((f, t, d, total))

                        net_summary = {
                            'details': details,
                            'positive_days': positive_days
                        }

                        if positive_days < 2:
                            meets_net_buy = False
                    else:
                        if FLAG_FILTER:
                            meets_net_buy = False
                        else:
                            meets_net_buy = True
                else:
                    meets_net_buy = True
        else:
            meets_red_three = True
            meets_net_buy = True

        if meets_volume and meets_red_three and meets_net_buy:
            result = {
                'code': file_path.stem,
                'latest_date': latest_date,
                'latest_close': latest_close,
            }
            if FLAG_VOLUME_SPIKE:
                result.update({
                    'last_volume': int(last_vol_val),
                    'max_prev_volume': int(max_prev_vol),
                    'multiple': multiple
                })
            if FLAG_RED_THREE:
                result['closes'] = closes
            if FLAG_NET_BUY:
                result['net_summary'] = net_summary
            return result
        
        elif not FLAG_FILTER:
            result = {
                'code': file_path.stem,
                'latest_date': latest_date,
                'latest_close': latest_close,
            }
            if FLAG_VOLUME_SPIKE and last_vol_val and max_prev_vol:
                result.update({
                    'last_volume': int(last_vol_val),
                    'max_prev_volume': int(max_prev_vol),
                    'multiple': multiple
                })
            if FLAG_RED_THREE and closes:
                result['closes'] = closes
            if FLAG_NET_BUY and net_summary:
                result['net_summary'] = net_summary
            return result

    except Exception as e:
        print(f"⚠️ 處理 {file_path.name} 時出錯: {e}")
    return None

# ==============================
# 📈 生成單檔股票圖表
# ==============================
def generate_stock_chart(stock_code, stock_name, csv_file, output_folder, stock_type='未知', stock_sector='未知'):
    """生成單檔股票的HTML圖表（移除量價戰法分析，合併三大法人圖表）"""
    try:
        # 讀取資料
        df = pd.read_csv(csv_file, encoding='utf-8')
        
        # 轉換資料類型
        df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        for col in ['開盤價', '最高價', '最低價', '收盤價', '成交張數',
                    '外陸資買賣超張數', '投信買賣超張數', '自營商買賣超張數']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(subset=['日期'], inplace=True)
        df.sort_values('日期', inplace=True)
        
        # 取得最後一天收盤價
        latest_close = df['收盤價'].iloc[-1]
        latest_close_str = f"{latest_close:.2f}"
        
        # 檔案名稱改用收盤價
        output_filename = f"{stock_code}_{stock_name}_{latest_close_str}.html"
        output_path = output_folder / output_filename
        
        # 取最近60筆資料
        df_chart = df.tail(60).copy()
        
        # 計算移動平均線
        df_chart['MA5'] = df_chart['收盤價'].rolling(window=5, min_periods=1).mean()
        df_chart['MA10'] = df_chart['收盤價'].rolling(window=10, min_periods=1).mean()
        
        # 創建子圖（改為3層）
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            subplot_titles=('', '', ''),
            row_heights=[0.5, 0.25, 0.25],
            specs=[[{"secondary_y": False}],
                   [{"secondary_y": False}],
                   [{"secondary_y": True}]]  # 第三層使用雙Y軸
        )
        
        # 第一層：K線圖
        fig.add_trace(
            go.Candlestick(
                x=df_chart['日期'],
                open=df_chart['開盤價'],
                high=df_chart['最高價'],
                low=df_chart['最低價'],
                close=df_chart['收盤價'],
                name='K線',
                increasing_line_color='#FF5252',
                increasing_fillcolor='#FF5252',
                decreasing_line_color='#00C851',
                decreasing_fillcolor='#00C851',
                line=dict(width=0.8),
            ),
            row=1, col=1
        )
        
        # 添加MA5和MA10
        for ma_name, ma_col, color in [('MA5', 'MA5', 'blue'), ('MA10', 'MA10', 'orange')]:
            if ma_col in df_chart.columns and df_chart[ma_col].notna().sum() > 0:
                fig.add_trace(
                    go.Scatter(
                        x=df_chart['日期'],
                        y=df_chart[ma_col],
                        name=ma_name,
                        line=dict(color=color, width=1.5),
                        mode='lines',
                    ),
                    row=1, col=1
                )
        
        # 第二層：成交量
        if '成交張數' in df_chart.columns:
            volume_lots = pd.to_numeric(df_chart['成交張數'], errors='coerce')
            colors = []
            for i in range(len(df_chart)):
                if i == 0:
                    if df_chart['收盤價'].iloc[i] >= df_chart['開盤價'].iloc[i]:
                        colors.append('rgba(255, 82, 82, 0.8)')
                    else:
                        colors.append('rgba(0, 200, 81, 0.8)')
                else:
                    if df_chart['收盤價'].iloc[i] >= df_chart['收盤價'].iloc[i-1]:
                        colors.append('rgba(255, 82, 82, 0.8)')
                    else:
                        colors.append('rgba(0, 200, 81, 0.8)')
            
            fig.add_trace(
                go.Bar(
                    x=df_chart['日期'],
                    y=volume_lots,
                    name='成交量',
                    marker=dict(color=colors, line=dict(width=0)),
                    showlegend=True
                ),
                row=2, col=1
            )
        
        # 第三層：三大法人當日買賣超（左Y軸）+ 累積買賣超（右Y軸）
        has_institutional = False
        if '外陸資買賣超張數' in df_chart.columns:
            foreign = pd.to_numeric(df_chart['外陸資買賣超張數'], errors='coerce')
            trust = pd.to_numeric(df_chart.get('投信買賣超張數', 0), errors='coerce')
            dealer = pd.to_numeric(df_chart.get('自營商買賣超張數', 0), errors='coerce')
            
            if foreign.notna().sum() > 0 or trust.notna().sum() > 0 or dealer.notna().sum() > 0:
                has_institutional = True
                
                # 當日買賣超（柱狀圖，左Y軸）
                for name, data, color in [
                    ('外資', foreign, 'rgba(255, 82, 82, 0.6)'),
                    ('投信', trust, 'rgba(0, 200, 81, 0.6)'),
                    ('自營商', dealer, 'rgba(0, 191, 255, 0.6)')
                ]:
                    fig.add_trace(
                        go.Bar(
                            x=df_chart['日期'],
                            y=data,
                            name=f'{name}當日',
                            marker_color=color,
                            legendgroup=name,
                            showlegend=True
                        ),
                        row=3, col=1,
                        secondary_y=False
                    )
                
                # 累積買賣超（折線圖，右Y軸）
                foreign_cumsum = foreign.fillna(0).cumsum()
                trust_cumsum = trust.fillna(0).cumsum()
                dealer_cumsum = dealer.fillna(0).cumsum()
                
                for name, data, color in [
                    ('外資', foreign_cumsum, 'rgb(255, 82, 82)'),
                    ('投信', trust_cumsum, 'rgb(0, 200, 81)'),
                    ('自營商', dealer_cumsum, 'rgb(0, 191, 255)')
                ]:
                    fig.add_trace(
                        go.Scatter(
                            x=df_chart['日期'],
                            y=data,
                            name=f'{name}累積',
                            line=dict(color=color, width=2.5, shape='spline', smoothing=0.8),
                            mode='lines',
                            legendgroup=name,
                            showlegend=True
                        ),
                        row=3, col=1,
                        secondary_y=True
                    )
        
        # 計算統計數據
        latest = df_chart.iloc[-1]
        latest_date_str = latest['日期'].strftime('%Y-%m-%d')
        stats = {
            '成交量': latest['成交張數'] if '成交張數' in latest and pd.notna(latest['成交張數']) else 0,
            '外資累積': foreign_cumsum.iloc[-1] if has_institutional and len(foreign_cumsum) > 0 else 0,
            '投信累積': trust_cumsum.iloc[-1] if has_institutional and len(trust_cumsum) > 0 else 0,
            '自營累積': dealer_cumsum.iloc[-1] if has_institutional and len(dealer_cumsum) > 0 else 0,
        }
        
        # 更新佈局
        stats_line1 = (
            f"最新資料日期: {latest_date_str} | "
            f"外資累積: {stats['外資累積']:,.0f}張 | "
            f"投信累積: {stats['投信累積']:,.0f}張 | "
            f"自營累積: {stats['自營累積']:,.0f}張"
        )
        stats_line2 = f"股價K線圖 | 成交量: {stats['成交量']:,.0f}張"
        
        fig.update_layout(
            title=dict(
                text=f'{stock_code} {stock_name} ({stock_type} | {stock_sector}) 技術分析圖表 (最近60筆)<br><sub>{stats_line1}</sub><br><sub>{stats_line2}</sub>',
                x=0.5,
                xanchor='center',
                font=dict(size=16, family='Microsoft JhengHei, Arial, sans-serif')
            ),
            xaxis_rangeslider_visible=False,
            height=1200,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white',
            barmode='relative',
            legend=dict(
                orientation="v",
                yanchor="top",
                y=0.98,
                xanchor="left",
                x=0.01,
                bgcolor="rgba(255, 255, 255, 0.8)",
                bordercolor="lightgray",
                borderwidth=1,
                font=dict(family='Microsoft JhengHei, Arial, sans-serif')
            ),
            font=dict(family='Microsoft JhengHei, Arial, sans-serif'),
            dragmode='pan'
        )
        
        # 更新Y軸
        price_cols = ['開盤價', '最高價', '最低價', '收盤價']
        price_min = df_chart[price_cols].min().min()
        price_max = df_chart[price_cols].max().max()
        price_margin = (price_max - price_min) * 0.05
        price_range = [price_min - price_margin, price_max + price_margin]
        
        fig.update_yaxes(title_text="股價 (元)", row=1, col=1, range=price_range, fixedrange=True)
        fig.update_yaxes(title_text="成交量 (張)", row=2, col=1, tickformat=",", fixedrange=True)
        fig.update_yaxes(title_text="當日買賣超 (張)", row=3, col=1, tickformat=",", fixedrange=True, secondary_y=False)
        fig.update_yaxes(title_text="累積買賣超 (張)", row=3, col=1, tickformat=",", fixedrange=True, secondary_y=True)
        
        # 更新X軸 - 移除非交易日空隙
        start_date = df_chart['日期'].min()
        end_date = df_chart['日期'].max()
        trading_dates = df_chart['日期'].tolist()
        
        # 生成刻度值（每月1、6、11、16、21、26日）
        tickvals = []
        current = start_date.replace(day=1)
        while current <= end_date:
            for day in [1, 6, 11, 16, 21, 26]:
                try:
                    tick_date = current.replace(day=day)
                    if start_date <= tick_date <= end_date:
                        tickvals.append(tick_date)
                except:
                    pass
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        
        for i in range(1, 4):
            fig.update_xaxes(
                tickformat="%m-%d",
                tickangle=-45,
                tickmode='array',
                tickvals=tickvals,
                showticklabels=True,
                autorange=True,
                hoverformat="%m-%d",
                fixedrange=True,
                rangebreaks=[
                    dict(values=pd.date_range(start=start_date, end=end_date, freq='D')
                         .difference(pd.DatetimeIndex(trading_dates)).tolist())
                ],
                row=i, col=1
            )
        
        # 生成HTML
        html_string = fig.to_html(include_plotlyjs='cdn')
        
        # 包裝完整HTML（不包含量價戰法分析）
        viewport_meta = '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no">'
        full_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    {viewport_meta}
    <title>{stock_code} {stock_name}</title>
    <style>
        body {{ margin: 0; padding: 0; background: #f5f5f5; }}
    </style>
</head>
<body>
{html_string}
</body>
</html>'''
        
        # 儲存檔案
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        
        print(f"  ✓ 圖表已生成: {output_path}")
        return True
        
    except Exception as e:
        print(f"  ❌ 生成圖表失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==============================
# 🚀 主程式
# ==============================
def main():
    folder = Path(FOLDER_PATH)
    if not folder.exists():
        print(f"❌ 資料夾 '{FOLDER_PATH}' 不存在！")
        return

    # 從概念股CSV讀取
    stock_codes = load_concept_stocks()
    if stock_codes:
        csv_files = []
        for code in stock_codes:
            csv_path = folder / f"{code}.csv"
            if csv_path.exists():
                csv_files.append(csv_path)
        print(f"📊 從概念股清單找到 {len(csv_files)}/{len(stock_codes)} 檔資料\n")
    else:
        print(f"⚠️ 未找到概念股CSV，使用資料夾所有檔案")
        csv_files = list(folder.glob("*.csv"))
    
    if not csv_files:
        print(f"📁 資料夾 '{FOLDER_PATH}' 中沒有 .csv 檔案！")
        return

    # 建立輸出資料夾
    base_output_folder = Path(OUTPUT_CHARTS_FOLDER)
    base_output_folder.mkdir(exist_ok=True)
    
    # 從第一個CSV檔案讀取最新日期
    latest_date_str = None
    try:
        sample_df = pd.read_csv(csv_files[0], encoding='utf-8', usecols=['日期'])
        sample_df['日期'] = pd.to_datetime(sample_df['日期'], errors='coerce')
        sample_df.dropna(subset=['日期'], inplace=True)
        if len(sample_df) > 0:
            latest_date = sample_df['日期'].max()
            latest_date_str = latest_date.strftime('%Y.%m.%d')
            print(f"📅 最新資料日期: {latest_date_str}")
    except Exception as e:
        print(f"⚠️ 無法讀取日期，使用當前日期: {e}")
        from datetime import datetime
        latest_date_str = datetime.now().strftime('%Y.%m.%d')
    
    # 建立以日期命名的子資料夾
    output_folder = base_output_folder / latest_date_str
    output_folder.mkdir(exist_ok=True)
    print(f"📁 輸出資料夾: {output_folder}\n")

    # 加載公司資訊
    company_info = load_company_lists()

    enabled = []
    if FLAG_VOLUME_SPIKE: enabled.append("爆量")
    if FLAG_RED_THREE: enabled.append("紅三兵")
    if FLAG_NET_BUY: enabled.append("三大法人≥2天淨買超")
    
    print(f"🔍 掃描 {len(csv_files)} 檔股票...")
    if FLAG_FILTER:
        print(f"   • 過濾模式：啟用")
        print(f"   • 條件設定: {' + '.join(enabled) if enabled else '無'}\n")
    else:
        print(f"   • 過濾模式：關閉（全部生成）\n")

    # 篩選符合條件的股票
    results = []
    for i, csv_file in enumerate(csv_files, 1):
        if i % 50 == 0 or i == len(csv_files):
            print(f"   進度: {i}/{len(csv_files)}")
        res = analyze_stock(csv_file)
        if res:
            results.append(res)

    if FLAG_VOLUME_SPIKE:
        results.sort(key=lambda x: x.get('last_volume', 0), reverse=True)

    print("=" * 70)
    if results:
        if FLAG_FILTER:
            print(f"✅ 找到 {len(results)} 檔符合條件：\n")
        else:
            print(f"✅ 生成 {len(results)} 檔概念股圖表：\n")
        
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
                    f = 0 if pd.isna(f) else f
                    t = 0 if pd.isna(t) else t
                    d = 0 if pd.isna(d) else d
                    total = 0 if pd.isna(total) else total
                    
                    sign = "🔴" if total <= 0 else "🟢"
                    print(f"        第{i}天： {int(f):>3} / {int(t):>3} / {int(d):>3} → {int(total):>+6} 張 {sign}")
                print(f"        ▸ 合計 >0 天數：{summary['positive_days']}/3")
            
            # 生成圖表
            csv_file_path = folder / f"{code}.csv"
            
            print(f"    🎨 生成圖表...")
            if generate_stock_chart(code, name, csv_file_path, output_folder, type_str, sector):
                chart_count += 1
            
            print()
        
        print("=" * 70)
        print(f"✅ 成功生成 {chart_count} 個圖表到 {OUTPUT_CHARTS_FOLDER} 資料夾")
        
        # 合併所有HTML成單一檔案
        if chart_count > 0:
            print(f"\n{'='*70}")
            print("⏳ 合併所有HTML圖表...")
            print(f"{'='*70}")
            
            merge_all_charts_to_single_html(output_folder, latest_date_str)
    else:
        if FLAG_FILTER:
            print("❌ 未找到符合所有啟用條件的股票")
        else:
            print("❌ 沒有可生成的股票資料")

def merge_all_charts_to_single_html(output_folder, date_str):
    """合併output_folder資料夾內所有HTML檔案成一個Concept_ALL.html"""
    try:
        # 取得所有HTML檔案（排除已合併的檔案）
        html_files = sorted([f for f in output_folder.glob("*.html") if not f.name.startswith("Concept_ALL")])
        
        if not html_files:
            print("⚠️ 找不到HTML檔案可合併")
            return
        
        print(f"📄 找到 {len(html_files)} 個HTML檔案")
        
        # 收集所有圖表的HTML內容
        merged_html_parts = []
        
        for idx, html_file in enumerate(html_files, 1):
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 提取body內容
                import re
                start_match = re.search(r'<body[^>]*>', content, re.IGNORECASE)
                end_match = re.search(r'</body>\s*</html>\s*$', content, re.DOTALL | re.IGNORECASE)
                
                if start_match and end_match:
                    html_content = content[start_match.end():end_match.start()].strip()
                    body_match = True
                else:
                    body_match = None
                if body_match:
                    merged_html_parts.append(html_content)
                    
                    # 在每個圖表之間加入分隔線（最後一個除外）
                    if idx < len(html_files):
                        merged_html_parts.append('<div class="stock-separator"></div>')
                else:
                    print(f"⚠️ {html_file.name} 無法提取body內容")
                
                if idx % 20 == 0:
                    print(f"  進度: {idx}/{len(html_files)}")
                    
            except Exception as e:
                print(f"⚠️ 讀取 {html_file.name} 失敗: {e}")
                continue
        
        if not merged_html_parts:
            print("❌ 沒有成功讀取任何HTML內容")
            return
        
        # 合併所有內容
        all_charts_html = '\n'.join(merged_html_parts)
        
        # 包裝成完整的HTML
        viewport_meta = '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no">'
        
        touch_action_css = '''
    <style>
        html {
            -webkit-text-size-adjust: 100%;
            -ms-text-size-adjust: 100%;
            height: 100%;
            touch-action: manipulation;
        }

        body {
            margin: 0;
            padding: 0;
            height: 100%;
            overflow-y: scroll;
            overflow-x: hidden;
            -webkit-overflow-scrolling: touch;
            overscroll-behavior-y: contain;
            background: #f5f5f5;
        }

        .plotly {
            touch-action: auto;
            -ms-touch-action: auto;
            pointer-events: auto;
        }
        
        .plotly .svg-container {
            pointer-events: none !important;
        }
        
        .plotly .hoverlayer {
            pointer-events: auto !important;
        }

        * {
            -webkit-tap-highlight-color: rgba(0,0,0,0.1);
        }

        .stock-separator {
            height: 30px;
            background: linear-gradient(to bottom, #f0f0f0, #ffffff);
            margin: 20px 0;
            border-top: 2px solid #ddd;
            border-bottom: 2px solid #ddd;
        }
    </style>'''
        
        disable_gestures_script = '''
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            let touchStartTime = 0;
            
            document.addEventListener('touchstart', function(e) {
                touchStartTime = Date.now();
                if (e.touches.length > 1) {
                    e.preventDefault();
                }
            }, { passive: false });

            document.addEventListener('gesturestart', function(e) {
                e.preventDefault();
            }, { passive: false });

            document.addEventListener('gesturechange', function(e) {
                e.preventDefault();
            }, { passive: false });

            document.addEventListener('gestureend', function(e) {
                e.preventDefault();
            }, { passive: false });

            let lastTouchEnd = 0;
            document.addEventListener('touchend', function(e) {
                const now = Date.now();
                const touchDuration = now - touchStartTime;
                
                if (touchDuration < 200) {
                    if (now - lastTouchEnd <= 300) {
                        e.preventDefault();
                    }
                    lastTouchEnd = now;
                }
            }, { passive: false });

            document.addEventListener('wheel', function(e) {
                if (e.ctrlKey) {
                    e.preventDefault();
                }
            }, { passive: false });
        });
    </script>'''
        
        full_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    {viewport_meta}
    <title>概念股技術分析圖表合集 - {date_str}</title>
    {touch_action_css}
</head>
<body>
{all_charts_html}
{disable_gestures_script}
</body>
</html>'''
        
        # 儲存合併的HTML
        merged_output_path = output_folder / "Concept_ALL.html"
        with open(merged_output_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        
        file_size_mb = merged_output_path.stat().st_size / 1024 / 1024
        
        print(f"\n✅ 合併HTML已生成!")
        print(f"  檔案: Concept_ALL.html")
        print(f"  路徑: {merged_output_path}")
        print(f"  檔案大小: {file_size_mb:.2f} MB")
        print(f"  包含圖表: {len(html_files)} 個")
        
    except Exception as e:
        print(f"❌ 合併HTML失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()