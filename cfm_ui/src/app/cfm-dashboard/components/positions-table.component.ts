import { Component, Input } from '@angular/core';

import { BaseStatus, CircuitBreakerStatus, PositionView, Regime } from '../cfm-dashboard.models';

@Component({
  selector: 'app-positions-table',
  templateUrl: './positions-table.component.html',
  styleUrls: ['./positions-table.component.css'],
})
export class PositionsTableComponent {
  @Input({ required: true }) positions: PositionView[] = [];

  regimeTone(regime: Regime): 'green' | 'yellow' | 'red' {
    switch (regime) {
      case Regime.Green:
        return 'green';
      case Regime.Yellow:
        return 'yellow';
      default:
        return 'red';
    }
  }

  baseStatusTone(status: BaseStatus): 'green' | 'yellow' | 'red' {
    switch (status) {
      case BaseStatus.Strong:
        return 'green';
      case BaseStatus.StrongYellow:
        return 'yellow';
      case BaseStatus.DefensiveRed:
      case BaseStatus.CircuitBreakerExit:
        return 'red';
      case BaseStatus.WeakBase:
      default:
        return 'yellow';
    }
  }

  circuitBreakerTone(status: CircuitBreakerStatus): 'green' | 'yellow' | 'red' {
    switch (status) {
      case CircuitBreakerStatus.Exit:
        return 'red';
      case CircuitBreakerStatus.Warning:
        return 'yellow';
      default:
        return 'green';
    }
  }

  weeklyTargetLabel(value: number | null): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return `${value.toFixed(1)}%`;
  }
}
