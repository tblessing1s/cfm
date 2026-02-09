import { BaseStatus, CircuitBreakerStatus, Regime } from './cfm-dashboard.models';

// README: update these thresholds to adjust Base Status sensitivity.
export const DEFAULT_BASE_THRESHOLDS = {
  dteMin: 120,
  deltaMin: 0.7,
};

export const BASE_STATUS_DEFINITIONS: { label: BaseStatus; description: string }[] = [
  {
    label: BaseStatus.CircuitBreakerExit,
    description: 'Circuit breaker status is EXIT. Immediate exit posture.',
  },
  {
    label: BaseStatus.WeakBase,
    description: 'Long DTE or long delta is below minimums and CB is not EXIT.',
  },
  {
    label: BaseStatus.Strong,
    description: 'Regime Green with DTE and delta above minimums and CB not EXIT.',
  },
  {
    label: BaseStatus.StrongYellow,
    description: 'Regime Yellow with DTE and delta above minimums and CB not EXIT.',
  },
  {
    label: BaseStatus.DefensiveRed,
    description: 'Regime Red with DTE and delta above minimums and CB not EXIT.',
  },
];

export const CIRCUIT_BREAKER_QUESTIONS: {
  key: string;
  label: string;
  meaning: string;
  level: 'warning' | 'exit';
}[] = [
  {
    key: 'cb_8_21_cross',
    label: '8/21 EMA cross',
    meaning: 'Momentum signal turning down.',
    level: 'warning',
  },
  {
    key: 'cb_price_below_50',
    label: 'Price below 50D',
    meaning: 'Early weakness below 50-day average.',
    level: 'warning',
  },
  {
    key: 'cb_drop_15_from_run_high',
    label: 'Drop 15% from run high',
    meaning: 'Drawdown trigger from run high.',
    level: 'warning',
  },
  {
    key: 'cb_below_50_2_closes',
    label: 'Below 50D (2 closes)',
    meaning: 'Escalation: 2 closes below 50-day.',
    level: 'exit',
  },
  {
    key: 'cb_price_below_200',
    label: 'Price below 200D',
    meaning: 'Immediate exit trigger.',
    level: 'exit',
  },
  {
    key: 'cb_50_below_200',
    label: '50D below 200D',
    meaning: 'Immediate exit trigger.',
    level: 'exit',
  },
  {
    key: 'cb_drop_20_from_run_high',
    label: 'Drop 20% from run high',
    meaning: 'Immediate exit drawdown.',
    level: 'exit',
  },
];

export const WEEKLY_TARGET_BY_REGIME: Record<Regime, number | null> = {
  [Regime.Green]: 1.5,
  [Regime.Yellow]: 1.5,
  [Regime.Red]: 1.0,
};

export const CIRCUIT_BREAKER_STATUS_LABELS: Record<CircuitBreakerStatus, string> = {
  [CircuitBreakerStatus.Ok]: 'OK',
  [CircuitBreakerStatus.Warning]: 'WARNING',
  [CircuitBreakerStatus.Exit]: 'EXIT',
};
