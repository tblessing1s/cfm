import { Component, Input } from '@angular/core';

import { AccountSummary } from '../cfm-dashboard.models';

@Component({
  selector: 'app-account-summary',
  templateUrl: './account-summary.component.html',
  styleUrls: ['./account-summary.component.css'],
})
export class AccountSummaryComponent {
  @Input({ required: true }) summary!: AccountSummary;

  get buybackReserveRequired(): number {
    return 1.5 * this.summary.openShortPremiumTotal;
  }

  get defenseReserveRequired(): number {
    return 0.1 * this.summary.longInitialCostTotal;
  }

  get reservedCashRequired(): number {
    return this.buybackReserveRequired + this.defenseReserveRequired;
  }

  get freeCash(): number {
    return this.summary.cashBalance - this.reservedCashRequired;
  }

  // Gap to goal intentionally omitted from the summary UI.
}
