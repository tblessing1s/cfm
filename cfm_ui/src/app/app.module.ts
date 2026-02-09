import { HttpClientModule } from '@angular/common/http';
import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';

import { AppComponent } from './app.component';
import { AppRoutingModule } from './app-routing.module';
import { CfmDashboardComponent } from './cfm-dashboard/cfm-dashboard.component';
import { AccountSummaryComponent } from './cfm-dashboard/components/account-summary.component';
import { PositionsTableComponent } from './cfm-dashboard/components/positions-table.component';
import { StatusBadgeComponent } from './cfm-dashboard/components/status-badge.component';
import { CircuitBreakerPopoverComponent } from './cfm-dashboard/components/circuit-breaker-popover.component';
import { BaseStatusPopoverComponent } from './cfm-dashboard/components/base-status-popover.component';
import { LegacyDashboardComponent } from './legacy-dashboard/legacy-dashboard.component';

@NgModule({
  declarations: [
    AppComponent,
    CfmDashboardComponent,
    AccountSummaryComponent,
    PositionsTableComponent,
    StatusBadgeComponent,
    CircuitBreakerPopoverComponent,
    BaseStatusPopoverComponent,
    LegacyDashboardComponent,
  ],
  imports: [BrowserModule, HttpClientModule, FormsModule, AppRoutingModule],
  providers: [],
  bootstrap: [AppComponent],
})
export class AppModule {}
