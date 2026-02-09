import assert from 'assert';

import { computeBaseStatus, computeCircuitBreakerStatus } from '../src/app/cfm-dashboard/cfm-dashboard.utils';
import { BaseStatus, CircuitBreakerStatus, Position, Regime } from '../src/app/cfm-dashboard/cfm-dashboard.models';

const thresholds = { dteMin: 120, deltaMin: 0.7 };

const basePosition: Position = {
  ticker: 'AAPL',
  regime: Regime.Green,
  longDte: 160,
  longDelta: 0.75,
  circuitBreakers: {
    cb_8_21_cross: false,
    cb_price_below_50: false,
    cb_drop_15_from_run_high: false,
    cb_below_50_2_closes: false,
    cb_price_below_200: false,
    cb_50_below_200: false,
    cb_drop_20_from_run_high: false,
  },
};

const warningPosition: Position = {
  ...basePosition,
  circuitBreakers: {
    ...basePosition.circuitBreakers,
    cb_price_below_50: true,
  },
};

const exitPosition: Position = {
  ...basePosition,
  circuitBreakers: {
    ...basePosition.circuitBreakers,
    cb_price_below_200: true,
  },
};

assert.equal(
  computeCircuitBreakerStatus(basePosition.circuitBreakers),
  CircuitBreakerStatus.Ok,
  'Expected OK when no circuit breakers are hit.'
);

assert.equal(
  computeCircuitBreakerStatus(warningPosition.circuitBreakers),
  CircuitBreakerStatus.Warning,
  'Expected WARNING when a warning circuit breaker is hit.'
);

assert.equal(
  computeCircuitBreakerStatus(exitPosition.circuitBreakers),
  CircuitBreakerStatus.Exit,
  'Expected EXIT when an exit circuit breaker is hit.'
);

assert.equal(
  computeBaseStatus(basePosition, thresholds),
  BaseStatus.Strong,
  'Expected STRONG when Green with sufficient DTE/delta and CB OK.'
);

assert.equal(
  computeBaseStatus({ ...basePosition, regime: Regime.Yellow }, thresholds),
  BaseStatus.StrongYellow,
  'Expected STRONG (YELLOW) when Yellow with sufficient DTE/delta and CB OK.'
);

assert.equal(
  computeBaseStatus({ ...basePosition, regime: Regime.Red }, thresholds),
  BaseStatus.DefensiveRed,
  'Expected DEFENSIVE (RED) when Red with sufficient DTE/delta and CB OK.'
);

assert.equal(
  computeBaseStatus({ ...basePosition, longDelta: 0.6 }, thresholds),
  BaseStatus.WeakBase,
  'Expected WEAK BASE when long delta is below threshold.'
);

assert.equal(
  computeBaseStatus(exitPosition, thresholds),
  BaseStatus.CircuitBreakerExit,
  'Expected CIRCUIT BREAKER — EXIT to override other conditions.'
);

console.log('CFM dashboard utils tests passed.');
