# SKAX Climate Physical Risk Analysis Service - Frontend

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/skax/climate-risk-frontend)
[![Vue](https://img.shields.io/badge/vue-3.5.22-green.svg)](https://vuejs.org/)
[![TypeScript](https://img.shields.io/badge/typescript-5.9.0-blue.svg)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

**사업장별 기후 물리적 리스크 분석 서비스 - 웹 애플리케이션**

기준일 : 25-12-18 (목)

SKAX의 기후 물리적 리스크 분석 서비스 프론트엔드는 Vue 3와 TypeScript 기반의 현대적인 웹 애플리케이션으로, 사업장별 기후 리스크 데이터를 직관적으로 시각화하고 분석할 수 있습니다.

## 핵심 기능

### 주요 페이지

**대시보드**

- 전체 사업장 리스크 현황 한눈에 파악
- 리스크 히트맵 시각화
- 주요 지표 카드
- 최근 분석 결과 요약

**사업장 분석**

- SSP 시나리오별 리스크 분석
- 재해 유형별 영향도 평가
- 재무 영향 분석 (손실률, 예상 손실액)
- 취약성 평가 (자산 연령, 적응 조치 등)
- 시계열 데이터 차트

**시뮬레이션**

- 기후 시나리오 시뮬레이션
- 위치 기반 리스크 예측
- 자산 취약성 분석
- TCFD 시나리오 분석
- 재무 영향 시뮬레이션

**리포트 관리**

- 분석 결과 리포트 생성
- ESG 보고서 작성
- TCFD 공시 자료 생성
- 데이터 내보내기 (JSON, CSV)

**사업장 관리**

- 사업장 등록/수정/삭제
- 위치 정보 관리
- 자산 정보 관리
- 산업 분류 설정

### 기술 스택

**프레임워크 & 라이브러리**

- Vue 3.5.22 (Composition API)
- TypeScript 5.9.0
- Vue Router 4.6.3 (라우팅)
- Pinia 3.0.3 (상태 관리)

**UI & 스타일**

- Tailwind CSS 4.1.17
- shadcn-vue 2.3.2 (UI 컴포넌트)
- Radix Vue 1.9.17 (헤드리스 컴포넌트)
- Lucide Vue Next (아이콘)

**데이터 시각화**

- Chart.js 4.5.1
- Vue ChartJS 5.3.3

**개발 도구**

- Vite 7.1.11 (빌드 도구)
- ESLint 9.37.0 (코드 린팅)
- Prettier 3.6.2 (코드 포맷팅)
- Vue DevTools 8.0.3

## 세팅 가이드

### 요구사항

- Node.js 20.19.0 이상 또는 22.12.0 이상
- npm 또는 pnpm

### 설치

```bash
# 1. 저장소 클론
git clone https://github.com/skax/climate-risk-frontend.git
cd climate-risk-frontend

# 2. 의존성 설치
npm install
# 또는
pnpm install

# 3. 개발 서버 실행
npm run dev
# 또는
pnpm dev
```

### 빌드 및 배포

```bash
# 타입 체크
npm run type-check

# 프로덕션 빌드
npm run build

# 빌드 미리보기
npm run preview
```

### 개발 환경 설정

```bash
# 코드 린팅
npm run lint

# 코드 포맷팅
npm run format
```

---

## 아키텍처

### 애플리케이션 구조

| 레이어 | 구성 요소 | 설명 |
| --- | --- | --- |
| **Core** | Router | Vue Router 기반 페이지 라우팅 |
| | State (Pinia) | auth, sites, ui 스토어 |
| **Views** | Dashboard | 대시보드 페이지 |
| | Analysis | 사업장 분석 페이지 |
| | Simulation | 시뮬레이션 페이지 |
| | Report | 리포트 페이지 |
| | SiteManagement | 사업장 관리 페이지 |
| | MyAccount | 계정 관리 페이지 |
| **Components** | Charts | 차트 컴포넌트 (Chart.js) |
| | Analysis Tabs | 분석 탭 컴포넌트 |
| | Simulation | 시뮬레이션 컴포넌트 |
| | UI (shadcn) | 공통 UI 컴포넌트 |
| | Common | Header, OnboardingLayout 등 |
| **Backend** | FastAPI | Climate Risk Analysis API |

### 상태 관리 (Pinia Stores)

- **authStore**: 사용자 인증 및 로그인 상태 관리
- **sitesStore**: 사업장 데이터 관리
- **uiStore**: UI 상태 및 페이지 네비게이션 관리

## 주요 화면

### 대시보드

- 전체 사업장 리스크 현황
- 리스크 레벨별 사업장 분포 (Low, Medium, High, Critical)
- 지역별 리스크 히트맵
- 최근 분석 결과 타임라인

### 사업장 분석

#### 개요 탭

- 사업장 기본 정보
- 종합 리스크 점수
- SSP 시나리오별 리스크 비교
- 주요 위험 요인

#### 재해 탭

- 재해 유형별 영향도 (홍수, 태풍, 폭염, 한파, 가뭄 등)
- 과거 재해 이력
- 예상 재해 빈도

#### 재무 탭

- 예상 손실액
- 손실률 (%)
- 시나리오별 재무 영향 비교
- 재무 리스크 차트

#### 취약성 탭

- 자산 연령 및 상태
- 적응 조치 현황
- 취약성 점수
- 개선 권장 사항

---

## 프로젝트 구조

```
frontend/new/
├── src/                           # 소스 코드
│   ├── main.ts                    # 애플리케이션 진입점
│   ├── App.vue                    # 루트 컴포넌트
│   ├── router/
│   │   └── index.ts               # 라우터 설정
│   ├── store/                     # Pinia 상태 관리
│   │   ├── auth.ts                # 인증 상태
│   │   ├── sites.ts               # 사업장 데이터
│   │   └── ui.ts                  # UI 상태
│   ├── views/                     # 페이지 컴포넌트
│   │   ├── LoginView.vue          # 로그인 페이지
│   │   ├── SignupView.vue         # 회원가입 페이지
│   │   ├── DashboardView.vue      # 대시보드
│   │   ├── AnalysisView.vue       # 사업장 분석
│   │   ├── SiteDetailView.vue     # 사업장 상세
│   │   ├── SimulationView.vue     # 시뮬레이션
│   │   ├── ReportView.vue         # 리포트
│   │   ├── SiteManagementView.vue # 사업장 관리
│   │   └── MyAccountView.vue      # 계정 관리
│   ├── components/                # 공유 컴포넌트
│   │   ├── common/                # 공통 컴포넌트
│   │   │   ├── Header.vue         # 헤더
│   │   │   └── OnboardingModal.vue # 온보딩 모달
│   │   ├── charts/                # 차트 컴포넌트
│   │   │   ├── RiskChart.vue      # 리스크 차트
│   │   │   ├── RiskHeatmap.vue    # 히트맵
│   │   │   ├── ESGRadar.vue       # ESG 레이더 차트
│   │   │   └── EmissionChart.vue  # 배출량 차트
│   │   ├── analysis/              # 분석 탭 컴포넌트
│   │   │   ├── AnalysisOverviewTab.vue
│   │   │   ├── AnalysisFinancialTab.vue
│   │   │   └── AnalysisVulnerabilityTab.vue
│   │   ├── simulation/            # 시뮬레이션 컴포넌트
│   │   │   ├── ClimateSimulation.vue
│   │   │   ├── LocationSimulation.vue
│   │   │   ├── TCFDScenario.vue
│   │   │   └── FinancialImpact.vue
│   │   └── ui/                    # UI 라이브러리 (shadcn-vue)
│   │       ├── button/
│   │       └── dialog/
│   ├── assets/                    # 정적 자산
│   │   ├── css/
│   │   │   └── tailwind.css       # Tailwind CSS
│   │   └── data/
│   │       └── sites.ts           # 사업장 데이터
│   └── lib/
│       └── utils.ts               # 유틸리티 함수
├── public/                        # 공개 정적 파일
│   └── favicon.ico
├── docs/                          # 문서
│   └── todo.md                    # TODO 리스트
├── package.json                   # 프로젝트 설정 및 의존성
├── vite.config.ts                 # Vite 설정
├── tsconfig.json                  # TypeScript 설정
├── tailwind.config.js             # Tailwind CSS 설정
├── eslint.config.ts               # ESLint 설정
└── README.md                      # 이 파일
```

## 주요 기능 상세

### 인증 및 사용자 관리

- 로그인/회원가입
- 비밀번호 찾기
- 계정 정보 수정
- 계정 삭제
- 최초 로그인 온보딩

### 라우트 구조

| 경로               | 컴포넌트           | 설명          | 인증 필요 |
| ------------------ | ------------------ | ------------- | --------- |
| `/`                | DashboardView      | 대시보드      | 불필요    |
| `/login`           | LoginView          | 로그인        | 불필요    |
| `/signup`          | SignupView         | 회원가입      | 불필요    |
| `/forgot-password` | ForgotPasswordView | 비밀번호 찾기 | 불필요    |
| `/analysis`        | AnalysisView       | 사업장 분석   | 필요      |
| `/site-detail`     | SiteDetailView     | 사업장 상세   | 필요      |
| `/simulation`      | SimulationView     | 시뮬레이션    | 필요      |
| `/report`          | ReportView         | 리포트 관리   | 필요      |
| `/site-management` | SiteManagementView | 사업장 관리   | 필요      |
| `/my-account`      | MyAccountView      | 내 계정       | 필요      |

### 데이터 모델

```typescript
interface Site {
  id: string
  name: string
  location: {
    latitude: number
    longitude: number
    address: string
  }
  industryCode: string
  facilityType: string
  assetValue: number
  assetAge: number
  riskLevel: 'Low' | 'Medium' | 'High' | 'Critical'
  // ... 기타 필드
}
```

---

## 개발 가이드

### 새로운 페이지 추가하기

1. `src/views/` 디렉토리에 새로운 Vue 컴포넌트 생성
2. `src/router/index.ts`에 라우트 추가
3. 필요한 경우 `src/store/ui.ts`에 페이지 타입 추가

```typescript
// 1. src/views/NewPageView.vue 생성
<script setup lang="ts">
// 페이지 로직
</script>

<template>
  <!-- 페이지 UI -->
</template>

// 2. src/router/index.ts에 라우트 추가
{
  path: '/new-page',
  name: 'new-page',
  component: NewPageView,
  meta: { requiresAuth: true },
}
```

### 새로운 컴포넌트 추가하기

```bash
# UI 컴포넌트 추가 (shadcn-vue)
npx shadcn-vue@latest add [component-name]

# 예시
npx shadcn-vue@latest add card
npx shadcn-vue@latest add table
```

### 상태 관리 사용하기

```typescript
// 컴포넌트에서 store 사용
import { useAuthStore } from '@/store/auth'
import { useSitesStore } from '@/store/sites'

const authStore = useAuthStore()
const sitesStore = useSitesStore()

// 상태 읽기
console.log(authStore.isLoggedIn)
console.log(sitesStore.allSites)

// 액션 호출
authStore.handleLogin(email, password)
```

## 테스트 계정

개발 환경에서 사용할 수 있는 테스트 계정:

- **이메일**: `user@sk.ax`
- **비밀번호**: `user123`

## 성능 최적화

- **빌드 최적화**: Vite 기반 빠른 HMR (Hot Module Replacement)
- **코드 분할**: Vue Router 기반 자동 코드 스플리팅
- **트리 쉐이킹**: 미사용 코드 자동 제거
- **타입 안정성**: TypeScript를 통한 컴파일 타임 에러 검증

## 트러블슈팅

### 개발 서버가 시작되지 않는 경우

```bash
# node_modules 삭제 후 재설치
rm -rf node_modules package-lock.json
npm install

# 또는 캐시 정리 후 재시작
npm run dev -- --force
```

### 타입 에러가 발생하는 경우

```bash
# TypeScript 컴파일러 재실행
npm run type-check

# VSCode에서 TypeScript 서버 재시작
# Cmd/Ctrl + Shift + P -> "TypeScript: Restart TS Server"
```

### 빌드 에러가 발생하는 경우

```bash
# dist 폴더 삭제 후 재빌드
rm -rf dist
npm run build
```

## 버전 히스토리

### v1.0.0 (2025-11-13)

- 초기 릴리스
- Vue 3 + TypeScript 기반 웹 애플리케이션
- Chart.js 기반 데이터 시각화
- shadcn-vue + Tailwind CSS UI 시스템
- 인증 시스템 (로그인/회원가입)
- 반응형 디자인
- 대시보드, 분석, 시뮬레이션, 리포트 페이지
- Pinia 기반 상태 관리
- Vite 빌드 시스템

## 기술 스택 및 라이브러리

- [Vue.js](https://vuejs.org/) - 프로그레시브 JavaScript 프레임워크
- [TypeScript](https://www.typescriptlang.org/) - JavaScript의 타입 안전성 강화
- [Vite](https://vitejs.dev/) - 차세대 프론트엔드 빌드 도구
- [Tailwind CSS](https://tailwindcss.com/) - 유틸리티 우선 CSS 프레임워크
- [shadcn-vue](https://www.shadcn-vue.com/) - 재사용 가능한 Vue 컴포넌트
- [Chart.js](https://www.chartjs.org/) - JavaScript 차트 라이브러리
- [Pinia](https://pinia.vuejs.org/) - Vue 상태 관리
