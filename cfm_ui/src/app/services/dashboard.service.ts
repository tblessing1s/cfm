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
  row_number?: number;
  strategy?: string;
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

  private _buildRequestOptions(account?: string) {
    if (!account) {
      return {};
    }

    const params = new HttpParams().set('account', account);
    return { params };
  }
}
