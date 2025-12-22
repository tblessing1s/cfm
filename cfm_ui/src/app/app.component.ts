import { Component, OnInit } from '@angular/core';

import {
  AccountOption,
  DashboardMetrics,
  DashboardService,
  LedgerEntryCreate,
  LedgerRow,
  Trade,
} from './services/dashboard.service';

interface LedgerDraft {
  account?: string;
  ticker: string;
  action: 'Open' | 'Close';
  strategy: string;
  side: 'Call' | 'Put';
  contracts?: number;
  strike?: number;
  expiry?: string;
  trade_datetime?: string;
  premium?: number;
}

interface LedgerSummary {
  key: string;
  ticker: string;
  side: string;
  strike: number;
  expiry: string | null;
  netContracts: number;
  netPremium: number;
  netJuice: number;
  netJuicePer100: number;
  rows: LedgerRow[];
}

interface ExpiryTotal {
  expiry: string;
  netContracts: number;
  netPremium: number;
  netJuice: number;
  netJuicePer100: number;
}

interface ExpiryMonthGroup {
  month: string;
  netContracts: number;
  netPremium: number;
  netJuice: number;
  netJuicePer100: number;
  children: ExpiryTotal[];
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent implements OnInit {
  accounts: AccountOption[] = [];
  selectedAccount?: string;
  metrics?: DashboardMetrics;
  loading = true;
  error?: string;
  trades: Trade[] = [];
  tradesLoading = false;
  ledgerRows: LedgerRow[] = [];
  ledgerSummaries: LedgerSummary[] = [];
  ledgerLoading = false;
  ledgerError?: string;
  ledgerPageSize = 20;
  ledgerPage = 1;
  ledgerOpenOnly = false;
  ledgerOpenBalances: Record<string, { remaining: number; row: LedgerRow }> = {};
  tickerFilterOptions: string[] = [];
  selectedTickers: string[] = [];
  tickerFilterOpen = false;
  sideFilterOptions: string[] = [];
  selectedSides: string[] = [];
  sideFilterOpen = false;
  strikeFilterOptions: string[] = [];
  selectedStrikes: string[] = [];
  strikeFilterOpen = false;
  expiryFilterOptions: string[] = [];
  selectedExpiries: string[] = [];
  expiryFilterOpen = false;
  editingLedgerRowNumber: number | null = null;
  editingLedgerAccount?: string;
  expandedSummaries = new Set<string>();
  expandedExpiryMonths = new Set<string>();
  ledgerSortOrder: Array<{
    column:
      | 'date'
      | 'ticker'
      | 'side'
      | 'strike'
      | 'expiry'
      | 'netContracts'
      | 'netPremium'
      | 'netJuice'
      | 'netJuicePer100';
    direction: 'asc' | 'desc';
  }> = [{ column: 'date', direction: 'desc' }];
  strategySuggestions: string[] = [];
  tickerSuggestions: string[] = [];

  tradeDraft: LedgerDraft = this.buildBlankDraft();
  pendingTrades: LedgerEntryCreate[] = [];
  entryError?: string;
  entrySuccess?: string;
  copyFeedback?: string;
  submitLoading = false;
  submitError?: string;
  submitSuccess?: string;

  constructor(private dashboardService: DashboardService) {}

  ngOnInit(): void {
    this.tradeDraft = this.buildBlankDraft();

    this.dashboardService.getAccounts().subscribe({
      next: (accounts) => {
        this.accounts = accounts.map((acc) => this.normalizeAccountOption(acc));
        if (accounts.length) {
          this.selectedAccount = accounts[0].name;
          this.tradeDraft.account = this.selectedAccount;
          this.trades = [];
          this.loadMetrics();
          this.loadLedger(this.selectedAccount);
          return;
        }

        this.loading = false;
        this.error = 'No accounts are configured in the journal yet.';
      },
      error: () => {
        this.loading = false;
        this.error = 'Unable to load account information.';
      },
    });
  }

  loadMetrics(): void {
    if (!this.selectedAccount) {
      this.loading = false;
      return;
    }

    this.loading = true;
    this.error = undefined;

    this.dashboardService.getDashboardMetrics(this.selectedAccount).subscribe({
      next: (data) => {
        this.metrics = data;
        this.loading = false;
        this.loadTrades(this.selectedAccount!);
        this.loadLedger(this.selectedAccount!);
      },
      error: () => {
        this.loading = false;
        this.error = 'Unable to load dashboard metrics from the API.';
      },
    });
  }

  loadTrades(account: string): void {
    this.tradesLoading = true;
    this.dashboardService.getTrades(account).subscribe({
      next: (data) => {
        this.trades = data;
        this.updateSuggestions(data);
        this.tradesLoading = false;
      },
      error: () => {
        this.trades = [];
        this.tradesLoading = false;
      },
    });
  }

  loadLedger(account: string): void {
    this.ledgerLoading = true;
    this.ledgerError = undefined;
    this.dashboardService.getLedger(account).subscribe({
      next: (rows) => {
        this.ledgerRows = this.sortLedgerRows(rows);
        this.ledgerOpenBalances = this.computeOpenBalances(this.ledgerRows);
        this.ledgerSummaries = this.buildLedgerSummaries(this.ledgerRows);
        this.updateLedgerFilterOptions(this.ledgerSummaries);
        this.ledgerPage = 1;
        this.ledgerLoading = false;
      },
      error: () => {
        this.ledgerRows = [];
        this.ledgerLoading = false;
        this.ledgerError = 'Unable to load ledger rows.';
      },
    });
  }

  onAccountChange(accountName: string): void {
    if (accountName === this.selectedAccount) {
      return;
    }

    this.selectedAccount = accountName;
    this.tradeDraft.account = accountName;
    this.selectedTickers = [];
    this.selectedSides = [];
    this.selectedStrikes = [];
    this.selectedExpiries = [];
    this.metrics = undefined;
    this.loadMetrics();
    this.loadLedger(accountName);
  }

  get selectedAccountLabel(): string {
    const account = this.accounts.find((entry) => entry.name === this.selectedAccount);
    return account ? account.label : 'Unknown account';
  }

  get latestWeekTradeCount(): number {
    if (!this.metrics?.weekly_juice_by_strategy?.length) {
      return 0;
    }

    return (
      this.metrics.weekly_juice_by_strategy[this.metrics.weekly_juice_by_strategy.length - 1]
        ?.trade_count ?? 0
    );
  }

  get stagedJson(): string {
    return JSON.stringify(this.pendingTrades, null, 2);
  }

  get canStageTrade(): boolean {
    const account = this.tradeDraft.account || this.selectedAccount;
    const contracts = this.toNumber(this.tradeDraft.contracts);
    const strike = this.toNumber(this.tradeDraft.strike);
    const premium = this.toNumber(this.tradeDraft.premium);
    const hasBasics =
      !!account &&
      !!this.tradeDraft.trade_datetime &&
      !!this.tradeDraft.ticker?.trim() &&
      !!this.tradeDraft.strategy &&
      !!this.tradeDraft.action &&
      contracts !== undefined &&
      strike !== undefined &&
      !!this.tradeDraft.expiry &&
      premium !== undefined;
    return hasBasics;
  }

  stageTrade(): void {
    this.entryError = undefined;
    this.entrySuccess = undefined;

    const account = this.tradeDraft.account || this.selectedAccount;
    if (!account) {
      this.entryError = 'Select an account before staging trades.';
      return;
    }

    if (!this.tradeDraft.trade_datetime) {
      this.entryError = 'Pick a trade date/time.';
      return;
    }

    const ticker = (this.tradeDraft.ticker || '').trim().toUpperCase();
    if (!ticker) {
      this.entryError = 'Ticker is required.';
      return;
    }

    if (!this.tradeDraft.expiry) {
      this.entryError = 'Pick an expiration date.';
      return;
    }

    const contracts = this.toNumber(this.tradeDraft.contracts);
    const strike = this.toNumber(this.tradeDraft.strike);
    const premium = this.toNumber(this.tradeDraft.premium);

    this.enforceSideForStrategy();

    const staged: LedgerEntryCreate = {
      account,
      // `datetime-local` is a local-time value with no timezone. Sending it as-is
      // avoids shifting the time when converting to UTC via `toISOString()`.
      trade_datetime: this.tradeDraft.trade_datetime,
      ticker,
      strategy: this.tradeDraft.strategy,
      action: this.tradeDraft.action,
      side: this.tradeDraft.side,
      contracts: contracts ?? 0,
      strike: strike ?? 0,
      expiry: this.tradeDraft.expiry!,
      premium: premium ?? 0,
    };

    this.pendingTrades = [...this.pendingTrades, staged];
    this.entrySuccess = `Staged ${ticker} ${staged.action} for ${account}.`;
    this.tradeDraft = this.buildBlankDraft(account);
  }

  removeStagedTrade(index: number): void {
    this.pendingTrades = this.pendingTrades.filter((_, idx) => idx !== index);
  }

  clearStagedTrades(): void {
    this.pendingTrades = [];
    this.submitSuccess = undefined;
    this.submitError = undefined;
  }

  editStagedTrade(index: number): void {
    const entry = this.pendingTrades[index];
    if (!entry) {
      return;
    }

    this.pendingTrades = this.pendingTrades.filter((_, idx) => idx !== index);
    this.tradeDraft = {
      account: entry.account,
      trade_datetime: entry.trade_datetime,
      ticker: entry.ticker,
      strategy: this.normalizeStrategy(entry.strategy),
      action: entry.action,
      side: entry.side,
      contracts: entry.contracts,
      strike: entry.strike,
      expiry: entry.expiry,
      premium: entry.premium,
    };
    this.enforceSideForStrategy(this.tradeDraft);
    this.entrySuccess = `Editing ${entry.ticker} ${entry.action}.`;
    this.submitError = undefined;
    this.submitSuccess = undefined;
  }

  startLedgerRowEdit(row: LedgerRow): void {
    if (!row.row_number) {
      this.entryError = 'Unable to edit this ledger row (missing row number).';
      return;
    }

    this.editingLedgerRowNumber = row.row_number;
    this.editingLedgerAccount = row.account;

    const actionClean = (row.action || 'Open').toString().toLowerCase();
    const action: 'Open' | 'Close' = actionClean.includes('close') ? 'Close' : 'Open';
    const side: 'Call' | 'Put' = (row.side || 'Call').toString().toLowerCase().includes('put') ? 'Put' : 'Call';
    const tradeDate = row.date ? row.date.toString().substring(0, 16) : '';

    this.tradeDraft = {
      account: row.account,
      trade_datetime: tradeDate,
      ticker: row.ticker,
      strategy: this.normalizeStrategy(row.strategy || ''),
      action,
      side,
      contracts: row.contracts ?? undefined,
      strike: row.strike ?? undefined,
      expiry: row.expiry ?? undefined,
      premium: row.premium_buyback ?? undefined,
    };
    this.enforceSideForStrategy(this.tradeDraft);
    this.entrySuccess = `Editing ledger row ${row.row_number} (${row.ticker}).`;
    this.submitError = undefined;
    this.submitSuccess = undefined;
  }

  cancelLedgerEdit(): void {
    this.editingLedgerRowNumber = null;
    this.editingLedgerAccount = undefined;
    this.tradeDraft = this.buildBlankDraft(this.selectedAccount);
    this.entryError = undefined;
    this.entrySuccess = undefined;
  }

  saveLedgerEdit(): void {
    this.submitError = undefined;
    this.submitSuccess = undefined;
    if (!this.editingLedgerRowNumber) {
      this.submitError = 'No ledger row selected for edit.';
      return;
    }

    const account = this.editingLedgerAccount || this.selectedAccount || this.tradeDraft.account;
    if (!account) {
      this.submitError = 'Select an account before saving.';
      return;
    }

    if (!this.tradeDraft.trade_datetime) {
      this.submitError = 'Pick a trade date/time.';
      return;
    }

    const ticker = (this.tradeDraft.ticker || '').trim().toUpperCase();
    if (!ticker) {
      this.submitError = 'Ticker is required.';
      return;
    }

    if (!this.tradeDraft.expiry) {
      this.submitError = 'Pick an expiration date.';
      return;
    }

    const contracts = this.toNumber(this.tradeDraft.contracts);
    const strike = this.toNumber(this.tradeDraft.strike);
    const premium = this.toNumber(this.tradeDraft.premium);

    const payload = {
      row_number: this.editingLedgerRowNumber,
      account,
      trade_datetime: this.tradeDraft.trade_datetime,
      ticker,
      strategy: this.normalizeStrategy(this.tradeDraft.strategy),
      action: this.tradeDraft.action,
      side: this.tradeDraft.side,
      contracts: contracts ?? 0,
      strike: strike ?? 0,
      expiry: this.tradeDraft.expiry!,
      premium: premium ?? 0,
    };

    this.submitLoading = true;
    this.dashboardService.updateLedger(payload).subscribe({
      next: () => {
        this.submitSuccess = `Updated ledger row ${this.editingLedgerRowNumber}.`;
        this.editingLedgerRowNumber = null;
        this.editingLedgerAccount = undefined;
        this.tradeDraft = this.buildBlankDraft(this.selectedAccount);
        if (this.selectedAccount) {
          this.loadLedger(this.selectedAccount);
        }
      },
      error: (err) => {
        const detail = err?.error?.detail || err?.error?.message || err?.message;
        this.submitError = detail ? String(detail) : 'Unable to update ledger row.';
      },
      complete: () => {
        this.submitLoading = false;
      },
    });
  }

  async copyStagedTrades(): Promise<void> {
    this.copyFeedback = undefined;
    if (!this.pendingTrades.length) {
      return;
    }

    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(this.stagedJson);
        this.copyFeedback = 'Copied JSON to clipboard.';
      } else {
        this.copyFeedback = 'Clipboard access is unavailable in this browser.';
      }
    } catch {
      this.copyFeedback = 'Unable to copy to clipboard.';
    }
  }

  resetDraft(account?: string): void {
    this.tradeDraft = this.buildBlankDraft(account ?? this.tradeDraft.account ?? this.selectedAccount);
    this.enforceSideForStrategy();
    this.entryError = undefined;
    this.entrySuccess = undefined;
  }

  normalizeTicker(): void {
    if (!this.tradeDraft.ticker) {
      return;
    }
    this.tradeDraft.ticker = this.tradeDraft.ticker.trim().toUpperCase();
  }

  get ledgerTotalPages(): number {
    const total = this.filteredLedgerSummaries().length;
    return Math.max(1, Math.ceil(total / this.ledgerPageSize));
  }

  get expiryTotals(): ExpiryTotal[] {
    return this.computeExpiryTotals(this.filteredLedgerSummaries());
  }

  get expiryMonthGroups(): ExpiryMonthGroup[] {
    const totals = this.computeExpiryTotals(this.filteredLedgerSummaries());
    const groups: Record<string, ExpiryMonthGroup> = {};

    totals.forEach((total) => {
      const monthKey = total.expiry && total.expiry !== '—' ? total.expiry.slice(0, 7) : '—';
      if (!groups[monthKey]) {
        groups[monthKey] = {
          month: monthKey,
          netContracts: 0,
          netPremium: 0,
          netJuice: 0,
          netJuicePer100: 0,
          children: [],
        };
      }
      const bucket = groups[monthKey];
      bucket.children.push(total);
      bucket.netContracts += total.netContracts;
      bucket.netPremium += total.netPremium;
      bucket.netJuice += total.netJuice;
    });

    return Object.values(groups)
      .map((group) => ({
        ...group,
        netJuicePer100: group.netJuice * 100,
        children: group.children.sort((a, b) => b.expiry.localeCompare(a.expiry)),
      }))
      .sort((a, b) => {
        if (a.month === '—') return 1;
        if (b.month === '—') return -1;
        return b.month.localeCompare(a.month);
      });
  }

  get pagedLedgerSummaries(): LedgerSummary[] {
    const rows = this.filteredLedgerSummaries();
    const start = (this.ledgerPage - 1) * this.ledgerPageSize;
    return rows.slice(start, start + this.ledgerPageSize);
  }

  get ledgerRangeLabel(): string {
    const total = this.filteredLedgerSummaries().length;
    if (!total) {
      return '0 of 0';
    }
    const start = (this.ledgerPage - 1) * this.ledgerPageSize + 1;
    const end = Math.min(this.ledgerPage * this.ledgerPageSize, total);
    return `${start}-${end} of ${total}`;
  }

  prevLedgerPage(): void {
    if (this.ledgerPage > 1) {
      this.ledgerPage -= 1;
    }
  }

  nextLedgerPage(): void {
    if (this.ledgerPage < this.ledgerTotalPages) {
      this.ledgerPage += 1;
    }
  }

  onLedgerPageSizeChange(size: number): void {
    this.ledgerPageSize = size;
    this.ledgerPage = 1;
  }

  toggleOpenOnly(): void {
    this.ledgerOpenOnly = !this.ledgerOpenOnly;
    this.ledgerPage = 1;
  }

  onTickerFilterChange(value: string[] | string): void {
    const list = Array.isArray(value) ? value : [value];
    this.selectedTickers = Array.from(
      new Set(list.map((item) => String(item || '').trim().toUpperCase()).filter((item) => item))
    );
    this.ledgerPage = 1;
  }

  clearTickerFilter(): void {
    this.selectedTickers = [];
    this.ledgerPage = 1;
  }

  toggleTickerFilter(): void {
    this.tickerFilterOpen = !this.tickerFilterOpen;
  }

  closeTickerFilter(): void {
    this.tickerFilterOpen = false;
  }

  isAllTickersSelected(): boolean {
    return (
      this.tickerFilterOptions.length > 0 &&
      this.selectedTickers.length === this.tickerFilterOptions.length
    );
  }

  toggleAllTickers(checked: boolean): void {
    this.selectedTickers = checked ? [...this.tickerFilterOptions] : [];
    this.ledgerPage = 1;
  }

  toggleTickerSelection(ticker: string, checked: boolean): void {
    const next = new Set(this.selectedTickers);
    if (checked) {
      next.add(ticker);
    } else {
      next.delete(ticker);
    }
    this.selectedTickers = Array.from(next);
    this.ledgerPage = 1;
  }

  toggleSideFilter(): void {
    this.sideFilterOpen = !this.sideFilterOpen;
  }

  closeSideFilter(): void {
    this.sideFilterOpen = false;
  }

  isAllSidesSelected(): boolean {
    return this.sideFilterOptions.length > 0 && this.selectedSides.length === this.sideFilterOptions.length;
  }

  toggleAllSides(checked: boolean): void {
    this.selectedSides = checked ? [...this.sideFilterOptions] : [];
    this.ledgerPage = 1;
  }

  toggleSideSelection(side: string, checked: boolean): void {
    const next = new Set(this.selectedSides);
    if (checked) {
      next.add(side);
    } else {
      next.delete(side);
    }
    this.selectedSides = Array.from(next);
    this.ledgerPage = 1;
  }

  toggleStrikeFilter(): void {
    this.strikeFilterOpen = !this.strikeFilterOpen;
  }

  closeStrikeFilter(): void {
    this.strikeFilterOpen = false;
  }

  isAllStrikesSelected(): boolean {
    return (
      this.strikeFilterOptions.length > 0 &&
      this.selectedStrikes.length === this.strikeFilterOptions.length
    );
  }

  toggleAllStrikes(checked: boolean): void {
    this.selectedStrikes = checked ? [...this.strikeFilterOptions] : [];
    this.ledgerPage = 1;
  }

  toggleStrikeSelection(strike: string, checked: boolean): void {
    const next = new Set(this.selectedStrikes);
    if (checked) {
      next.add(strike);
    } else {
      next.delete(strike);
    }
    this.selectedStrikes = Array.from(next);
    this.ledgerPage = 1;
  }

  toggleExpiryFilter(): void {
    this.expiryFilterOpen = !this.expiryFilterOpen;
  }

  closeExpiryFilter(): void {
    this.expiryFilterOpen = false;
  }

  isAllExpiriesSelected(): boolean {
    return (
      this.expiryFilterOptions.length > 0 &&
      this.selectedExpiries.length === this.expiryFilterOptions.length
    );
  }

  toggleAllExpiries(checked: boolean): void {
    this.selectedExpiries = checked ? [...this.expiryFilterOptions] : [];
    this.ledgerPage = 1;
  }

  toggleExpirySelection(expiry: string, checked: boolean): void {
    const next = new Set(this.selectedExpiries);
    if (checked) {
      next.add(expiry);
    } else {
      next.delete(expiry);
    }
    this.selectedExpiries = Array.from(next);
    this.ledgerPage = 1;
  }

  toggleSummary(key: string): void {
    if (this.expandedSummaries.has(key)) {
      this.expandedSummaries.delete(key);
    } else {
      this.expandedSummaries.add(key);
    }
  }

  toggleExpiryMonth(month: string): void {
    if (this.expandedExpiryMonths.has(month)) {
      this.expandedExpiryMonths.delete(month);
    } else {
      this.expandedExpiryMonths.add(month);
    }
  }

  onLedgerSort(
    column:
      | 'date'
      | 'ticker'
      | 'side'
      | 'strike'
      | 'expiry'
      | 'netContracts'
      | 'netPremium'
      | 'netJuice'
      | 'netJuicePer100',
    event?: MouseEvent
  ): void {
    const shift = !!event?.shiftKey;
    const idx = this.ledgerSortOrder.findIndex((s) => s.column === column);

    if (!shift) {
      const nextDir =
        idx >= 0 ? (this.ledgerSortOrder[idx].direction === 'asc' ? 'desc' : 'asc') : column === 'date' ? 'desc' : 'asc';
      this.ledgerSortOrder = [{ column, direction: nextDir }];
    } else {
      if (idx >= 0) {
        const nextDir = this.ledgerSortOrder[idx].direction === 'asc' ? 'desc' : 'asc';
        const clone = [...this.ledgerSortOrder];
        clone[idx] = { column, direction: nextDir };
        this.ledgerSortOrder = clone;
      } else {
        const nextDir = column === 'date' ? 'desc' : 'asc';
        this.ledgerSortOrder = [...this.ledgerSortOrder, { column, direction: nextDir }];
      }
    }

    this.ledgerPage = 1;
  }

  ledgerSortIndicator(column: (typeof this.ledgerSortOrder)[number]['column']): string {
    const idx = this.ledgerSortOrder.findIndex((s) => s.column === column);
    if (idx < 0) {
      return '';
    }
    const arrow = this.ledgerSortOrder[idx].direction === 'asc' ? '▲' : '▼';
    const order = this.ledgerSortOrder.length > 1 ? ` ${idx + 1}` : '';
    return `${arrow}${order}`;
  }

  onStrategyChange(value: string): void {
    const strategy = this.normalizeStrategy(value);
    this.tradeDraft.strategy = strategy;
    this.enforceSideForStrategy();
  }

  submitTrades(): void {
    this.submitError = undefined;
    this.submitSuccess = undefined;
    if (!this.pendingTrades.length) {
      this.submitError = 'No staged trades to submit.';
      return;
    }
    this.submitLoading = true;
    this.dashboardService.appendLedger(this.pendingTrades).subscribe({
      next: () => {
        this.submitSuccess = `Submitted ${this.pendingTrades.length} trade(s) to the ledger.`;
        this.pendingTrades = [];
        if (this.selectedAccount) {
          this.loadTrades(this.selectedAccount);
          this.loadMetrics();
          this.loadLedger(this.selectedAccount);
        }
      },
      error: (err) => {
        const detail = err?.error?.detail || err?.error?.message || err?.message;
        this.submitError = detail ? String(detail) : 'Unable to submit trades to the ledger.';
      },
      complete: () => {
        this.submitLoading = false;
      },
    });
  }

  private updateSuggestions(trades: Trade[]): void {
    const strategies = new Set<string>();
    const tickers = new Set<string>();
    trades.forEach((trade) => {
      if (trade.strategy) {
        strategies.add(trade.strategy);
      }
      if (trade.ticker) {
        tickers.add(trade.ticker.toUpperCase());
      }
    });

    this.strategySuggestions = Array.from(strategies).sort();
    this.tickerSuggestions = Array.from(tickers).sort();
  }

  private normalizeStrategy(value: string | undefined): 'Juice Lever' | 'Cashflow Machine' {
    if (typeof value === 'string') {
      const normalized = value.toLowerCase();
      if (normalized.includes('juice')) {
        return 'Juice Lever';
      }
      if (normalized.includes('cashflow')) {
        return 'Cashflow Machine';
      }
    }
    return 'Cashflow Machine';
  }

  private buildBlankDraft(account?: string): LedgerDraft {
    const today = new Date().toISOString().slice(0, 10);
    const draft: LedgerDraft = {
      account,
      trade_datetime: `${today}T09:30`,
      ticker: '',
      action: 'Open',
      strategy: 'Cashflow Machine',
      side: 'Call',
      contracts: undefined,
      strike: undefined,
      expiry: undefined,
      premium: undefined,
    };
    this.enforceSideForStrategy(draft);
    return draft;
  }

  private toNumber(value: number | string | undefined): number | undefined {
    if (value === undefined || value === null) {
      return undefined;
    }

    const asNumber = typeof value === 'string' ? parseFloat(value) : value;
    return Number.isFinite(asNumber) ? Number(asNumber) : undefined;
  }

  private normalizeAccountOption(option: AccountOption): AccountOption {
    const normalizedName = option.name.toLowerCase();
    if (normalizedName.includes('travis')) {
      return { ...option, label: 'Travis' };
    }
    if (normalizedName.includes('christie')) {
      return { ...option, label: 'Christie' };
    }
    return option;
  }

  private enforceSideForStrategy(target?: LedgerDraft): void {
    const draft = target ?? this.tradeDraft;
    if (draft && draft.strategy === 'Cashflow Machine') {
      draft.side = 'Call';
    }
  }

  private sortLedgerRows(rows: LedgerRow[]): LedgerRow[] {
    return [...rows].sort((a, b) => {
      const da = a.date ? new Date(a.date).getTime() : 0;
      const db = b.date ? new Date(b.date).getTime() : 0;
      return db - da;
    });
  }

  private updateLedgerFilterOptions(summaries: LedgerSummary[]): void {
    const tickers = new Set<string>();
    const sides = new Set<string>();
    const strikes = new Set<string>();
    const expiries = new Set<string>();

    summaries.forEach((summary) => {
      if (summary.ticker) {
        tickers.add(summary.ticker.toUpperCase());
      }
      const side = this.normalizeSideOption(summary.side);
      if (side) {
        sides.add(side);
      }
      const strike = this.formatStrikeOption(summary.strike);
      if (strike) {
        strikes.add(strike);
      }
      const expiry = this.normalizeExpiryOption(summary.expiry);
      if (expiry) {
        expiries.add(expiry);
      }
    });

    this.tickerFilterOptions = Array.from(tickers).sort();
    if (this.selectedTickers.length) {
      const available = new Set(this.tickerFilterOptions);
      this.selectedTickers = this.selectedTickers.filter((ticker) => available.has(ticker));
    }

    this.sideFilterOptions = Array.from(sides).sort();
    if (this.selectedSides.length) {
      const available = new Set(this.sideFilterOptions);
      this.selectedSides = this.selectedSides.filter((side) => available.has(side));
    }

    this.strikeFilterOptions = Array.from(strikes).sort((a, b) => Number(a) - Number(b));
    if (this.selectedStrikes.length) {
      const available = new Set(this.strikeFilterOptions);
      this.selectedStrikes = this.selectedStrikes.filter((strike) => available.has(strike));
    }

    this.expiryFilterOptions = Array.from(expiries).sort((a, b) => {
      if (a === '—') return 1;
      if (b === '—') return -1;
      return b.localeCompare(a);
    });
    if (this.selectedExpiries.length) {
      const available = new Set(this.expiryFilterOptions);
      this.selectedExpiries = this.selectedExpiries.filter((expiry) => available.has(expiry));
    }
  }

  private normalizeSideOption(value: string | undefined): string {
    if (!value) {
      return '';
    }
    const normalized = value.trim().toLowerCase();
    if (!normalized) {
      return '';
    }
    if (normalized.includes('put')) {
      return 'Put';
    }
    if (normalized.includes('call')) {
      return 'Call';
    }
    return value.trim();
  }

  private formatStrikeOption(value: number | null | undefined): string {
    if (!value || !Number.isFinite(value)) {
      return '';
    }
    const rounded = Math.round(value * 100) / 100;
    let label = rounded.toFixed(2);
    label = label.replace(/\.00$/, '');
    label = label.replace(/(\.\d)0$/, '$1');
    return label;
  }

  private normalizeExpiryOption(value: string | null | undefined): string {
    const trimmed = (value || '').trim();
    return trimmed || '—';
  }

  calculateJuicePerContract(row: LedgerRow): number | null {
    const premium = this.toNumber(row.premium_buyback);
    if (premium === undefined) {
      return null;
    }
    const strike = this.toNumber(row.strike);
    const underlying = this.toNumber(row.underlying);
    const side = (row.side || '').toString().toLowerCase();
    const isPut = side.includes('put');
    const action = (row.action || '').toString().toLowerCase();
    const isClose = action.includes('close');

    let juice: number;
    if (strike !== undefined && underlying !== undefined) {
      const intrinsic = isPut ? Math.max(0, strike - underlying) : Math.max(0, underlying - strike);
      const extrinsic = premium - intrinsic;
      juice = isClose ? (extrinsic < 0 ? Math.abs(extrinsic) : -extrinsic) : extrinsic;
    } else {
      juice = isClose ? (premium < 0 ? Math.abs(premium) : -premium) : premium;
    }

    return this.roundTo2(juice);
  }

  calculateSignedJuice(row: LedgerRow): number | null {
    const perContract = this.calculateJuicePerContract(row);
    if (perContract === null) {
      return null;
    }
    const contracts = this.toNumber(row.contracts);
    if (contracts === undefined) {
      return null;
    }
    return this.roundTo2(perContract * contracts);
  }

  calculateSignedJuicePer100(row: LedgerRow): number | null {
    const signed = this.calculateSignedJuice(row);
    if (signed === null) {
      return null;
    }
    return this.roundTo2(signed * 100);
  }

  private roundTo2(value: number): number {
    return Math.round(value * 100) / 100;
  }

  private filteredLedgerRows(): LedgerRow[] {
    if (!this.ledgerOpenOnly) {
      return this.ledgerRows;
    }
    const openBaseKeys = new Set(
      Object.entries(this.ledgerOpenBalances)
        .filter(([, info]) => (info.remaining ?? 0) > 0)
        .map(([key]) => key)
    );
    return this.ledgerRows.filter((row) => {
      const baseKey = this.extractBaseKey(row);
      if (!baseKey || !openBaseKeys.has(baseKey)) {
        return false;
      }
      const action = (row.action || '').toLowerCase();
      return !action.includes('close');
    });
  }

  private filteredLedgerSummaries(): LedgerSummary[] {
    let summaries = this.ledgerSummaries;
    if (this.selectedTickers.length) {
      const selected = new Set(this.selectedTickers);
      summaries = summaries.filter((summary) => selected.has((summary.ticker || '').toUpperCase()));
    }
    if (this.selectedSides.length) {
      const selected = new Set(this.selectedSides);
      summaries = summaries.filter((summary) => selected.has(this.normalizeSideOption(summary.side)));
    }
    if (this.selectedStrikes.length) {
      const selected = new Set(this.selectedStrikes);
      summaries = summaries.filter((summary) =>
        selected.has(this.formatStrikeOption(summary.strike))
      );
    }
    if (this.selectedExpiries.length) {
      const selected = new Set(this.selectedExpiries);
      summaries = summaries.filter((summary) =>
        selected.has(this.normalizeExpiryOption(summary.expiry))
      );
    }
    if (this.ledgerOpenOnly) {
      summaries = summaries.filter((summary) => summary.netContracts > 0);
    }
    return this.sortSummaries(summaries);
  }

  private computeOpenBalances(rows: LedgerRow[]): Record<string, { remaining: number; row: LedgerRow }> {
    const balances: Record<string, { remaining: number; row: LedgerRow }> = {};
    rows.forEach((row) => {
      const baseKey = this.extractBaseKey(row);
      if (!baseKey) {
        return;
      }
      const contracts = Number(row.contracts || 0);
      if (!Number.isFinite(contracts)) {
        return;
      }
      const action = (row.action || '').toLowerCase();
      const delta = action.includes('close') ? -contracts : contracts;
      const prev = balances[baseKey]?.remaining ?? 0;
      balances[baseKey] = {
        remaining: prev + delta,
        row,
      };
    });
    return balances;
  }

  private extractBaseKey(row: LedgerRow): string | null {
    if (row.key) {
      const parts = row.key.split('|');
      if (parts.length >= 4) {
        return parts.slice(0, 4).join('|');
      }
    }
    if (row.ticker && row.strike !== undefined && row.expiry && row.side) {
      return `${row.ticker}|${row.strike}|${row.expiry}|${row.side}`.toUpperCase();
    }
    return null;
  }

  private buildLedgerSummaries(rows: LedgerRow[]): LedgerSummary[] {
    const groups: Record<string, LedgerSummary> = {};

    rows.forEach((row) => {
      const baseKey = this.extractBaseKey(row);
      if (!baseKey) {
        return;
      }

      const existing = groups[baseKey];
      const action = (row.action || '').toLowerCase();
      const isClose = action.includes('close');
      const contracts = Number(row.contracts || 0);
      const premium = Number(row.premium_buyback || 0);
      const signedJuice = this.calculateSignedJuice(row) ?? 0;

      if (!groups[baseKey]) {
        groups[baseKey] = {
          key: baseKey,
          ticker: row.ticker,
          side: row.side || '',
          strike: row.strike || 0,
          expiry: row.expiry || null,
          netContracts: 0,
          netPremium: 0,
          netJuice: 0,
          netJuicePer100: 0,
          rows: [],
        };
      }

      const summary = groups[baseKey];
      const contractDelta = isClose ? -contracts : contracts;
      const premiumDelta = isClose ? -premium : premium;

      summary.netContracts += contractDelta;
      summary.netPremium += premiumDelta;
      summary.netJuice += signedJuice;
      summary.rows.push(row);
    });

    Object.values(groups).forEach((summary) => {
      summary.netJuice = this.roundTo2(summary.netJuice);
      summary.netPremium = this.roundTo2(summary.netPremium);
      summary.netJuicePer100 = this.roundTo2(summary.netJuice * 100);
    });

    return Object.values(groups);
  }

  private computeExpiryTotals(summaries: LedgerSummary[]): ExpiryTotal[] {
    const grouped: Record<string, ExpiryTotal> = {};
    summaries.forEach((summary) => {
      // Only include fully paired positions (netContracts == 0) in expiry totals.
      if (summary.netContracts !== 0) {
        return;
      }

      const key = summary.expiry || '—';
      if (!grouped[key]) {
        grouped[key] = {
          expiry: key,
          netContracts: 0,
          netPremium: 0,
          netJuice: 0,
          netJuicePer100: 0,
        };
      }
      const bucket = grouped[key];
      bucket.netContracts += summary.netContracts;
      bucket.netPremium += summary.netPremium;
      bucket.netJuice += summary.netJuice;
    });

    return Object.values(grouped)
      .map((item) => ({
        ...item,
        netJuicePer100: item.netJuice * 100,
      }))
      .sort((a, b) => {
        if (a.expiry === '—') return 1;
        if (b.expiry === '—') return -1;
        return b.expiry.localeCompare(a.expiry);
      });
  }

  private sortSummaries(list: LedgerSummary[]): LedgerSummary[] {
    const orders = this.ledgerSortOrder;
    const sorted = [...list].sort((a, b) => {
      for (const { column, direction } of orders) {
        const va = this.getSummarySortValue(a, column);
        const vb = this.getSummarySortValue(b, column);

        let cmp: number;
        if (typeof va === 'number' && typeof vb === 'number') {
          cmp = va - vb;
        } else {
          cmp = String(va ?? '').localeCompare(String(vb ?? ''), undefined, { sensitivity: 'base' });
        }

        if (cmp !== 0) {
          return direction === 'asc' ? cmp : -cmp;
        }
      }

      // Fallback: most recent date first
      const da = this.getSummarySortValue(a, 'date') as number;
      const db = this.getSummarySortValue(b, 'date') as number;
      return db - da;
    });

    return sorted;
  }

  private getSummarySortValue(
    summary: LedgerSummary,
    column:
      | 'date'
      | 'ticker'
      | 'side'
      | 'strike'
      | 'expiry'
      | 'netContracts'
      | 'netPremium'
      | 'netJuice'
      | 'netJuicePer100'
  ): string | number {
    switch (column) {
      case 'ticker':
        return summary.ticker || '';
      case 'side':
        return summary.side || '';
      case 'strike':
        return summary.strike ?? 0;
      case 'expiry':
        return summary.expiry || '';
      case 'netContracts':
        return summary.netContracts;
      case 'netPremium':
        return summary.netPremium;
      case 'netJuice':
        return summary.netJuice;
      case 'netJuicePer100':
        return summary.netJuicePer100;
      case 'date':
      default: {
        const latest = summary.rows
          .map((r) => (r.date ? new Date(r.date).getTime() : 0))
          .reduce((max, curr) => Math.max(max, curr), 0);
        return latest;
      }
    }
  }
}
