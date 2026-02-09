import { Injectable } from '@angular/core';
import { forkJoin, map, Observable } from 'rxjs';

import {
  AccountOption,
  BusinessDashboard,
  BaseLeg,
  LedgerRow,
  MinimalPositionStatus,
  PositionMetrics,
  DashboardService,
} from '../services/dashboard.service';
import { AccountSummary, CircuitBreakers, Position, Regime } from './cfm-dashboard.models';
import { buildLedgerSummaries } from '../utils/ledger-utils';

interface DashboardPayload {
  summary: AccountSummary;
  positions: Position[];
}

@Injectable({ providedIn: 'root' })
export class CfmDashboardService {
  constructor(private readonly dashboardService: DashboardService) {}

  getAccounts(): Observable<AccountOption[]> {
    return this.dashboardService.getAccounts();
  }

  loadDashboard(account?: string): Observable<DashboardPayload> {
    return forkJoin({
      business: this.dashboardService.getBusinessDashboard(account),
      minimal: this.dashboardService.getMinimalPositionStatus(account),
      metrics: this.dashboardService.listPositionMetrics(account),
      baseLegs: this.dashboardService.listBaseLegs(),
      ledger: this.dashboardService.getLedger(account),
    }).pipe(
      map(({ business, minimal, metrics, baseLegs, ledger }) => {
        const positions = this.mapPositions(minimal, metrics);
        return {
          summary: this.mapSummary(business, minimal, metrics, baseLegs, ledger),
          positions,
        };
      })
    );
  }

  private mapSummary(
    business: BusinessDashboard,
    minimal: MinimalPositionStatus[],
    metrics: PositionMetrics[],
    baseLegs: BaseLeg[],
    ledger: LedgerRow[]
  ): AccountSummary {
    const weeklyGoalDollars = this.computeWeeklyGoalFromBaseLegs(baseLegs, ledger);

    return {
      cashBalance: business.nav_cash ?? 0,
      openShortPremiumTotal: this.computeOpenShortPremiumTotal(ledger, baseLegs),
      longInitialCostTotal: business.account_summary?.principal_cost ?? 0,
      weeklyGoalDollars,
      realizedNetJuiceWtd: business.consistency_avg_weekly_juice ?? 0,
    };
  }

  private mapPositions(minimal: MinimalPositionStatus[], metrics: PositionMetrics[]): Position[] {
    const metricsBySymbol = new Map(
      metrics.map((row) => [row.position.symbol.toUpperCase(), row])
    );

    return minimal.map((row) => {
      const symbol = row.symbol.toUpperCase();
      const metric = metricsBySymbol.get(symbol);
      const circuitBreakers = this.mapCircuitBreakers(metric);
      return {
        ticker: symbol,
        regime: this.normalizeRegime(row.stock_regime),
        longDte: row.long_dte_days ?? 0,
        longDelta: row.long_delta ?? 0,
        realizedNetJuiceWtd: row.weekly_net_income_avg ?? row.net_juice_current_month ?? undefined,
        circuitBreakers,
      };
    });
  }

  private normalizeRegime(value: string | null | undefined): Regime {
    const normalized = (value || '').toUpperCase();
    if (normalized === 'GREEN') {
      return Regime.Green;
    }
    if (normalized === 'RED') {
      return Regime.Red;
    }
    return Regime.Yellow;
  }

  private mapCircuitBreakers(metric?: PositionMetrics): CircuitBreakers {
    const reasons = new Set((metric?.circuit_breaker_reasons || []).map((r) => r.toUpperCase()));
    const status = (metric?.circuit_breaker_status || '').toUpperCase();

    const circuitBreakers: CircuitBreakers = {
      cb_8_21_cross: reasons.has('S_8<21'),
      cb_price_below_50: reasons.has('S_<50'),
      cb_drop_15_from_run_high: false,
      cb_below_50_2_closes: reasons.has('S_HARD_2D'),
      cb_price_below_200: reasons.has('S_<200'),
      cb_50_below_200: false,
      cb_drop_20_from_run_high: reasons.has('S_CATA'),
    };

    if (status === 'EXITNOW') {
      circuitBreakers.cb_price_below_200 = true;
    } else if (status === 'EXITCANDIDATE') {
      circuitBreakers.cb_below_50_2_closes = true;
    }

    return circuitBreakers;
  }

  private computeWeeklyGoalFromBaseLegs(baseLegs: BaseLeg[], ledger: LedgerRow[]): number {
    const markLegIds = new Set(
      baseLegs
        .filter((leg) => (leg.tag || '').toUpperCase() === 'MARK')
        .map((leg) => (leg.base_leg_id || '').toString().trim())
        .filter(Boolean)
    );
    const weeklyRate = 0.015;
    const contractMultiplier = 100;
    return baseLegs.reduce((total, leg) => {
      if ((leg.instrument_type || '').toUpperCase() !== 'LONG_OPTION') {
        return total;
      }
      if ((leg.tag || '').toUpperCase() !== 'OPEN') {
        return total;
      }
      if ((leg.side || '').toUpperCase() !== 'BUY') {
        return total;
      }
      const legId = (leg.base_leg_id || '').toString().trim();
      if (markLegIds.size && !markLegIds.has(legId)) {
        return total;
      }
      const amount = Number(leg.amount ?? 0);
      const quantity = Number(leg.quantity ?? 0);
      const price = Number(leg.price ?? 0);
      const initialCost = amount || price * quantity * contractMultiplier;
      if (!Number.isFinite(initialCost) || initialCost <= 0) {
        return total;
      }
      return total + initialCost * weeklyRate;
    }, 0);
  }

  private computeOpenShortPremiumTotal(ledger: LedgerRow[], baseLegs: BaseLeg[]): number {
    const openLegIds = new Set(
      baseLegs
        .filter((leg) => (leg.tag || '').toUpperCase() === 'OPEN')
        .map((leg) => (leg.base_leg_id || '').toString().trim())
        .filter(Boolean)
    );
    const markLegIds = new Set(
      baseLegs
        .filter((leg) => (leg.tag || '').toUpperCase() === 'MARK')
        .map((leg) => (leg.base_leg_id || '').toString().trim())
        .filter(Boolean)
    );
    const activeLegIds = new Set<string>();
    openLegIds.forEach((id) => {
      if (markLegIds.has(id)) {
        activeLegIds.add(id);
      }
    });

    const summaries = buildLedgerSummaries(ledger);
    return summaries.reduce((sum, summary) => {
      if (summary.netContracts <= 0) {
        return sum;
      }
      const baseLegId = this.extractBaseLegId(summary.key);
      if (!baseLegId) {
        return sum;
      }
      if (activeLegIds.size && !activeLegIds.has(baseLegId)) {
        return sum;
      }
      return sum + summary.netPremium;
    }, 0);
  }

  private extractBaseLegId(key: string): string | null {
    const parts = (key || '').split('|');
    if (parts.length < 2) {
      return null;
    }
    return parts[0] || null;
  }
}
