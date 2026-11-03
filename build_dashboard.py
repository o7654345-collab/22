"""
글로벌 매크로 대시보드 빌드 스크립트
====================================
yfinance로 시장 데이터를 가져오고, RSS로 글로벌 뉴스를 수집한 뒤
Chart.js 기반의 정적 HTML 대시보드를 생성합니다.

사용법:
    python build_dashboard.py              # 실제 데이터로 빌드
    python build_dashboard.py --mock       # 목업 데이터로 미리보기 빌드

GitHub Actions에서 매일 자동 실행됩니다.
"""

import json
import os
import sys
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# ──────────────────────────────────────────────
# 1. 설정: 가져올 데이터 목록
# ──────────────────────────────────────────────

# yfinance 티커 매핑
TICKERS = {
    # ── 증시 ──
    "KOSPI":    "^KS11",
    "KOSPI200": "^KS200",
    "KOSDAQ":   "^KQ11",
    "DOW":      "^DJI",
    "NASDAQ":   "^IXIC",
    "상해종합":  "000001.SS",
    "NIKKEI":   "^N225",
    # ── 환율 (원화 기준) ──
    "USD/KRW":  "USDKRW=X",
    "EUR/KRW":  "EURKRW=X",
    "CNY/KRW":  "CNYKRW=X",
    "JPY/KRW":  "JPYKRW=X",   # 1엔 기준, 나중에 ×100
    # ── 원자재 ──
    "WTI":      "CL=F",
    "Gold(USD)":"GC=F",
    # ── 암호화폐 ──
    "BTC/KRW":  "BTC-KRW",
    # ── 채권 금리 ──
    "US10Y":    "^TNX",
}

# 전체 지표 목록 — (이름, 카테고리, 차트 선 색상)
# 화이트 크림 배경 위에서 또렷하게 읽히도록 채도를 조금 올린 톤입니다.
INDICATORS = [
    ("KOSPI",       "증시", "#2F43A6"),  # indigo
    ("KOSPI200",    "증시", "#5468C4"),
    ("KOSDAQ",      "증시", "#117A6B"),  # pine
    ("DOW",         "증시", "#946312"),  # ochre
    ("NASDAQ",      "증시", "#BC8118"),  # amber
    ("상해종합",     "증시", "#C04824"),  # rust
    ("NIKKEI",      "증시", "#B03A5C"),  # berry
    ("USD/KRW",     "환율", "#2F43A6"),
    ("EUR/KRW",     "환율", "#117A6B"),
    ("CNY/KRW",     "환율", "#7B3A8C"),  # plum
    ("JPY100/KRW",  "환율", "#B03A5C"),
    ("한국",        "금리", "#2F43A6"),
    ("미국",        "금리", "#BC8118"),
    ("유럽",        "금리", "#4F7A2E"),  # moss
    ("중국",        "금리", "#C04824"),
    ("일본",        "금리", "#B03A5C"),
    ("Gold(원/g)",  "기타", "#946312"),
    ("WTI($/bbl)",  "기타", "#4D5B58"),  # slate
    ("BTC(만원)",   "기타", "#C26715"),  # burnt orange
    ("휘발유(원/L)","기타", "#4F7A2E"),
    ("US10Y",       "기타", "#7B3A8C"),
]

# 뉴스 RSS 피드 — 카테고리별로 영어권 주요 매체를 묶어둡니다.
# 탭을 추가하려면 여기에 키 하나와 (매체명, RSS URL) 목록을 넣으면 됩니다.
NEWS_CATEGORIES = {
    "국제": [
        ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
        ("BBC",            "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("The Guardian",   "https://www.theguardian.com/world/rss"),
    ],
    "경제": [
        ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
        ("BBC",            "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("The Guardian",   "https://www.theguardian.com/business/rss"),
    ],
    "테크": [
        ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
        ("BBC",            "https://feeds.bbci.co.uk/news/technology/rss.xml"),
        ("The Guardian",   "https://www.theguardian.com/technology/rss"),
    ],
    "스포츠": [
        ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml"),
        ("BBC Sport",      "https://feeds.bbci.co.uk/sport/rss.xml"),
        ("The Guardian",   "https://www.theguardian.com/sport/rss"),
    ],
    "연예": [
        ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml"),
        ("BBC",            "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"),
        ("The Guardian",   "https://www.theguardian.com/culture/rss"),
    ],
}

# 카테고리당 표시할 기사 수
NEWS_PER_CATEGORY = 3

# 데이터 기간 (1년)
LOOKBACK_DAYS = 365


# ──────────────────────────────────────────────
# 2. 데이터 수집 함수
# ──────────────────────────────────────────────

def fetch_market_data():
    """yfinance를 사용해 시장 데이터를 수집합니다."""
    import yfinance as yf

    end = datetime.now()
    start = end - timedelta(days=LOOKBACK_DAYS)
    result = {}

    for name, ticker in TICKERS.items():
        try:
            # yfinance로 일별 종가 다운로드
            df = yf.download(ticker, start=start, end=end, progress=False)
            if df.empty:
                print(f"  ⚠ {name} ({ticker}): 데이터 없음, 건너뜀")
                continue

            # 종가 컬럼 추출 (MultiIndex 대응)
            if isinstance(df.columns, __import__('pandas').MultiIndex):
                close = df[("Close", ticker)] if ("Close", ticker) in df.columns else df["Close"].iloc[:, 0]
            else:
                close = df["Close"]

            # 날짜를 문자열로 변환하여 JSON 호환 딕셔너리로 저장
            series = {d.strftime("%Y-%m-%d"): round(float(v), 4)
                      for d, v in close.dropna().items()}
            result[name] = series
            print(f"  ✓ {name}: {len(series)}일치 수집")
        except Exception as e:
            print(f"  ✗ {name}: 에러 - {e}")

    # JPY/KRW → JPY100/KRW 변환 (100엔 기준)
    if "JPY/KRW" in result:
        result["JPY100/KRW"] = {d: round(v * 100, 2) for d, v in result["JPY/KRW"].items()}

    return result


def fetch_news():
    """
    카테고리별 RSS 피드에서 각각 최신 기사를 수집합니다.
    반환 형태: {"국제": [기사, 기사, 기사], "경제": [...], ...}
    """
    import feedparser
    import re as _re
    from html import unescape

    def strip_html(text):
        """RSS 요약에 섞인 HTML 태그를 제거합니다."""
        clean = _re.sub(r"<[^>]+>", "", text or "")
        return unescape(clean).strip()

    result = {}

    for category, feeds in NEWS_CATEGORIES.items():
        entries = []
        for source_name, url in feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    # 발행 시간 파싱
                    pub = entry.get("published_parsed") or entry.get("updated_parsed")
                    pub_dt = datetime(*pub[:6]) if pub else datetime.now()
                    entries.append({
                        "title":   strip_html(entry.get("title", "")),
                        "link":    entry.get("link", ""),
                        "source":  source_name,
                        "summary": strip_html(entry.get("summary", ""))[:220],
                        "date":    pub_dt.strftime("%Y-%m-%d %H:%M"),
                    })
            except Exception as e:
                print(f"  ✗ [{category}] {source_name} RSS 에러: {e}")

        # 매체가 겹치지 않도록 섞어서 최신순 상위 N개 선택
        entries.sort(key=lambda x: x["date"], reverse=True)
        result[category] = entries[:NEWS_PER_CATEGORY]
        print(f"  ✓ [{category}] {len(result[category])}건 수집")

    return result


# ──────────────────────────────────────────────
# 3. 목업 데이터 생성 (--mock 모드)
# ──────────────────────────────────────────────

def generate_mock_data():
    """재린이 제공한 2026-11-01 기준값을 기반으로 1년치 목업 데이터를 생성합니다."""
    np.random.seed(42)
    end_date = datetime(2026, 11, 1)
    dates = [(end_date - timedelta(days=i)).strftime("%Y-%m-%d")
             for i in range(LOOKBACK_DAYS, -1, -1)]

    # (지표명, 현재값, 일일 변동성(%))
    mock_config = [
        ("KOSPI",       5730,    0.8),
        ("KOSPI200",    899,     0.8),
        ("KOSDAQ",      724,     1.2),
        ("DOW",         52002,   0.7),
        ("NASDAQ",      25437,   1.0),
        ("상해종합",     3599,    0.9),
        ("NIKKEI",      63290,   0.9),
        ("USD/KRW",     1335,    0.3),
        ("EUR/KRW",     1490,    0.4),
        ("CNY/KRW",     200,     0.3),
        ("JPY100/KRW",  847,     0.4),
        ("Gold(원/g)",  171020,  0.6),
        ("WTI($/bbl)",  68.5,    1.5),
        ("BTC(만원)",   10453,   2.5),
        ("US10Y",       4.25,    1.0),
        ("휘발유(원/L)", 1855,   0.2),
    ]

    # 중앙은행 금리 (불연속, 단계적 변경)
    rate_config = {
        "한국": 3.00, "미국": 4.00, "유럽": 2.65, "중국": 3.00, "일본": 1.25,
    }

    result = {}

    for name, current_val, vol_pct in mock_config:
        # 역방향 랜덤 워크로 과거 데이터 생성
        # 현재값에서 시작해 과거로 가면서 변동 추가
        daily_vol = vol_pct / 100
        prices = [current_val]
        for _ in range(len(dates) - 1):
            change = prices[-1] * np.random.normal(0, daily_vol)
            prices.append(prices[-1] - change)  # 역방향이므로 부호 반전
        prices.reverse()  # 과거→현재 순서로 뒤집기

        # 정수형 지표는 반올림
        decimals = 2 if current_val < 100 else 0
        result[name] = {d: round(p, decimals) for d, p in zip(dates, prices)}

    # 중앙은행 금리: 최근 1년간 1~2번 변경된 시뮬레이션
    for name, current in rate_config.items():
        series = {}
        # 간단히: 6개월 전에 0.25%p 인하가 있었다고 가정
        prev_rate = current + 0.25
        change_date = (end_date - timedelta(days=180)).strftime("%Y-%m-%d")
        for d in dates:
            series[d] = prev_rate if d < change_date else current
        result[name] = series

    return result


def generate_mock_news():
    """목업 뉴스 데이터 (카테고리별) — 실제 배포 시 RSS로 대체됩니다."""
    def item(title, source, summary, date):
        return {
            "title": title, "source": source, "summary": summary,
            "date": date, "link": "#",
        }

    return {
        "국제": [
            item("Federal Reserve Holds Rates Steady, Signals Possible Hike in December",
                 "New York Times",
                 "The Federal Reserve kept its benchmark interest rate unchanged, citing persistent inflation pressures across the services sector.",
                 "2026-10-28 14:30"),
            item("ECB Pauses Rate Cuts Amid Stubborn Eurozone Inflation",
                 "The Guardian",
                 "The European Central Bank held its deposit rate at 2.50%, pausing its easing cycle as inflation remains above the 2% target.",
                 "2026-10-29 13:45"),
            item("China Unveils New Stimulus Package Targeting Property Sector",
                 "BBC",
                 "Beijing announced a coordinated package aimed at stabilising housing markets and restoring consumer confidence.",
                 "2026-10-31 09:00"),
        ],
        "경제": [
            item("Global Supply Chains Reroute as Trade Tensions Escalate",
                 "New York Times",
                 "Manufacturers are accelerating shifts away from concentrated production hubs amid renewed tariff threats.",
                 "2026-11-01 08:15"),
            item("Oil Steadies After OPEC+ Signals Output Discipline",
                 "The Guardian",
                 "Crude prices found support as the producer group reiterated its commitment to current production quotas.",
                 "2026-10-31 17:20"),
            item("Semiconductor Exports Post Strongest Quarter in Two Years",
                 "BBC",
                 "Demand from data centre buildouts drove a sharp rebound in advanced chip shipments across Asia.",
                 "2026-10-30 11:05"),
        ],
        "테크": [
            item("AI Infrastructure Spending Reaches New Record Among Hyperscalers",
                 "New York Times",
                 "Capital expenditure guidance from major cloud providers points to sustained buildout through next year.",
                 "2026-11-01 10:40"),
            item("EU Finalises Rules on Foundation Model Transparency",
                 "The Guardian",
                 "Developers will be required to publish training data summaries under the newly agreed framework.",
                 "2026-10-30 15:30"),
            item("Quantum Computing Milestone Claimed by Research Consortium",
                 "BBC",
                 "Researchers reported sustained error correction across a larger qubit array than previously demonstrated.",
                 "2026-10-29 09:50"),
        ],
        "스포츠": [
            item("World Cup Qualifiers Deliver Late Drama Across Three Continents",
                 "BBC Sport",
                 "Several berths remain undecided heading into the final round of fixtures next month.",
                 "2026-11-01 22:10"),
            item("Marathon World Record Falls in Record-Breaking Conditions",
                 "The Guardian",
                 "Cool temperatures and a flat course produced one of the fastest fields in the event's history.",
                 "2026-10-31 12:00"),
            item("NBA Season Opens With Shift Toward Younger Rosters",
                 "New York Times",
                 "Several franchises are leaning on draft picks as veteran contracts come off the books.",
                 "2026-10-30 07:45"),
        ],
        "연예": [
            item("Streaming Platforms Rethink Release Strategy After Theatrical Rebound",
                 "New York Times",
                 "Studios are extending exclusive cinema windows following stronger than expected box office returns.",
                 "2026-11-01 16:25"),
            item("Major Retrospective Opens to Record Advance Ticket Sales",
                 "The Guardian",
                 "The exhibition brings together works that have not been shown together in over four decades.",
                 "2026-10-31 14:00"),
            item("Music Industry Reports Shift in Global Listening Patterns",
                 "BBC",
                 "Non-English language tracks accounted for a growing share of top chart positions this year.",
                 "2026-10-30 18:35"),
        ],
    }


# ──────────────────────────────────────────────
# 4. 데이터 후처리 (주별/월별 리샘플링, 변곡점 탐지)
# ──────────────────────────────────────────────

def resample_data(daily_data, freq="W"):
    """
    일별 데이터를 주별(W) 또는 월별(M)로 리샘플링합니다.
    freq: 'W' (주별) 또는 'M' (월별)
    """
    from collections import defaultdict
    import statistics

    buckets = defaultdict(list)

    for date_str, value in sorted(daily_data.items()):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if freq == "W":
            # ISO 주 시작일 (월요일) 기준으로 그룹화
            week_start = dt - timedelta(days=dt.weekday())
            key = week_start.strftime("%Y-%m-%d")
        else:  # M
            key = dt.strftime("%Y-%m-01")
        buckets[key].append(value)

    # 각 구간의 마지막 값(종가 개념) 사용
    return {k: round(vals[-1], 4) for k, vals in sorted(buckets.items())}


def detect_inflection_points(daily_data, top_n=3):
    """
    시계열에서 일일 변동률이 가장 큰 상위 N개 지점을 찾아 반환합니다.
    변곡점 = 큰 폭의 변동이 발생한 날짜
    """
    sorted_dates = sorted(daily_data.keys())
    changes = []

    for i in range(1, len(sorted_dates)):
        prev_val = daily_data[sorted_dates[i - 1]]
        curr_val = daily_data[sorted_dates[i]]
        if prev_val == 0:
            continue
        pct_change = (curr_val - prev_val) / prev_val * 100
        changes.append({
            "date": sorted_dates[i],
            "value": curr_val,
            "change_pct": round(pct_change, 2),
        })

    # 절대 변동률 기준 상위 N개
    changes.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return changes[:top_n]


# ──────────────────────────────────────────────
# 5. 변곡점 원인 분석 (Claude API + Web Search)
# ──────────────────────────────────────────────

def analyze_inflections(chart_data):
    """
    Claude API에 웹 검색을 붙여서 각 변곡점의 원인을 한 문장으로 분석합니다.
    ANTHROPIC_API_KEY 환경변수가 없으면 건너뜁니다.
    """
    import re
    try:
        import requests as req
    except ImportError:
        print("  ⚠ requests 패키지 없음 → 원인 분석 건너뜀")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ⚠ ANTHROPIC_API_KEY 미설정 → 원인 분석 건너뜀")
        return

    # 분석할 변곡점 수집 (지표당 상위 3개, 총 최대 30개)
    items = []
    for name, info in chart_data.items():
        for pt in info.get("inflections", [])[:3]:
            items.append({
                "indicator": name,
                "date": pt["date"],
                "change_pct": pt["change_pct"],
            })

    if not items:
        return

    # 프롬프트 구성
    lines = [f'- {it["date"]}: {it["indicator"]} {it["change_pct"]:+.2f}%' for it in items]
    prompt = (
        "아래는 경제 지표에서 큰 변동이 발생한 날짜 목록입니다.\n"
        "각 항목에 대해 해당 날짜에 왜 그런 변동이 있었는지 "
        "한국어 15자 이내의 간결한 원인(명사 끝맺음)으로 설명해주세요.\n"
        "예시: 'Fed 기준금리 인상', 'OPEC 감산 합의', '중국 경기부양책 발표'\n\n"
        + "\n".join(lines)
        + "\n\n반드시 아래 JSON 배열 형식으로만 응답하세요 (마크다운 없이):\n"
        '[{"date":"YYYY-MM-DD","indicator":"지표명","reason":"원인"}]'
    )

    print(f"  📡 Claude API로 {len(items)}개 변곡점 원인 분석 중...")

    try:
        resp = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4000,
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()

        # 응답에서 text 블록만 추출
        text_parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        full_text = "\n".join(text_parts)

        # JSON 배열 추출 (```json ... ``` 래핑 대응)
        clean = re.sub(r"```(?:json)?", "", full_text).strip()
        json_match = re.search(r"\[.*\]", clean, re.DOTALL)
        if not json_match:
            print("  ⚠ JSON 파싱 실패 — 응답에서 배열을 찾을 수 없음")
            return

        reasons = json.loads(json_match.group())

        # reason을 chart_data의 inflection에 매핑
        reason_map = {}
        for r in reasons:
            key = f'{r["indicator"]}_{r["date"]}'
            reason_map[key] = r.get("reason", "")

        count = 0
        for name, info in chart_data.items():
            for pt in info.get("inflections", []):
                key = f"{name}_{pt['date']}"
                if key in reason_map and reason_map[key]:
                    pt["reason"] = reason_map[key]
                    count += 1

        print(f"  ✓ {count}개 변곡점에 원인 분석 완료")

    except Exception as e:
        print(f"  ✗ Claude API 호출 실패: {e}")


# ──────────────────────────────────────────────
# 6. HTML 대시보드 생성
# ──────────────────────────────────────────────
def format_value(v):
    """지표 값을 크기에 맞는 소수점 자릿수로 포맷합니다."""
    a = abs(v)
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:,.1f}"
    return f"{v:,.2f}"


def build_html(market_data, news_data, updated_at):
    """수집된 데이터를 Chart.js 기반 HTML 대시보드로 변환합니다."""

    # ── 차트 데이터 준비 (지표별 일별/주별/월별 + 변곡점) ──
    chart_data = {}
    for name, group, color in INDICATORS:
        if name not in market_data:
            continue
        daily = market_data[name]
        chart_data[name] = {
            "group": group,
            "color": color,
            "daily": daily,
            "weekly": resample_data(daily, "W"),
            "monthly": resample_data(daily, "M"),
            "inflections": detect_inflection_points(daily, top_n=5),
        }

    # ── 변곡점 원인 분석 (Claude API) ──
    analyze_inflections(chart_data)

    # ── 지표 레일 HTML (카테고리별 그룹, 현재값 + 등락률 + 스파크라인) ──
    from collections import OrderedDict
    groups_ordered = OrderedDict()
    first_indicator = None

    for name, group, color in INDICATORS:
        if name not in chart_data:
            continue
        if first_indicator is None:
            first_indicator = name

        daily = chart_data[name]["daily"]
        dates = sorted(daily.keys())
        if len(dates) < 2:
            continue
        current = daily[dates[-1]]
        previous = daily[dates[-2]]
        change_pct = ((current - previous) / previous * 100) if previous else 0

        groups_ordered.setdefault(group, []).append({
            "name": name,
            "value": format_value(current),
            "change_pct": round(change_pct, 2),
        })

    rail_html = ""
    for group_label, items in groups_ordered.items():
        rail_html += f'<div class="rail-section"><div class="rail-section-title">{group_label}</div>'
        for it in items:
            selected = " is-selected" if it["name"] == first_indicator else ""
            direction = "up" if it["change_pct"] >= 0 else "down"
            sign = "+" if it["change_pct"] >= 0 else ""
            rail_html += f"""
            <button class="rail-row{selected}" data-name="{it['name']}">
                <span class="rail-name">{it['name']}</span>
                <svg class="rail-spark" data-spark="{it['name']}" viewBox="0 0 64 20" preserveAspectRatio="none"></svg>
                <span class="rail-figures">
                    <span class="rail-value">{it['value']}</span>
                    <span class="rail-change {direction}">{sign}{it['change_pct']}%</span>
                </span>
            </button>"""
        rail_html += '</div>\n'

    # ── 뉴스 HTML (카테고리 탭 + 패널) ──
    news_tabs = ""
    news_panels = ""

    for i, (category, items) in enumerate(news_data.items()):
        is_first = (i == 0)
        active_tab = " is-active" if is_first else ""
        news_tabs += (
            f'<button class="news-tab{active_tab}" data-cat="cat-{i}" '
            f'role="tab" aria-selected="{str(is_first).lower()}">{category}</button>'
        )

        cards = ""
        if not items:
            cards = '<p class="news-empty">불러온 기사가 없습니다.</p>'
        for item in items:
            cards += f"""
            <a class="news-card" href="{item['link']}" target="_blank" rel="noopener">
                <div class="news-meta">
                    <span class="news-source">{item['source']}</span>
                    <time class="news-date">{item['date']}</time>
                </div>
                <h3 class="news-title">{item['title']}</h3>
                <p class="news-summary">{item['summary']}</p>
            </a>"""

        hidden = "" if is_first else " hidden"
        news_panels += (
            f'<div class="news-panel" id="cat-{i}" role="tabpanel"{hidden}>'
            f'<div class="news-grid">{cards}</div></div>'
        )

    # ── 최종 HTML 조립 ──
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>매크로 대시보드</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
/* ═══════════════════════════════════════════
   디자인 토큰
   ═══════════════════════════════════════════ */
:root {{
    color-scheme: light;

    /* 배경 — 화이트 크림 톤 (온기만 살짝 남긴 밝은 오프화이트)
       더 따뜻하게 하려면 --paper를 #F6F2EA 쪽으로,
       더 차갑게 하려면 #FBFBF9 쪽으로 조정하면 됩니다. */
    --paper:        #FAF8F3;
    --surface:      #FFFFFF;
    --surface-sunk: #F2EFE8;

    /* 잉크 — UI의 주 색상 (별도 액센트 색 없음), 온기 있는 먹색 */
    --ink:          #1C1A15;
    --ink-soft:     #6E6659;
    --ink-faint:    #A79F90;

    /* 선 */
    --line:         #EDE8DE;
    --line-strong:  #DBD4C6;

    /* 의미색 — 등락에만 사용 */
    --up:           #1F7A4D;
    --down:         #C03D27;
    --up-bright:    #86D6A8;
    --down-bright:  #F5A18C;

    /* 그림자 — 따뜻한 중성 계열로 아주 옅게 */
    --shadow-sm: 0 1px 2px rgba(82,70,50,0.045);
    --shadow-md: 0 1px 2px rgba(82,70,50,0.045),
                 0 14px 30px -18px rgba(82,70,50,0.18);

    --radius:       9px;
    --radius-lg:    14px;

    --sans: 'IBM Plex Sans KR', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    --mono: 'IBM Plex Mono', ui-monospace, 'SF Mono', monospace;

    padding-top: env(safe-area-inset-top, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
}}

/* 다크 모드 — 뷰어 설정에 따름 */
@media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
        color-scheme: dark;
        --paper:        #15120D;
        --surface:      #1E1A14;
        --surface-sunk: #120F0A;
        --ink:          #F0EADC;
        --ink-soft:     #A99D88;
        --ink-faint:    #786C58;
        --line:         #2E281F;
        --line-strong:  #41392C;
        --up:           #6ECB97;
        --down:         #E8775F;
        --up-bright:    #6ECB97;
        --down-bright:  #E8775F;
        --shadow-sm: 0 1px 2px rgba(0,0,0,0.35);
        --shadow-md: 0 1px 2px rgba(0,0,0,0.35),
                     0 12px 28px -16px rgba(0,0,0,0.7);
    }}
}}

/* ═══════════════════════════════════════════
   기본 리셋
   ═══════════════════════════════════════════ */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

html {{ scroll-padding-top: env(safe-area-inset-top, 0px); }}

body {{
    font-family: var(--sans);
    background: var(--paper);
    color: var(--ink);
    font-size: 14px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
}}

button {{
    font-family: inherit;
    font-size: inherit;
    border: none;
    background: none;
    color: inherit;
    cursor: pointer;
}}

:focus-visible {{
    outline: 2px solid var(--ink);
    outline-offset: 2px;
}}

@media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; animation: none !important; }}
}}

/* ═══════════════════════════════════════════
   레이아웃
   ═══════════════════════════════════════════ */
.shell {{
    max-width: 1240px;
    margin: 0 auto;
    padding: 2.25rem 1.75rem 3.5rem;
}}

/* ── 헤더 ── */
.masthead {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--line-strong);
    margin-bottom: 1.5rem;
}}

.masthead h1 {{
    font-size: 1.0625rem;
    font-weight: 600;
    letter-spacing: -0.015em;
}}

.masthead .stamp {{
    font-family: var(--mono);
    font-size: 0.6875rem;
    color: var(--ink-faint);
    font-variant-numeric: tabular-nums;
}}

/* ── 본문 2단 그리드 ── */
.workspace {{
    display: grid;
    grid-template-columns: 268px 1fr;
    gap: 1.25rem;
    align-items: start;
}}

/* ═══════════════════════════════════════════
   좌측: 지표 레일
   ═══════════════════════════════════════════ */
.rail {{
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    padding: 0.5rem;
    max-height: 616px;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-width: thin;
    scrollbar-color: var(--line-strong) transparent;
}}

.rail::-webkit-scrollbar {{ width: 6px; }}
.rail::-webkit-scrollbar-track {{ background: transparent; }}
.rail::-webkit-scrollbar-thumb {{
    background: var(--line-strong);
    border-radius: 3px;
}}

/* ── 지표 필터 ── */
.rail-filter {{
    position: sticky;
    top: 0;
    z-index: 3;
    background: var(--surface);
    padding: 0.25rem 0.25rem 0.5rem;
}}

.rail-filter input {{
    width: 100%;
    font-family: var(--sans);
    font-size: 0.8125rem;
    color: var(--ink);
    background: var(--surface-sunk);
    border: 1px solid transparent;
    border-radius: var(--radius);
    padding: 0.4375rem 0.6875rem;
    transition: border-color 0.12s ease, background 0.12s ease;
}}

.rail-filter input::placeholder {{ color: var(--ink-faint); }}

.rail-filter input:focus {{
    outline: none;
    background: var(--surface);
    border-color: var(--line-strong);
}}

.rail-section + .rail-section {{ margin-top: 0.375rem; }}

.rail-section[hidden] {{ display: none; }}

.rail-section-title {{
    position: sticky;
    top: 2.625rem;
    z-index: 2;
    font-size: 0.6875rem;
    font-weight: 600;
    color: var(--ink-faint);
    background: var(--surface);
    padding: 0.5rem 0.625rem 0.375rem;
    letter-spacing: 0.02em;
}}

.rail-row {{
    display: grid;
    grid-template-columns: 1fr 58px auto;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0.625rem;
    border-radius: var(--radius);
    text-align: left;
    transition: background 0.14s ease, color 0.14s ease;
}}

.rail-row[hidden] {{ display: none; }}

.rail-row:hover {{ background: var(--surface-sunk); }}

.rail-row.is-selected {{
    background: var(--ink);
    color: var(--paper);
}}

.rail-name {{
    font-size: 0.8125rem;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.rail-spark {{
    width: 58px;
    height: 18px;
    overflow: visible;
    opacity: 0.55;
    transition: opacity 0.14s ease;
}}

.rail-row:hover .rail-spark {{ opacity: 0.9; }}

.rail-spark path {{
    fill: none;
    stroke: currentColor;
    stroke-width: 1.4;
    stroke-linecap: round;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
}}

.rail-row.is-selected .rail-spark {{
    opacity: 0.85;
    color: var(--paper) !important;
}}

.rail-figures {{
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    line-height: 1.3;
}}

.rail-value {{
    font-family: var(--mono);
    font-size: 0.75rem;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
}}

.rail-change {{
    font-family: var(--mono);
    font-size: 0.6875rem;
    font-variant-numeric: tabular-nums;
}}

.rail-change.up   {{ color: var(--up); }}
.rail-change.down {{ color: var(--down); }}

/* 선택된 행에서는 등락색을 밝게 보정 */
.rail-row.is-selected .rail-change.up   {{ color: var(--up-bright); }}
.rail-row.is-selected .rail-change.down {{ color: var(--down-bright); }}

/* ═══════════════════════════════════════════
   우측: 차트 패널
   ═══════════════════════════════════════════ */
.panel {{
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    padding: 1.5rem 1.625rem 1.375rem;
}}

/* ── 선택 지표 수치 리드아웃 ── */
.readout {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1.5rem;
}}

.readout-label {{
    display: flex;
    align-items: center;
    gap: 0.4375rem;
    font-size: 0.8125rem;
    color: var(--ink-soft);
    margin-bottom: 0.3125rem;
}}

/* 지표 색상 점 */
.readout-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
}}

.readout-cat {{
    font-size: 0.6875rem;
    color: var(--ink-faint);
    padding: 0.0625rem 0.375rem;
    border: 1px solid var(--line);
    border-radius: 4px;
}}

.readout-figure {{
    display: flex;
    align-items: baseline;
    gap: 0.625rem;
}}

.readout-value {{
    font-family: var(--mono);
    font-size: 2rem;
    font-weight: 500;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
}}

.readout-change {{
    font-family: var(--mono);
    font-size: 0.875rem;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
}}

.readout-change.up   {{ color: var(--up); }}
.readout-change.down {{ color: var(--down); }}

/* ── 기간 전환 ── */
.period {{
    display: inline-flex;
    background: var(--surface-sunk);
    border-radius: var(--radius);
    padding: 2px;
    gap: 2px;
}}

.period-btn {{
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--ink-soft);
    padding: 0.375rem 0.875rem;
    border-radius: 6px;
    transition: all 0.12s ease;
}}

.period-btn:hover:not(.is-active) {{ color: var(--ink); }}

.period-btn.is-active {{
    background: var(--surface);
    color: var(--ink);
    box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}}

/* ── 차트 캔버스 ── */
.canvas-wrap {{
    position: relative;
    height: 320px;
}}

/* ═══════════════════════════════════════════
   변곡점 분석 목록
   ═══════════════════════════════════════════ */
.inflections {{
    margin-top: 1.25rem;
    padding-top: 1.125rem;
    border-top: 1px solid var(--line);
}}

.inflections-title {{
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--ink-soft);
    margin-bottom: 0.625rem;
}}

.inflection-row {{
    display: grid;
    grid-template-columns: 5.5rem 4.25rem 1fr;
    align-items: baseline;
    gap: 0.75rem;
    padding: 0.5rem 0.5rem;
    margin: 0 -0.5rem;
    border-radius: 6px;
    border-bottom: 1px solid var(--line);
    transition: background 0.12s ease;
}}

.inflection-row:hover {{ background: var(--surface-sunk); }}

.inflection-row:last-child {{ border-bottom: none; }}

.inflection-date {{
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--ink-faint);
    font-variant-numeric: tabular-nums;
}}

.inflection-pct {{
    font-family: var(--mono);
    font-size: 0.75rem;
    font-weight: 600;
    text-align: right;
    font-variant-numeric: tabular-nums;
}}

.inflection-pct.up   {{ color: var(--up); }}
.inflection-pct.down {{ color: var(--down); }}

.inflection-reason {{
    font-size: 0.8125rem;
    color: var(--ink);
}}

.inflection-reason.pending {{
    color: var(--ink-faint);
    font-style: italic;
}}

/* ═══════════════════════════════════════════
   뉴스
   ═══════════════════════════════════════════ */
.headlines {{
    margin-top: 2rem;
}}

.headlines-bar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--line-strong);
    margin-bottom: 1.125rem;
}}

.headlines-bar h2 {{
    font-size: 0.875rem;
    font-weight: 600;
    letter-spacing: -0.01em;
}}

/* ── 카테고리 탭 (밑줄 슬라이드) ── */
.news-tabs {{
    display: flex;
    gap: 0.25rem;
    overflow-x: auto;
    scrollbar-width: none;
    margin-bottom: -0.75rem;
}}

.news-tabs::-webkit-scrollbar {{ display: none; }}

.news-tab {{
    position: relative;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--ink-faint);
    padding: 0.375rem 0.75rem 0.75rem;
    white-space: nowrap;
    transition: color 0.14s ease;
}}

.news-tab:hover {{ color: var(--ink-soft); }}

.news-tab.is-active {{
    color: var(--ink);
    font-weight: 600;
}}

/* 활성 탭 아래 잉크 밑줄 */
.news-tab::after {{
    content: '';
    position: absolute;
    left: 0.75rem;
    right: 0.75rem;
    bottom: -1px;
    height: 2px;
    background: var(--ink);
    border-radius: 1px;
    transform: scaleX(0);
    transition: transform 0.18s ease;
}}

.news-tab.is-active::after {{ transform: scaleX(1); }}

/* ── 뉴스 카드 ── */
.news-panel[hidden] {{ display: none; }}

.news-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.875rem;
}}

.news-card {{
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    padding: 1.125rem 1.25rem 1.25rem;
    text-decoration: none;
    color: inherit;
    transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}}

.news-card:hover {{
    border-color: var(--line-strong);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}}

.news-meta {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.5rem;
    margin-bottom: 0.625rem;
}}

.news-source {{
    font-size: 0.6875rem;
    font-weight: 600;
    color: var(--ink-soft);
    white-space: nowrap;
}}

.news-title {{
    font-size: 0.9375rem;
    font-weight: 600;
    line-height: 1.42;
    letter-spacing: -0.012em;
    margin-bottom: 0.5rem;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}}

.news-summary {{
    font-size: 0.8125rem;
    color: var(--ink-soft);
    line-height: 1.55;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}}

.news-date {{
    font-family: var(--mono);
    font-size: 0.6875rem;
    color: var(--ink-faint);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}}

.news-empty {{
    font-size: 0.8125rem;
    color: var(--ink-faint);
    padding: 1.5rem 0;
}}

/* ── 푸터 ── */
.colophon {{
    margin-top: 2.5rem;
    padding-top: 1rem;
    border-top: 1px solid var(--line);
    font-size: 0.6875rem;
    color: var(--ink-faint);
    text-align: center;
}}

/* ═══════════════════════════════════════════
   반응형
   ═══════════════════════════════════════════ */
@media (max-width: 920px) {{
    .workspace {{ grid-template-columns: 1fr; }}
    .rail {{ max-height: 232px; }}
    .news-grid {{ grid-template-columns: 1fr; }}
}}

@media (max-width: 640px) {{
    .shell {{ padding: 1.5rem 1rem 2.5rem; }}
    .masthead {{ flex-direction: column; gap: 0.25rem; align-items: flex-start; }}
    .panel {{ padding: 1.125rem 1rem 1rem; }}
    .readout-value {{ font-size: 1.625rem; }}
    .canvas-wrap {{ height: 260px; }}
    .inflection-row {{ grid-template-columns: 4.75rem 3.75rem 1fr; gap: 0.5rem; }}
}}
</style>
</head>
<body>
<div class="shell">

    <!-- ══ 헤더 ══ -->
    <header class="masthead">
        <h1>매크로 대시보드</h1>
        <span class="stamp">{updated_at}</span>
    </header>

    <!-- ══ 본문 ══ -->
    <div class="workspace">

        <!-- 좌측: 지표 목록 -->
        <nav class="rail" aria-label="지표 선택">
            <div class="rail-filter">
                <input type="search" id="rail-search" placeholder="지표 검색" aria-label="지표 검색">
            </div>
            {rail_html}
        </nav>

        <!-- 우측: 차트 -->
        <section class="panel">
            <div class="readout">
                <div>
                    <div class="readout-label">
                        <span class="readout-dot" id="ro-dot"></span>
                        <span id="ro-label"></span>
                        <span class="readout-cat" id="ro-cat"></span>
                    </div>
                    <div class="readout-figure">
                        <span class="readout-value" id="ro-value"></span>
                        <span class="readout-change" id="ro-change"></span>
                    </div>
                </div>
                <div class="period" role="group" aria-label="기간">
                    <button class="period-btn is-active" data-period="daily">일별</button>
                    <button class="period-btn" data-period="weekly">주별</button>
                    <button class="period-btn" data-period="monthly">월별</button>
                </div>
            </div>

            <div class="canvas-wrap">
                <canvas id="chart"></canvas>
            </div>

            <div class="inflections">
                <div class="inflections-title">주요 변곡점</div>
                <div id="inflection-list"></div>
            </div>
        </section>

    </div>

    <!-- ══ 뉴스 ══ -->
    <section class="headlines">
        <div class="headlines-bar">
            <h2>오늘의 헤드라인</h2>
            <div class="news-tabs" role="tablist">
                {news_tabs}
            </div>
        </div>
        {news_panels}
    </section>

    <footer class="colophon">
        시장 데이터 Yahoo Finance · 변곡점 분석 Claude · GitHub Actions 자동 빌드
    </footer>

</div>

<script>
/* ═══════════════════════════════════════════
   임베디드 데이터
   ═══════════════════════════════════════════ */
const DATA = {json.dumps(chart_data, ensure_ascii=False)};

/* ═══════════════════════════════════════════
   상태
   ═══════════════════════════════════════════ */
let chart = null;           // Chart.js 인스턴스
let selected = null;        // 현재 선택된 지표명
let period = 'daily';       // daily | weekly | monthly

/* ── CSS 변수 값을 읽어오는 헬퍼 (다크모드 대응) ── */
function token(name) {{
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}}

/* ── 숫자 포맷 (크기에 따라 소수점 자동 조정) ── */
function fmt(v) {{
    const a = Math.abs(v);
    if (a >= 100) return v.toLocaleString('ko-KR', {{maximumFractionDigits: 0}});
    if (a >= 10)  return v.toLocaleString('ko-KR', {{minimumFractionDigits: 1, maximumFractionDigits: 1}});
    return v.toLocaleString('ko-KR', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
}}

/* ═══════════════════════════════════════════
   스파크라인 — 레일 각 행에 월별 추세를 그립니다
   ═══════════════════════════════════════════ */
function drawSparklines() {{
    document.querySelectorAll('.rail-spark').forEach(svg => {{
        const name = svg.dataset.spark;
        const info = DATA[name];
        if (!info) return;

        // 월별 데이터로 간결한 추세선 생성
        const vals = Object.keys(info.monthly).sort().map(d => info.monthly[d]);
        if (vals.length < 2) return;

        const min = Math.min(...vals);
        const max = Math.max(...vals);
        const range = (max - min) || 1;

        // viewBox 64×20 안에 맞춰 좌표 변환 (상하 2px 여백)
        const pts = vals.map((v, i) => {{
            const x = (i / (vals.length - 1)) * 64;
            const y = 18 - ((v - min) / range) * 16;
            return `${{x.toFixed(1)}},${{y.toFixed(1)}}`;
        }});

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M' + pts.join('L'));
        svg.appendChild(path);

        // 지표 고유 색상을 currentColor로 전달 (선택 시 CSS가 흰색으로 덮어씀)
        svg.style.color = info.color;
    }});
}}

/* ═══════════════════════════════════════════
   메인 차트 렌더링
   ═══════════════════════════════════════════ */
function render(name) {{
    const info = DATA[name];
    if (!info) return;
    selected = name;

    const raw = info[period];
    const dates = Object.keys(raw).sort();
    const values = dates.map(d => raw[d]);

    /* ── 수치 리드아웃 업데이트 ── */
    const daily = info.daily;
    const dDates = Object.keys(daily).sort();
    const cur = daily[dDates[dDates.length - 1]];
    const prev = daily[dDates[dDates.length - 2]];
    const pct = prev ? ((cur - prev) / prev * 100) : 0;
    const dir = pct >= 0 ? 'up' : 'down';

    document.getElementById('ro-label').textContent = name;
    document.getElementById('ro-cat').textContent = info.group;
    document.getElementById('ro-dot').style.background = info.color;
    document.getElementById('ro-value').textContent = fmt(cur);
    const chEl = document.getElementById('ro-change');
    chEl.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
    chEl.className = 'readout-change ' + dir;

    /* ── 변곡점 목록 (일별일 때만 차트에 점 표시) ── */
    const inflections = info.inflections || [];
    const listEl = document.getElementById('inflection-list');
    listEl.innerHTML = inflections.map(pt => {{
        const d = pt.change_pct >= 0 ? 'up' : 'down';
        const sign = pt.change_pct >= 0 ? '+' : '';
        const reason = pt.reason
            ? `<span class="inflection-reason">${{pt.reason}}</span>`
            : `<span class="inflection-reason pending">분석 데이터 없음</span>`;
        return `<div class="inflection-row">
            <span class="inflection-date">${{pt.date}}</span>
            <span class="inflection-pct ${{d}}">${{sign}}${{pt.change_pct}}%</span>
            ${{reason}}
        </div>`;
    }}).join('');

    /* ── 차트 다시 그리기 ── */
    if (chart) chart.destroy();

    const color = info.color;
    const inkFaint = token('--ink-faint');
    const line = token('--line');
    const surface = token('--surface');
    const ink = token('--ink');

    // 선 아래 그라디언트 영역
    const ctx = document.getElementById('chart').getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, 320);
    grad.addColorStop(0, color + '26');
    grad.addColorStop(1, color + '00');

    // 변곡점을 별도 scatter 데이터셋으로 추가 (일별에서만)
    const datasets = [{{
        label: name,
        data: dates.map((d, i) => ({{ x: d, y: values[i] }})),
        borderColor: color,
        backgroundColor: grad,
        borderWidth: 1.75,
        pointRadius: 0,
        pointHitRadius: 12,
        tension: 0.25,
        fill: true,
        order: 2,
    }}];

    if (period === 'daily' && inflections.length) {{
        datasets.push({{
            label: '변곡점',
            data: inflections.map(pt => ({{
                x: pt.date, y: pt.value,
                reason: pt.reason || null,
                pct: pt.change_pct,
            }})),
            showLine: false,
            pointRadius: 4,
            pointHoverRadius: 6,
            pointBackgroundColor: inflections.map(
                pt => pt.change_pct >= 0 ? token('--up') : token('--down')),
            pointBorderColor: surface,
            pointBorderWidth: 2,
            order: 1,
        }});
    }}

    chart = new Chart(ctx, {{
        type: 'line',
        data: {{ datasets }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            animation: {{ duration: 250 }},
            interaction: {{ mode: 'nearest', axis: 'x', intersect: false }},
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{
                    backgroundColor: ink,
                    titleColor: surface,
                    bodyColor: surface,
                    padding: 10,
                    cornerRadius: 6,
                    displayColors: false,
                    titleFont: {{ size: 11, family: "'IBM Plex Mono', monospace", weight: '400' }},
                    bodyFont: {{ size: 13, family: "'IBM Plex Mono', monospace", weight: '500' }},
                    callbacks: {{
                        label: function(c) {{
                            // 변곡점 데이터셋이면 원인을 함께 표시
                            if (c.datasetIndex === 1) {{
                                const r = c.raw;
                                const s = r.pct >= 0 ? '+' : '';
                                return r.reason
                                    ? [`${{s}}${{r.pct}}%`, r.reason]
                                    : `${{s}}${{r.pct}}%`;
                            }}
                            return fmt(c.parsed.y);
                        }},
                    }},
                }},
            }},
            scales: {{
                x: {{
                    type: 'time',
                    time: {{
                        unit: period === 'monthly' ? 'month' : period === 'weekly' ? 'week' : 'day',
                        displayFormats: {{ day: 'M/d', week: 'M/d', month: "yy'.'MM" }},
                    }},
                    border: {{ display: false }},
                    grid: {{ display: false }},
                    ticks: {{
                        color: inkFaint,
                        font: {{ size: 10, family: "'IBM Plex Mono', monospace" }},
                        maxTicksLimit: 8,
                        maxRotation: 0,
                    }},
                }},
                y: {{
                    position: 'right',
                    border: {{ display: false }},
                    grid: {{ color: line, drawTicks: false }},
                    ticks: {{
                        color: inkFaint,
                        font: {{ size: 10, family: "'IBM Plex Mono', monospace" }},
                        maxTicksLimit: 6,
                        padding: 8,
                        callback: v => {{
                            if (Math.abs(v) >= 1000000) return (v / 1000000).toFixed(1) + 'M';
                            if (Math.abs(v) >= 10000) return (v / 1000).toFixed(0) + 'k';
                            return v.toLocaleString();
                        }},
                    }},
                }},
            }},
        }},
    }});
}}

/* ═══════════════════════════════════════════
   이벤트 바인딩
   ═══════════════════════════════════════════ */

// 지표 선택
document.querySelectorAll('.rail-row').forEach(row => {{
    row.addEventListener('click', () => {{
        document.querySelectorAll('.rail-row').forEach(r => r.classList.remove('is-selected'));
        row.classList.add('is-selected');
        render(row.dataset.name);
    }});
}});

// 기간 전환
document.querySelectorAll('.period-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('is-active'));
        btn.classList.add('is-active');
        period = btn.dataset.period;
        if (selected) render(selected);
    }});
}});

// 지표 검색 필터 — 입력에 맞는 행만 남기고, 빈 섹션은 숨깁니다
document.getElementById('rail-search').addEventListener('input', (e) => {{
    const q = e.target.value.trim().toLowerCase();

    document.querySelectorAll('.rail-section').forEach(section => {{
        let visible = 0;
        section.querySelectorAll('.rail-row').forEach(row => {{
            const match = !q || row.dataset.name.toLowerCase().includes(q);
            row.hidden = !match;
            if (match) visible++;
        }});
        // 해당 섹션에 보이는 행이 하나도 없으면 섹션 제목까지 숨김
        section.hidden = (visible === 0);
    }});
}});

// 뉴스 카테고리 탭 전환
document.querySelectorAll('.news-tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
        document.querySelectorAll('.news-tab').forEach(t => {{
            t.classList.remove('is-active');
            t.setAttribute('aria-selected', 'false');
        }});
        tab.classList.add('is-active');
        tab.setAttribute('aria-selected', 'true');

        document.querySelectorAll('.news-panel').forEach(p => p.hidden = true);
        const panel = document.getElementById(tab.dataset.cat);
        if (panel) panel.hidden = false;
    }});
}});

// 다크모드 전환 시 차트 색상 갱신
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {{
    if (selected) render(selected);
}});

/* ═══════════════════════════════════════════
   초기 실행
   ═══════════════════════════════════════════ */
drawSparklines();
const first = Object.keys(DATA)[0];
if (first) render(first);
</script>
</body>
</html>"""

    return html


# ──────────────────────────────────────────────
# 6. 메인 실행
# ──────────────────────────────────────────────

def main():
    is_mock = "--mock" in sys.argv
    print("=" * 50)
    print(f"글로벌 매크로 대시보드 빌드 {'(목업 모드)' if is_mock else ''}")
    print("=" * 50)

    # 데이터 수집
    if is_mock:
        print("\n📦 목업 데이터 생성 중...")
        market_data = generate_mock_data()
        news_data = generate_mock_news()
    else:
        print("\n📡 시장 데이터 수집 중...")
        market_data = fetch_market_data()
        print("\n📰 뉴스 수집 중...")
        news_data = fetch_news()

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M KST")

    # HTML 생성
    print("\n🏗  대시보드 HTML 생성 중...")
    html = build_html(market_data, news_data, updated_at)

    # 출력 디렉토리 생성 및 저장
    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"\n✅ 대시보드 생성 완료: {out_path}")
    print(f"   파일 크기: {out_path.stat().st_size / 1024:.1f} KB")
    return str(out_path)


if __name__ == "__main__":
    main()
