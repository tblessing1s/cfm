import { Component, OnInit } from '@angular/core';

import {
  DEFAULT_BASE_THRESHOLDS,
  WEEKLY_TARGET_BY_REGIME,
} from './cfm-dashboard.constants';
import {
  AccountSummary,
  Position,
  PositionView,
} from './cfm-dashboard.models';
import { CfmDashboardService } from './cfm-dashboard.service';
import { computeBaseStatus, computeCircuitBreakerStatus } from './cfm-dashboard.utils';
import { AccountOption } from '../services/dashboard.service';

@Component({
  selector: 'app-cfm-dashboard',
  templateUrl: './cfm-dashboard.component.html',
  styleUrls: ['./cfm-dashboard.component.css'],
})
export class CfmDashboardComponent implements OnInit {
  accounts: AccountOption[] = [];
  selectedAccount?: string;
  summary?: AccountSummary;
  positions: PositionView[] = [];
  loading = true;
  error?: string;
  readonly thresholds = DEFAULT_BASE_THRESHOLDS;

  constructor(private readonly dashboardService: CfmDashboardService) {}

  ngOnInit(): void {
    this.dashboardService.getAccounts().subscribe({
      next: (accounts) => {
        this.accounts = accounts;
        this.selectedAccount = accounts[0]?.name;
        this.loadDashboard();
      },
      error: () => {
        this.error = 'Unable to load accounts.';
        this.loading = false;
        this.loadDashboard();
      },
    });
  }

  onAccountChange(value: string): void {
    this.selectedAccount = value;
    this.loadDashboard();
  }

  loadDashboard(): void {
    this.loading = true;
    this.error = undefined;
    this.dashboardService.loadDashboard(this.selectedAccount).subscribe({
      next: ({ summary, positions }) => {
        this.summary = summary;
        this.positions = this.decoratePositions(positions);
        this.loading = false;
      },
      error: () => {
        this.error = 'Unable to load dashboard data.';
        this.loading = false;
      },
    });
  }

  private decoratePositions(positions: Position[]): PositionView[] {
    return positions.map((pos) => {
      const circuitBreakerStatus = computeCircuitBreakerStatus(pos.circuitBreakers);
      const baseStatus = computeBaseStatus(pos, this.thresholds);
      const weeklyTargetPct = WEEKLY_TARGET_BY_REGIME[pos.regime];

      return {
        ...pos,
        circuitBreakerStatus,
        baseStatus,
        weeklyTargetPct,
      };
    });
  }
}
