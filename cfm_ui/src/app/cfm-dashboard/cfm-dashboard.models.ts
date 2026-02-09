export enum Regime {
  Green = 'Green',
  Yellow = 'Yellow',
  Red = 'Red',
}

export enum CircuitBreakerStatus {
  Ok = 'OK',
  Warning = 'WARNING',
  Exit = 'EXIT',
}

export enum BaseStatus {
  Strong = 'STRONG',
  StrongYellow = 'STRONG (YELLOW)',
  DefensiveRed = 'DEFENSIVE (RED)',
  WeakBase = 'WEAK BASE',
  CircuitBreakerExit = 'CIRCUIT BREAKER — EXIT',
}

export interface CircuitBreakers {
  cb_8_21_cross: boolean;
  cb_price_below_50: boolean;
  cb_drop_15_from_run_high: boolean;
  cb_below_50_2_closes: boolean;
  cb_price_below_200: boolean;
  cb_50_below_200: boolean;
  cb_drop_20_from_run_high: boolean;
}

export interface Position {
  ticker: string;
  regime: Regime;
  longDte: number;
  longDelta: number;
  circuitBreakers: CircuitBreakers;
  realizedNetJuiceWtd?: number;
}

export interface PositionView extends Position {
  circuitBreakerStatus: CircuitBreakerStatus;
  baseStatus: BaseStatus;
  weeklyTargetPct: number | null;
}

export interface AccountSummary {
  cashBalance: number;
  openShortPremiumTotal: number;
  longInitialCostTotal: number;
  weeklyGoalDollars: number;
  realizedNetJuiceWtd: number;
}
