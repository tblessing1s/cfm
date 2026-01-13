import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

export interface Trade {
  date: string;
  ticker: string;
  strategy: string;
  premium_in?: number;
  premium_out?: number;
  juice: number;
  basis?: number;
  dte?: number;
  itm?: boolean;
}

export interface WeeklySummary {
  week_start: string;
  week_end: string;
  strategy: string;
  total_juice: number;
  total_basis: number;
  percent_return: number;
  trade_count: number;
}

export interface CombinedWeeklyJuicePoint {
  week_start: string;
  total_juice: number;
}

export interface JuicePerTicker {
  ticker: string;
  total_juice: number;
}

export interface AccountOption {
  name: string;
  label: string;
}

export interface DashboardMetrics {
  weekly_juice_by_strategy: WeeklySummary[];
  combined_weekly_juice: CombinedWeeklyJuicePoint[];
  weekly_percent_returns: { week_start: string; percent_return: number }[];
  rolling_average_juice: { week_start: string; rolling_average: number }[];
  juice_per_ticker: JuicePerTicker[];
  win_rate: number;
  cumulative_juice: number;
  total_trades: number;
}

// Business scoreboard models
export interface NavSnapshot {
  account: string;
  date: string;
  nav_total: number;
  nav_cash?: number;
  nav_long_value?: number;
  nav_liabilities?: number;
  deposits?: number;
  withdrawals?: number;
}

export interface BasePosition {
  position_id: string;
  account: string;
  symbol: string;
  strategy: string;
  base_type: string;
  opened_date: string;
  closed_date?: string;
}

export interface BaseLeg {
  base_leg_id: string;
  position_id: string;
  date: string;
  time?: string;
  instrument_type: string;
  side: string;
  quantity: number;
  strike?: number;
  expiry?: string;
  price: number;
  underlying_price?: number;
  fees?: number;
  amount: number;
  tag?: string;
  condition?: string;
}

export interface ReserveRow {
  position_id: string;
  as_of_date: string;
  reserved_cash: number;
  note_or_rule_text?: string;
}

export interface ReplacementCost {
  position_id: string;
  as_of_date: string;
  replacement_cost_same_size: number;
  unit_replacement_cost: number;
  method: string;
}

export interface PositionMetrics {
  position: BasePosition;
  base_value?: number;
  base_cost?: number;
  initial_base_cost?: number;
  initial_base_intrinsic?: number;
  initial_base_extrinsic?: number;
  current_base_intrinsic?: number;
  base_plus_protection?: number;
  base_health_delta?: number;
  net_juice_to_date: number;
  net_intrinsic_to_date?: number;
  short_extrinsic_net?: number;
  long_extrinsic_loan?: number;
  long_extrinsic_paid?: number;
  long_extrinsic_remaining?: number;
  long_extrinsic_income?: number;
  replacement_cost?: number;
  unit_replacement_cost?: number;
  reserve_cash: number;
  replacement_ratio?: number;
  base_growth?: number;
  scale_capacity_units?: number;
  roll_plan_flag: boolean;
  roll_action_flag: boolean;
}

export interface BusinessDashboard {
  weekly_net_juice: number;
  monthly_net_juice: number;
  weekly_juice_yield_pct: number;
  monthly_juice_yield_pct: number;
  consistency_profitable_weeks_pct: number;
  consistency_avg_weekly_juice: number;
  preservation_ratio?: number;
  drawdown_pct?: number;
  reserve_coverage?: number;
  worst_replacement_ratio?: number;
  concentration_pct?: number;
  nav_current?: number;
  nav_peak?: number;
  nav_cash?: number;
  nav_long_value?: number;
  nav_liabilities?: number;
  nav_contributed?: number;
  portfolio_replacement_ratio?: number;
  distributable_income_weekly?: number;
  distributable_income_monthly?: number;
  income_allowed_weekly?: boolean;
  income_allowed_monthly?: boolean;
  mode?: string;
  nav_weekly?: { period_start: string; nav_total: number; nav_cash?: number; nav_long_value?: number; nav_liabilities?: number }[];
  nav_monthly?: { period_start: string; nav_total: number; nav_cash?: number; nav_long_value?: number; nav_liabilities?: number }[];
}

export interface PillarSeriesPoint {
  period_start: string;
  value: number;
}

export interface StockSummaryRow {
  ticker: string;
  original_base_value?: number;
  current_base_value?: number;
  initial_base_intrinsic?: number;
  initial_base_extrinsic?: number;
  current_base_intrinsic?: number;
  total_protection_collected?: number;
  base_strength_ratio?: number;
  base_market_value_change?: number;
  base_growth_pct?: number;
  income_total_realized: number;
  income_after_protection?: number;
  protection_gap?: number;
  protection_juice_applied?: number;
  juice_needed_for_protection?: number;
  income_rate_weekly?: number;
  income_rate_monthly?: number;
  avg_weekly_income?: number;
  income_efficiency?: number;
  income_consistency_pct?: number;
  short_extrinsic_net?: number;
  long_extrinsic_loan?: number;
  long_extrinsic_paid?: number;
  long_extrinsic_remaining?: number;
  long_extrinsic_income?: number;
  contribution_income_pct?: number;
  contribution_protection_pct?: number;
  contribution_growth_pct?: number;
}

export interface PortfolioSummary {
  total_account_value?: number;
  total_cash?: number;
  total_base_value_initial?: number;
  total_current_base_value?: number;
  total_initial_base_intrinsic?: number;
  total_initial_base_extrinsic?: number;
  total_current_base_intrinsic?: number;
  total_protection_collected?: number;
  total_base_plus_protection?: number;
  total_income_realized: number;
  total_income_after_protection?: number;
  total_protection_gap?: number;
  total_juice_needed_for_protection?: number;
  total_base_strength_ratio?: number;
  total_base_growth_pct?: number;
  total_short_extrinsic_net?: number;
  total_long_extrinsic_loan?: number;
  total_long_extrinsic_paid?: number;
  total_long_extrinsic_remaining?: number;
  total_long_extrinsic_income?: number;
  open_mark_initial_base_value?: number;
  open_mark_initial_intrinsic?: number;
  open_mark_initial_extrinsic?: number;
  open_mark_current_base_intrinsic?: number;
  open_mark_protection_collected?: number;
  open_mark_protection_gap?: number;
  open_mark_net_juice?: number;
  stocks: StockSummaryRow[];
}

export interface CashAllocation {
  account: string;
  ticker: string;
  type: 'extrinsic' | 'protection';
  amount: number;
  updated_at?: string;
}

export interface StockDetail {
  ticker: string;
  base_strength_ratio?: number;
  base_growth_pct?: number;
  income_total_realized: number;
  income_after_protection?: number;
  income_efficiency?: number;
  base_market_value?: number;
  original_base_value?: number;
  initial_base_intrinsic?: number;
  initial_base_extrinsic?: number;
  current_base_intrinsic?: number;
  base_plus_protection?: number;
  total_protection_collected?: number;
  protection_gap?: number;
  net_juice_total?: number;
  short_extrinsic_net?: number;
  long_extrinsic_loan?: number;
  long_extrinsic_paid?: number;
  long_extrinsic_remaining?: number;
  long_extrinsic_income?: number;
  income_series_weekly: PillarSeriesPoint[];
  base_strength_series_weekly: PillarSeriesPoint[];
  base_value_series_weekly: PillarSeriesPoint[];
  positions: PositionMetrics[];
}

export interface RegimeEntry {
  date: string;
  symbol: string;
  stock_score: number;
  market_score: number;
  stock_condition: string;
  market_condition: string;
}

export interface ProtectionMetrics {
  symbol: string;
  account?: string;
  target_income: number;
  latest_cycle_income: number;
  shortfall: number;
  defense_cost: number;
  cumulative_income: number;
  estimated_break_even_drop?: number;
}

export interface CashMovement {
  movement_id: string;
  account: string;
  date: string;
  direction: string;
  purpose: string;
  amount: number;
  position_id?: string;
  note?: string;
}

export interface TradeCreatePayload extends Trade {
  account: string;
}

export interface LedgerRow {
  account: string;
  date?: string;
  action?: string;
  side?: string;
  ticker: string;
  contracts?: number;
  strike?: number;
  expiry?: string;
  premium_buyback?: number;
  underlying?: number;
  juice_per_contract?: number;
  signed_juice_dollars?: number;
  signed_juice_per_100?: number;
  key?: string;
  notes?: string;
  condition?: string;
  row_number?: number;
  strategy?: string;
  base_position_id?: string;
  base_leg_id?: string;
}

export interface LedgerEntryCreate {
  account: string;
  ticker: string;
  action: 'Open' | 'Close';
  strategy: string;
  side?: 'Call' | 'Put';
  contracts: number;
  strike: number;
  expiry: string;
  trade_datetime: string;
  premium: number;
  underlying?: number;
  condition?: string;
  base_position_id?: string;
  base_leg_id?: string;
}

export interface LedgerUpdatePayload {
  row_number: number;
  account: string;
  ticker: string;
  action: string;
  strategy: string;
  side?: string;
  contracts: number;
  strike: number;
  expiry: string;
  trade_datetime: string;
  premium: number;
  base_position_id?: string;
  base_leg_id?: string;
}

@Injectable({
  providedIn: 'root',
})
export class DashboardService {
  private baseUrl = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  getTrades(account?: string): Observable<Trade[]> {
    return this.http.get<Trade[]>(`${this.baseUrl}/trades`, this._buildRequestOptions(account));
  }

  getWeeklySummary(account?: string): Observable<WeeklySummary[]> {
    return this.http.get<WeeklySummary[]>(`${this.baseUrl}/weekly-summary`, this._buildRequestOptions(account));
  }

  getDashboardMetrics(account?: string): Observable<DashboardMetrics> {
    return this.http.get<DashboardMetrics>(`${this.baseUrl}/dashboard-metrics`, this._buildRequestOptions(account));
  }

  // Business dashboard
  getBusinessDashboard(account?: string, expiryStart?: string, expiryEnd?: string): Observable<BusinessDashboard> {
    let params = new HttpParams();
    if (account) {
      params = params.set('account', account);
    }
    if (expiryStart) {
      params = params.set('expiry_start', expiryStart);
    }
    if (expiryEnd) {
      params = params.set('expiry_end', expiryEnd);
    }
    return this.http.get<BusinessDashboard>(`${this.baseUrl}/business-dashboard`, params.keys().length ? { params } : {});
  }

  listPositionMetrics(
    account?: string,
    includeClosed: boolean = false,
    expiryStart?: string,
    expiryEnd?: string
  ): Observable<PositionMetrics[]> {
    let params = new HttpParams();
    if (account) {
      params = params.set('account', account);
    }
    if (includeClosed) {
      params = params.set('include_closed', 'true');
    }
    if (expiryStart) {
      params = params.set('expiry_start', expiryStart);
    }
    if (expiryEnd) {
      params = params.set('expiry_end', expiryEnd);
    }
    const options = params.keys().length ? { params } : {};
    return this.http.get<PositionMetrics[]>(`${this.baseUrl}/positions`, options);
  }

  getPortfolioSummary(account?: string, includeClosed?: boolean, expiryStart?: string, expiryEnd?: string): Observable<PortfolioSummary> {
    let params = new HttpParams();
    if (account) {
      params = params.set('account', account);
    }
    if (includeClosed) {
      params = params.set('include_closed', 'true');
    }
    if (expiryStart) {
      params = params.set('expiry_start', expiryStart);
    }
    if (expiryEnd) {
      params = params.set('expiry_end', expiryEnd);
    }
    return this.http.get<PortfolioSummary>(`${this.baseUrl}/portfolio-summary`, params.keys().length ? { params } : {});
  }

  listStocks(account?: string, includeClosed?: boolean): Observable<StockSummaryRow[]> {
    return this.http.get<StockSummaryRow[]>(`${this.baseUrl}/stocks`, this._buildRequestOptions(account, includeClosed));
  }

  getStockDetail(
    ticker: string,
    account?: string,
    includeClosed?: boolean,
    expiryStart?: string,
    expiryEnd?: string
  ): Observable<StockDetail> {
    let params = new HttpParams();
    if (account) {
      params = params.set('account', account);
    }
    if (includeClosed) {
      params = params.set('include_closed', 'true');
    }
    if (expiryStart) {
      params = params.set('expiry_start', expiryStart);
    }
    if (expiryEnd) {
      params = params.set('expiry_end', expiryEnd);
    }
    return this.http.get<StockDetail>(
      `${this.baseUrl}/stocks/${encodeURIComponent(ticker)}`,
      params.keys().length ? { params } : {}
    );
  }

  createRegimeEntry(payload: RegimeEntry): Observable<RegimeEntry> {
    return this.http.post<RegimeEntry>(`${this.baseUrl}/regime`, payload);
    }

  listRegimeEntries(symbol?: string): Observable<RegimeEntry[]> {
    const options = symbol ? { params: new HttpParams().set('symbol', symbol) } : {};
    return this.http.get<RegimeEntry[]>(`${this.baseUrl}/regime`, options);
  }

  getProtectionMetrics(
    symbol: string,
    account?: string,
    targetIncome?: number,
    expiryStart?: string,
    expiryEnd?: string
  ): Observable<ProtectionMetrics> {
    let params = new HttpParams().set('symbol', symbol);
    if (account) params = params.set('account', account);
    if (targetIncome !== undefined) params = params.set('target_income', targetIncome);
    if (expiryStart) params = params.set('expiry_start', expiryStart);
    if (expiryEnd) params = params.set('expiry_end', expiryEnd);
    return this.http.get<ProtectionMetrics>(`${this.baseUrl}/protection-metrics`, { params });
  }

  listCashAllocations(account?: string): Observable<CashAllocation[]> {
    return this.http.get<CashAllocation[]>(`${this.baseUrl}/cash-allocations`, this._buildRequestOptions(account));
  }

  saveCashAllocation(payload: CashAllocation): Observable<CashAllocation> {
    return this.http.post<CashAllocation>(`${this.baseUrl}/cash-allocations`, payload);
  }

  // CRUD helpers
  createNavSnapshot(payload: NavSnapshot): Observable<NavSnapshot> {
    return this.http.post<NavSnapshot>(`${this.baseUrl}/nav-snapshots`, payload);
  }

  createBasePosition(payload: BasePosition): Observable<BasePosition> {
    return this.http.post<BasePosition>(`${this.baseUrl}/positions`, payload);
  }

  updateBasePosition(positionId: string, payload: BasePosition): Observable<BasePosition> {
    return this.http.put<BasePosition>(`${this.baseUrl}/positions/${positionId}`, payload);
  }

  createBaseLeg(payload: BaseLeg): Observable<BaseLeg> {
    return this.http.post<BaseLeg>(`${this.baseUrl}/base-legs`, payload);
  }

  listBaseLegs(positionId?: string): Observable<BaseLeg[]> {
    let params = new HttpParams();
    if (positionId) {
      params = params.set('position_id', positionId);
    }
    return this.http.get<BaseLeg[]>(`${this.baseUrl}/base-legs`, { params });
  }

  createReserve(payload: ReserveRow): Observable<ReserveRow> {
    return this.http.post<ReserveRow>(`${this.baseUrl}/reserves`, payload);
  }

  createReplacementCost(payload: ReplacementCost): Observable<ReplacementCost> {
    return this.http.post<ReplacementCost>(`${this.baseUrl}/replacement-costs`, payload);
  }

  listCashMovements(account?: string, positionId?: string): Observable<CashMovement[]> {
    let params = new HttpParams();
    if (account) {
      params = params.set('account', account);
    }
    if (positionId) {
      params = params.set('position_id', positionId);
    }
    return this.http.get<CashMovement[]>(`${this.baseUrl}/cash-movements`, params.keys().length ? { params } : {});
  }

  createCashMovement(payload: CashMovement): Observable<CashMovement> {
    return this.http.post<CashMovement>(`${this.baseUrl}/cash-movements`, payload);
  }

  getAccounts(): Observable<AccountOption[]> {
    return this.http.get<AccountOption[]>(`${this.baseUrl}/accounts`);
  }

  createTrades(trades: TradeCreatePayload[]): Observable<{ created: number }> {
    return this.http.post<{ created: number }>(`${this.baseUrl}/trades`, trades);
  }

  getLedger(account?: string): Observable<LedgerRow[]> {
    return this.http.get<LedgerRow[]>(`${this.baseUrl}/ledger`, this._buildRequestOptions(account));
  }

  appendLedger(entries: LedgerEntryCreate[]): Observable<LedgerRow[]> {
    return this.http.post<LedgerRow[]>(`${this.baseUrl}/ledger/append`, entries);
  }

  updateLedger(entry: LedgerUpdatePayload): Observable<LedgerRow> {
    return this.http.put<LedgerRow>(`${this.baseUrl}/ledger/update`, entry);
  }

  private _buildRequestOptions(account?: string, includeClosed?: boolean) {
    let params = new HttpParams();
    if (account) {
      params = params.set('account', account);
    }
    if (includeClosed) {
      params = params.set('include_closed', 'true');
    }
    return params.keys().length ? { params } : {};
  }
}
