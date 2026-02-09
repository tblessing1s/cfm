import {
  BaseStatus,
  CircuitBreakerStatus,
  CircuitBreakers,
  Position,
  Regime,
} from './cfm-dashboard.models';

export interface BaseStatusThresholds {
  dteMin: number;
  deltaMin: number;
}

export const computeCircuitBreakerStatus = (cb: CircuitBreakers): CircuitBreakerStatus => {
  const warningHit = cb.cb_8_21_cross || cb.cb_price_below_50 || cb.cb_drop_15_from_run_high;
  const exitHit =
    cb.cb_below_50_2_closes ||
    cb.cb_price_below_200 ||
    cb.cb_50_below_200 ||
    cb.cb_drop_20_from_run_high;

  if (exitHit) {
    return CircuitBreakerStatus.Exit;
  }

  if (warningHit) {
    return CircuitBreakerStatus.Warning;
  }

  return CircuitBreakerStatus.Ok;
};

export const computeBaseStatus = (pos: Position, thresholds: BaseStatusThresholds): BaseStatus => {
  const circuitBreakerStatus = computeCircuitBreakerStatus(pos.circuitBreakers);
  const longDteOk = pos.longDte >= thresholds.dteMin;
  const longDeltaOk = pos.longDelta >= thresholds.deltaMin;

  if (circuitBreakerStatus === CircuitBreakerStatus.Exit) {
    return BaseStatus.CircuitBreakerExit;
  }

  if (!longDteOk || !longDeltaOk) {
    return BaseStatus.WeakBase;
  }

  if (pos.regime === Regime.Green) {
    return BaseStatus.Strong;
  }

  if (pos.regime === Regime.Yellow) {
    return BaseStatus.StrongYellow;
  }

  return BaseStatus.DefensiveRed;
};
