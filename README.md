# 📊 글로벌 매크로 대시보드

매일 자동으로 업데이트되는 거시경제 지표 대시보드입니다.  
GitHub Actions가 매일 KST 07:00에 실행되어 최신 데이터를 수집하고 GitHub Pages로 배포합니다.

## 포함 지표

| 카테고리 | 지표 |
|---------|------|
| 증시 | KOSPI, KOSPI200, KOSDAQ, DOW, NASDAQ, 상해종합, NIKKEI |
| 환율 | USD/KRW, EUR/KRW, CNY/KRW, JPY(100엔)/KRW |
| 금리 | 한국, 미국, 유럽, 중국, 일본 기준금리 |
| 기타 | Gold(원/g), WTI($/bbl), Bitcoin(원), 휘발유(원/L) |
| 뉴스 | 국제 · 경제 · 테크 · 스포츠 · 연예 (카테고리별 3건) |

## 기능

- **일별 / 주별 / 월별** 기간 전환
- **변곡점 자동 탐지** — 큰 변동 발생 시점에 주석 표시
- **정규화 뷰** — 증시 탭에서 100 기준 비교 가능
- **반응형** — 모바일에서도 깔끔하게 표시

## 설정 방법

### 1. 저장소 생성 & 파일 업로드

```bash
# 새 GitHub 저장소를 만들고 이 폴더의 파일을 모두 push
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/macro-dashboard.git
git push -u origin main
```

### 2. GitHub Pages 활성화

1. 저장소 → **Settings** → **Pages**
2. Source: **GitHub Actions** 선택
3. 저장

### 3. Actions 권한 확인

1. 저장소 → **Settings** → **Actions** → **General**
2. "Workflow permissions" → **Read and write permissions** 체크
3. 저장

### 4. 첫 빌드 실행

1. 저장소 → **Actions** 탭
2. "Update Macro Dashboard" 워크플로우 선택
3. **Run workflow** 버튼 클릭

빌드 완료 후 `https://YOUR_USERNAME.github.io/macro-dashboard/` 에서 확인 가능합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
python build_dashboard.py          # 실제 데이터
python build_dashboard.py --mock   # 목업 데이터 (테스트용)
# → docs/index.html 생성
```

## 코드 구조

`build_dashboard.py` 한 파일에 번호순 섹션으로 정리되어 있습니다.

| 섹션 | 역할 |
|------|------|
| 1. 설정 | `TICKERS`, `INDICATORS`, `NEWS_FEEDS`, `LOOKBACK_DAYS` |
| 2. 데이터 수집 | `fetch_market_data()`, `fetch_news()` |
| 3. 목업 데이터 | `generate_mock_data()` — 테스트용 |
| 4. 후처리 | `resample_data()`, `detect_inflection_points()` |
| 5. 변곡점 분석 | `analyze_inflections()` — Claude API + 웹 검색 |
| 6. HTML 생성 | `build_html()` — CSS 토큰 → 레이아웃 → JS |

## 확장 포인트

**지표 추가** — `TICKERS`에 yfinance 티커를, `INDICATORS`에 `(이름, 카테고리, 색상)`을 추가하면 끝입니다. 레일·차트·스파크라인이 자동으로 따라옵니다.

**새 카테고리 추가** — `INDICATORS`의 두 번째 항목에 새 카테고리명을 쓰면 레일에 섹션이 자동 생성됩니다.

**색상 / 간격 / 타이포 변경** — `build_html()` 안의 `:root` CSS 변수 블록만 수정하면 전체에 반영됩니다. 다크모드 값은 바로 아래 `@media (prefers-color-scheme: dark)` 블록에 있습니다.

**뉴스 카테고리 추가** — `NEWS_CATEGORIES`에 `"카테고리명": [(매체명, RSS URL), ...]`을 추가하면 탭이 자동 생성됩니다. 카테고리당 표시 건수는 `NEWS_PER_CATEGORY`로 조정합니다.

**분석 프롬프트 수정** — `analyze_inflections()` 안의 `prompt` 변수. 현재는 15자 이내 원인을 JSON으로 받습니다.

## 설계 메모

- 지표 선택 UI와 요약 수치를 **하나의 레일**로 통합했습니다 (별도 요약 카드 없음)
- 차트에는 변곡점 **점만** 찍고, 원인 텍스트는 **차트 아래 목록**으로 분리해 겹침을 없앴습니다
- 액센트 색 없이 **잉크 블랙**으로 선택 상태를 표현하고, 채도는 데이터 선에만 사용합니다
- 외부 의존성은 Chart.js + 날짜 어댑터 2개뿐입니다 (어노테이션 플러그인 제거)
- 레일 상단 검색창으로 지표를 필터링할 수 있고, 카테고리 헤더는 스크롤 시 고정됩니다
- 스파크라인은 각 지표 고유 색상을 쓰되 투명도를 낮춰 배경 역할만 합니다
- 뉴스는 카테고리 탭으로 분리해 한 번에 3건씩만 노출합니다

## 데이터 출처

- 시장 데이터: [Yahoo Finance](https://finance.yahoo.com/) (via yfinance)
- 뉴스: NYT, Reuters, BBC, The Guardian RSS
