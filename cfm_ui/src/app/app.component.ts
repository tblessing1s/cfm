import { Component, OnInit } from '@angular/core';

import {
  AccountOption,
  DashboardMetrics,
  DashboardService,
  LedgerEntryCreate,
  LedgerRow,
  BusinessDashboard,
  PositionMetrics,
  NavSnapshot,
  BasePosition,
  BaseLeg,
  ReserveRow,
  ReplacementCost,
  Trade,
  PortfolioSummary,
  StockSummaryRow,
  StockDetail,
  RegimeEntry,
  ProtectionMetrics,
} from './services/dashboard.service';
import {
  ExpiryMonthGroup,
  ExpiryTotal,
  LedgerSummary,
  LedgerSortOrder,
  buildLedgerSummaries,
  calculateJuicePerContract,
  calculateProtectionRaw,
  calculateSignedJuiceRaw,
  computeExpiryTotals,
  extractBaseKey,
  formatStrikeOption,
  normalizeExpiryOption,
  normalizeSideOption,
  roundTo2,
  sortLedgerRows,
  sortSummaries,
} from './utils/ledger-utils';

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
  condition?: string;
  base_position_id?: string;
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent implements OnInit {
  accounts: AccountOption[] = [];
  selectedAccount?: string;
  activePage: 'business' | 'data' | 'trades' = 'business';
  metrics?: DashboardMetrics;
  businessMetrics?: BusinessDashboard;
  portfolioSummary?: PortfolioSummary;
  stockRows: StockSummaryRow[] = [];
  portfolioExpiryStart = '';
  portfolioExpiryEnd = '';
  portfolioExpiryMin?: string;
  portfolioExpiryMax?: string;
  selectedStock?: string;
  stockDetail?: StockDetail;
  stockDetailLoading = false;
  positionMetrics: PositionMetrics[] = [];
  showClosedBases = false;
  showClosedStocks = false;
  showAdvanced = false;
  showRegimeDialog = false;
  showPlanDialog = false;
  showRegimeForm = false;
  selectedTradePositionId?: string;
  tradeTickerLocked = false;
  tradeStrategyLocked = false;
  tradeSideLocked = false;
   tradeActionLocked = false;
   tradeStrikeLocked = false;
   tradeExpiryLocked = false;
   selectedOpenShortKey?: string;
   openShortOptions: {
     key: string;
     base_position_id?: string | null;
     ticker?: string | null;
     side?: string | null;
     strike?: number | null;
     expiry?: string | null;
     remaining: number;
     label: string;
   }[] = [];
   availableOpenShorts: {
     key: string;
     base_position_id?: string | null;
     ticker?: string | null;
     side?: string | null;
     strike?: number | null;
     expiry?: string | null;
     remaining: number;
     label: string;
   }[] = [];
  currentMarketCondition: 'RED' | 'YELLOW' | 'GREEN' = 'RED';
  currentStockCondition: 'RED' | 'YELLOW' | 'GREEN' = 'RED';
  marketConditionDraft: 'RED' | 'YELLOW' | 'GREEN' = 'RED';
  stockConditionDraft: 'RED' | 'YELLOW' | 'GREEN' | '-' = '-';
  selectedStockForRegime: string | '-' = '-';
  latestRegimeBySymbol: Record<string, RegimeEntry> = {};
  regimeDraft: RegimeEntry = {
    date: new Date().toISOString().slice(0, 10),
    symbol: '',
    stock_score: 0,
    market_score: 0,
    stock_condition: 'RED',
    market_condition: 'RED',
  };
  regimeEntries: RegimeEntry[] = [];
  protection?: ProtectionMetrics;
  // Single display mode: always show totals and /100 for premium/juice/protection
  displayMode: 'all_contracts_per100' = 'all_contracts_per100';
  private readonly contractMultiplier = 100;
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
  ledgerSortOrder: LedgerSortOrder = [{ column: 'date', direction: 'desc' }];
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

  // Business forms
  navDraft: NavSnapshot = this.buildBlankNav();
  navCash?: number;
  navPositions?: number;
  navLiabilities?: number;
  baseDraft: BasePosition = this.buildBlankBase();
  closingBaseId?: string;
  baseTypeOptions = ['SHARES', 'LONG_OPTION', 'OTHER'];
  strategyOptions = ['CFM', 'JL', 'DD', 'OTHER'];
  baseLegDraft: BaseLeg = this.buildBlankBaseLeg();
  baseLegOptions: BaseLeg[] = [];
  selectedBaseLegId: string = '';
  baseLegDateTime?: string;
  legSideOptions = ['BUY', 'SELL'];
  legTagOptions = ['OPEN', 'CLOSE'];
  conditionOptions = ['GREEN', 'YELLOW', 'RED'];
  tradeConditionOptions = ['GREEN', 'YELLOW', 'RED'];
  reserveDraft: ReserveRow = this.buildBlankReserve();
  replacementDraft: ReplacementCost = this.buildBlankReplacement();
  selectedPositionId?: string;
  defaultReservePct = 0.05;
  navChartWidth = 360;
  navChartHeight = 120;
  // Targets for coloring
  weeklyYieldTargetPct = 0.5; // % of NAV
  monthlyYieldTargetPct = 2.0; // % of NAV
  selectedDataForm: 'nav' | 'base' | 'leg' = 'nav';
  dataFormHelp: Record<string, { label: string; when: string }> = {
    nav: { label: 'Account value snapshot', when: 'Log account net liq (NAV) weekly or daily; include free cash, deposits, withdrawals.' },
    base: { label: 'Base position', when: 'Create once per engine/symbol before logging base legs or reserves.' },
    leg: { label: 'Base leg', when: 'Whenever you buy/sell/roll the base (shares/long options).' },
    reserve: { label: 'Reserve', when: 'When you earmark cash for a base or adjust required reserves.' },
    replacement: { label: 'Replacement cost', when: 'When you update manual replacement pricing for a base.' },
  };
  visibleHelp: string | null = null;
  fieldHelp: Record<string, string> = {
    nav_cash: 'Unencumbered cash/buying power you can deploy right now.',
    nav_positions: 'Mark-to-market value of long holdings only (exclude shorts/credit legs).',
    nav_liabilities: 'Borrow/margin debits or obligations that reduce net liq.',
    nav_nav: 'Computed: cash on hand + positions value − liabilities/margin.',
    nav_deposits: 'New money added since the last snapshot.',
    nav_withdrawals: 'Cash removed since the last snapshot.',
    base_symbol: 'Ticker for this base engine (e.g., SPY, AAPL).',
    base_strategy: 'Label like CFM / JL / DD to tag the engine.',
    base_type: 'SHARES / LONG_OPTION / OTHER to describe the base.',
    base_opened: 'When you started this base engine.',
    base_closed: 'When this base was closed/retired; closed bases are hidden from selection.',
    leg_position: 'Base position this leg belongs to.',
    leg_side: 'BUY or SELL for the base leg.',
    leg_tag: 'OPEN / ROLL_OUT / ROLL_IN / CLOSE / ADD / REDUCE.',
    leg_price: 'Price paid/received per unit (share or contract) for the base leg.',
    leg_fees: 'Commissions/fees associated with this base leg.',
    leg_amount: 'Signed cash flow for the leg (BUY negative, SELL positive).',
    leg_condition: 'Condition when logging this leg: GREEN (growth OK), YELLOW/RED (stay in cash).',
    reserve_position: 'Base position this reserve is tied to.',
    reserve_cash: 'Cash earmarked for this base to cover rolls/assignments.',
    reserve_note: 'Rule or reason for this reserve.',
    replacement_position: 'Base position this replacement cost applies to.',
    replacement_same: 'Cost to rebuild the entire base at current prices.',
    replacement_unit: 'Cost per unit (share/contract) to rebuild.',
  };
  businessError?: string;
  businessSuccess?: string;

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
          this.loadPortfolio();
          this.loadBusiness();
          this.loadRegimes();
          if (this.selectedStock) {
            this.loadProtection(this.selectedStock);
          }
          this.loadLedger(this.selectedAccount);
          this.setPage('business');
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

  setPage(page: 'business' | 'data' | 'trades'): void {
    this.activePage = page;
    if (page === 'business' && this.selectedAccount) {
      this.loadPortfolio();
      this.loadBusiness();
    }
    if (page === 'trades' && this.selectedAccount) {
      this.loadMetrics();
      this.loadLedger(this.selectedAccount);
    }
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
        this.loadBusiness();
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

  loadPortfolio(): void {
    if (!this.selectedAccount) {
      return;
    }
    const expiryStart = this.portfolioExpiryStart || undefined;
    const expiryEnd = this.portfolioExpiryEnd || undefined;
    this.dashboardService.getPortfolioSummary(this.selectedAccount, this.showClosedStocks, expiryStart, expiryEnd).subscribe({
      next: (summary) => {
        this.portfolioSummary = summary;
        this.stockRows = summary.stocks || [];
        if (this.selectedStock) {
          const exists = this.stockRows.some((r) => r.ticker === this.selectedStock);
          if (!exists) {
            this.selectedStock = undefined;
            this.stockDetail = undefined;
          }
        }
      },
      error: () => {
        this.portfolioSummary = undefined;
        this.stockRows = [];
      },
    });
  }

  selectStock(ticker: string): void {
    this.selectedStock = ticker;
    if (!ticker || !this.selectedAccount) {
      this.stockDetail = undefined;
      return;
    }
    const expiryStart = this.portfolioExpiryStart || undefined;
    const expiryEnd = this.portfolioExpiryEnd || undefined;
    this.stockDetailLoading = true;
    this.dashboardService
      .getStockDetail(ticker, this.selectedAccount, this.showClosedStocks, expiryStart, expiryEnd)
      .subscribe({
        next: (detail) => {
          this.stockDetail = detail;
          this.stockDetailLoading = false;
          this.loadProtection(ticker);
          this.loadRegimes();
        },
        error: () => {
          this.stockDetail = undefined;
          this.stockDetailLoading = false;
        },
      });
  }

  goToTradesForStock(ticker: string): void {
    this.selectedTickers = ticker ? [ticker] : [];
    this.setPage('trades');
  }

  loadLedger(account: string): void {
    this.ledgerLoading = true;
    this.ledgerError = undefined;
    this.dashboardService.getLedger(account).subscribe({
      next: (rows) => {
        this.ledgerRows = sortLedgerRows(rows);
        this.ledgerOpenBalances = this.computeOpenBalances(this.ledgerRows);
        this.ledgerSummaries = buildLedgerSummaries(this.ledgerRows, this.contractMultiplier);
        this.refreshOpenShortOptions();
        this.updateLedgerFilterOptions(this.ledgerSummaries);
        this.updatePortfolioExpiryOptions(this.ledgerRows);
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

  loadBusiness(): void {
    if (!this.selectedAccount) {
      return;
    }
    const expiryStart = this.portfolioExpiryStart || undefined;
    const expiryEnd = this.portfolioExpiryEnd || undefined;
    this.dashboardService.getBusinessDashboard(this.selectedAccount, expiryStart, expiryEnd).subscribe({
      next: (data) => {
        this.businessMetrics = data;
      },
      error: () => {
        this.businessMetrics = undefined;
      },
    });
    this.dashboardService
      .listPositionMetrics(this.selectedAccount, this.showClosedBases, expiryStart, expiryEnd)
      .subscribe({
        next: (rows) => {
          this.positionMetrics = this.showClosedBases
            ? rows
            : rows.filter((pm) => !pm.position.closed_date);
          // Ensure selectedPositionId stays valid
          if (this.selectedPositionId) {
            const exists = rows.some((pm) => pm.position.position_id === this.selectedPositionId);
            if (!exists) {
              this.selectedPositionId = undefined;
            }
          }
          if (this.selectedPositionId) {
            this.applyReserveDefault(this.selectedPositionId);
          }
        },
        error: () => {
          this.positionMetrics = [];
        },
      });
  }

  private computeConditions(): void {
    const scoreMap: Record<string, number> = { GREEN: 3, YELLOW: 2, RED: 1 };
    this.regimeDraft.stock_score = scoreMap[this.regimeDraft.stock_condition] ?? 0;
    this.regimeDraft.market_score = scoreMap[this.regimeDraft.market_condition] ?? 0;
  }

  loadRegimes(): void {
    this.dashboardService.listRegimeEntries().subscribe({
      next: (rows) => {
        this.regimeEntries = rows.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        this.updateConditionChips();
      },
      error: () => {
        this.regimeEntries = [];
        this.updateConditionChips();
      },
    });
  }

  saveRegime(): void {
    // legacy single-entry save; keep for compatibility
    this.computeConditions();
    const payload: RegimeEntry = {
      ...this.regimeDraft,
      symbol: (this.regimeDraft.symbol || this.selectedStock || '').toUpperCase(),
    };
    this.dashboardService.createRegimeEntry(payload).subscribe({
      next: (row) => {
        this.regimeEntries = [row, ...this.regimeEntries];
        this.updateConditionChips();
        this.showRegimeDialog = false;
      },
    });
  }

  loadProtection(symbol: string): void {
    if (!symbol) return;
    const expiryStart = this.portfolioExpiryStart || undefined;
    const expiryEnd = this.portfolioExpiryEnd || undefined;
    this.dashboardService.getProtectionMetrics(symbol, this.selectedAccount, undefined, expiryStart, expiryEnd).subscribe({
      next: (data) => (this.protection = data),
      error: () => (this.protection = undefined),
    });
  }

  onTradePositionSelect(positionId?: string): void {
    this.selectedTradePositionId = positionId || undefined;
    if (!positionId) {
      this.tradeTickerLocked = false;
      this.tradeStrategyLocked = false;
      this.tradeSideLocked = false;
      this.tradeActionLocked = false;
      this.tradeStrikeLocked = false;
      this.tradeExpiryLocked = false;
      this.selectedOpenShortKey = undefined;
      this.availableOpenShorts = [];
      this.tradeDraft.side = 'Call';
      this.tradeDraft.ticker = '';
      this.tradeDraft.strategy = '';
      this.tradeDraft.base_position_id = undefined;
      return;
    }
    const pm = this.positionMetrics.find((p) => p.position.position_id === positionId);
    if (pm) {
      this.tradeDraft.ticker = pm.position.symbol;
      this.tradeDraft.strategy = pm.position.strategy || this.tradeDraft.strategy;
      this.tradeDraft.side = 'Call';
      this.tradeDraft.base_position_id = pm.position.position_id;
      this.tradeTickerLocked = true;
      this.tradeStrategyLocked = true;
      this.tradeSideLocked = pm.position.strategy === 'CFM';
      this.tradeActionLocked = false;
      this.tradeStrikeLocked = false;
      this.tradeExpiryLocked = false;
      this.selectedOpenShortKey = undefined;
      this.updateAvailableOpenShorts();
    }
  }

  updateConditionChips(): void {
    this.latestRegimeBySymbol = {};
    const MARKET_KEY = '__MARKET__';
    // Track latest per symbol; blank symbol entries treated as market-level
    for (const entry of this.regimeEntries) {
      const sym = (entry.symbol && entry.symbol.trim() ? entry.symbol.toUpperCase() : MARKET_KEY);
      const existing = this.latestRegimeBySymbol[sym];
      const existingDate = existing ? new Date(existing.date) : null;
      const incomingDate = new Date(entry.date);
      if (!existing || incomingDate > (existingDate as Date)) {
        this.latestRegimeBySymbol[sym] = entry;
      }
    }
    // Latest market: newest entry whose symbol is empty
    const marketEntry =
      this.regimeEntries
        .filter((r) => !r.symbol || !r.symbol.trim())
        .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())[0] || this.latestRegimeBySymbol[MARKET_KEY];
    this.currentMarketCondition = ((marketEntry?.market_condition as any) || 'RED').toUpperCase() as any;
    const selectedSymbol = (this.selectedStock || '').toUpperCase();
    const stockEntry = selectedSymbol ? this.latestRegimeBySymbol[selectedSymbol] : undefined;
    this.currentStockCondition = (stockEntry?.stock_condition as any) || 'RED';
  }

  openRegimeDialog(): void {
    this.regimeDraft.symbol = this.selectedStock || '';
    this.loadRegimes();
    if (!this.positionMetrics.length && this.selectedAccount) {
      this.loadBusiness();
    }
    this.showRegimeForm = false;
    this.selectedStockForRegime = '-';
    this.stockConditionDraft = '-';
    this.showRegimeDialog = true;
  }

  closeRegimeDialog(): void {
    this.showRegimeDialog = false;
  }

  toggleRegimeForm(show: boolean): void {
    this.showRegimeForm = show;
  }

  conditionClass(cond: string): string {
    const c = (cond || '').toUpperCase();
    return c === 'GREEN' ? 'green' : c === 'YELLOW' ? 'yellow' : 'red';
  }

  calcOverallFromConditions(
    marketCond: 'RED' | 'YELLOW' | 'GREEN',
    stockCond: 'RED' | 'YELLOW' | 'GREEN'
  ): 'RED' | 'YELLOW' | 'GREEN' {
    const m = (marketCond || 'RED').toUpperCase() as any;
    const s = (stockCond || 'RED').toUpperCase() as any;
    const combo = new Set([m, s]);
    if (combo.has('GREEN') && combo.has('RED')) {
      return 'YELLOW';
    }
    if (m === 'RED' || s === 'RED') return 'RED';
    if (m === 'YELLOW' || s === 'YELLOW') return 'YELLOW';
    return 'GREEN';
  }

  overallCondition(): 'RED' | 'YELLOW' | 'GREEN' {
    return this.calcOverallFromConditions(this.currentMarketCondition, this.currentStockCondition);
  }

  openPlanDialog(): void {
    this.showPlanDialog = true;
  }

  closePlanDialog(): void {
    this.showPlanDialog = false;
  }

  onStockSelect(value: string | '-'): void {
    this.selectedStockForRegime = value || '-';
    if (this.selectedStockForRegime === '-') {
      this.stockConditionDraft = '-';
    }
  }

  private buildPayload(
    symbol: string,
    stockCond: 'RED' | 'YELLOW' | 'GREEN' | '-',
    marketCond: 'RED' | 'YELLOW' | 'GREEN'
  ): RegimeEntry {
    const scoreMap: Record<string, number> = { GREEN: 3, YELLOW: 2, RED: 1 };
    const sc = stockCond === '-' ? 'RED' : stockCond;
    return {
      date: this.regimeDraft.date,
      symbol,
      stock_condition: stockCond,
      market_condition: marketCond,
      stock_score: scoreMap[sc],
      market_score: scoreMap[marketCond],
    };
  }

  saveCombinedRegime(): void {
    const symbol = (this.selectedStockForRegime && this.selectedStockForRegime !== '-' ? this.selectedStockForRegime : '') || '';
    const payload = this.buildPayload(
      symbol,
      symbol ? this.stockConditionDraft : '-',
      this.marketConditionDraft
    );
    this.dashboardService.createRegimeEntry(payload).subscribe({
      next: (row) => {
        this.regimeEntries = [row, ...this.regimeEntries];
        this.updateConditionChips();
        this.showRegimeForm = false;
      },
    });
  }

  onAccountChange(accountName: string): void {
    if (accountName === this.selectedAccount) {
      return;
    }

    this.selectedAccount = accountName;
    this.tradeDraft.account = accountName;
    this.selectedTradePositionId = undefined;
    this.tradeTickerLocked = false;
    this.tradeStrategyLocked = false;
    this.selectedTickers = [];
    this.selectedSides = [];
    this.selectedStrikes = [];
    this.selectedExpiries = [];
    this.portfolioExpiryStart = '';
    this.portfolioExpiryEnd = '';
    this.portfolioExpiryMin = undefined;
    this.portfolioExpiryMax = undefined;
    this.metrics = undefined;
    this.loadMetrics();
    this.loadPortfolio();
    this.loadBusiness();
    this.loadRegimes();
    if (this.selectedStock) {
      this.loadProtection(this.selectedStock);
    }
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

  onPortfolioExpiryRangeChange(): void {
    this.loadPortfolio();
    this.loadBusiness();
    if (this.selectedStock) {
      this.selectStock(this.selectedStock);
    }
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
      condition: this.tradeDraft.condition,
      base_position_id: this.selectedTradePositionId,
    };

    this.pendingTrades = [...this.pendingTrades, staged];
    this.entrySuccess = `Staged ${ticker} ${staged.action} for ${account}.`;
    this.tradeDraft = this.buildBlankDraft(account);
    this.tradeTickerLocked = !!this.selectedTradePositionId;
    this.tradeStrategyLocked = !!this.selectedTradePositionId;
    this.tradeSideLocked = this.tradeDraft.strategy === 'CFM' || !!this.selectedTradePositionId;
    this.tradeActionLocked = false;
    this.tradeStrikeLocked = false;
    this.tradeExpiryLocked = false;
    this.selectedOpenShortKey = undefined;
    this.updateAvailableOpenShorts();
  }

  submitNavSnapshot(): void {
    if (!this.selectedAccount || !this.navDraft.date) {
      this.businessError = 'Select account and date for NAV snapshot.';
      return;
    }
    this.recomputeNavTotal();
    this.navDraft.account = this.selectedAccount;
    this.dashboardService.createNavSnapshot(this.navDraft).subscribe({
      next: () => {
        this.businessSuccess = 'Saved NAV snapshot.';
        this.businessError = undefined;
        this.navDraft = this.buildBlankNav(this.selectedAccount);
        this.navCash = undefined;
        this.navPositions = undefined;
        this.navLiabilities = undefined;
        this.loadBusiness();
      },
      error: () => {
        this.businessError = 'Unable to save NAV snapshot.';
      },
    });
  }

  submitBasePosition(): void {
    if (!this.selectedAccount || !this.baseDraft.symbol) {
      this.businessError = 'Account and symbol are required for base.';
      return;
    }
    this.baseDraft.account = this.selectedAccount;
    // If closing an existing base, update it
    if (this.closingBaseId) {
      this.dashboardService.updateBasePosition(this.closingBaseId, this.baseDraft).subscribe({
        next: () => {
          this.businessSuccess = 'Closed base position.';
          this.businessError = undefined;
          this.baseDraft = this.buildBlankBase(this.selectedAccount);
          this.closingBaseId = undefined;
          this.loadBusiness();
        },
        error: () => {
          this.businessError = 'Unable to close base position.';
        },
      });
      return;
    }
    // Otherwise create new
    this.dashboardService.createBasePosition(this.baseDraft).subscribe({
      next: () => {
        this.businessSuccess = 'Saved base position.';
        this.businessError = undefined;
        this.baseDraft = this.buildBlankBase(this.selectedAccount);
        this.loadBusiness();
      },
      error: () => {
        this.businessError = 'Unable to save base position.';
      },
    });
  }

  submitBaseLeg(): void {
    const positionId = this.selectedPositionId || this.baseLegDraft.position_id;
    if (!positionId) {
      this.businessError = 'Select a base position before adding a base leg.';
      return;
    }
    // If updating an existing leg (selectedBaseLegId), treat it as a MARK unless explicitly closing.
    const payload = { ...this.baseLegDraft, position_id: positionId };
    if (this.selectedBaseLegId && payload.tag !== 'CLOSE') {
      payload.tag = 'MARK';
    }
    this.dashboardService.createBaseLeg(payload).subscribe({
      next: () => {
        this.businessSuccess = 'Saved base leg.';
        this.businessError = undefined;
        this.baseLegDraft = this.buildBlankBaseLeg();
        this.baseLegDraft.position_id = positionId;
        this.loadBaseLegOptions(positionId);
        this.loadBusiness();
      },
      error: () => {
        this.businessError = 'Unable to save base leg.';
      },
    });
  }

  submitReserve(): void {
    const positionId = this.selectedPositionId || this.reserveDraft.position_id;
    if (!positionId) {
      this.businessError = 'Select a base position before adding a reserve.';
      return;
    }
    const payload = { ...this.reserveDraft, position_id: positionId };
    this.dashboardService.createReserve(payload).subscribe({
      next: () => {
        this.businessSuccess = 'Saved reserve.';
        this.businessError = undefined;
        this.reserveDraft = this.buildBlankReserve();
        this.loadBusiness();
      },
      error: () => {
        this.businessError = 'Unable to save reserve.';
      },
    });
  }

  submitReplacement(): void {
    const positionId = this.selectedPositionId || this.replacementDraft.position_id;
    if (!positionId) {
      this.businessError = 'Select a base position before adding replacement cost.';
      return;
    }
    const payload = { ...this.replacementDraft, position_id: positionId };
    this.dashboardService.createReplacementCost(payload).subscribe({
      next: () => {
        this.businessSuccess = 'Saved replacement cost.';
        this.businessError = undefined;
        this.replacementDraft = this.buildBlankReplacement();
        this.loadBusiness();
      },
      error: () => {
        this.businessError = 'Unable to save replacement cost.';
      },
    });
  }

  setDataForm(form: 'nav' | 'base' | 'leg'): void {
    this.selectedDataForm = form;
    if (form === 'leg') {
      this.loadBaseLegOptions(this.selectedPositionId);
    }
  }

  onPositionSelect(positionId: string | undefined): void {
    this.selectedPositionId = positionId || undefined;
    const pid = this.selectedPositionId || '';
    this.baseLegDraft.position_id = pid;
    this.reserveDraft.position_id = pid;
    this.replacementDraft.position_id = pid;
    this.selectedBaseLegId = '';
    this.baseLegOptions = [];
    if (this.selectedDataForm === 'leg' && pid) {
      this.loadBaseLegOptions(pid);
    }
    if (pid) {
      this.applyReserveDefault(pid);
    }
  }

  onBaseSelectForClose(positionId: string | undefined): void {
    if (!positionId) {
      this.closingBaseId = undefined;
      this.baseDraft = this.buildBlankBase(this.selectedAccount);
      return;
    }
    this.closingBaseId = positionId;
    const pm = this.positionMetrics.find((p) => p.position.position_id === positionId);
    if (pm) {
      this.baseDraft = {
        position_id: pm.position.position_id,
        account: pm.position.account,
        symbol: pm.position.symbol,
        strategy: pm.position.strategy,
        base_type: pm.position.base_type,
        opened_date: pm.position.opened_date,
        closed_date: pm.position.closed_date,
      };
    }
  }

  recomputeNavTotal(): void {
    const cash = this.toNumber(this.navCash);
    const positions = this.toNumber(this.navPositions);
    const liabilities = this.toNumber(this.navLiabilities) || 0;
    if (cash !== undefined || positions !== undefined || liabilities !== undefined) {
      const total = (cash || 0) + (positions || 0) - liabilities;
      this.navDraft.nav_total = Math.round(total * 100) / 100;
      this.navDraft.nav_cash = cash;
      this.navDraft.nav_long_value = positions;
      this.navDraft.nav_liabilities = liabilities || undefined;
    }
  }

  toggleHelp(key: string): void {
    this.visibleHelp = this.visibleHelp === key ? null : key;
  }

  onBaseLegDateTimeChange(value: string): void {
    this.baseLegDateTime = value;
    if (value) {
      const [d, t] = value.split('T');
      this.baseLegDraft.date = d;
      this.baseLegDraft.time = t ? t.slice(0, 5) : this.baseLegDraft.time;
    }
  }

  recomputeBaseLegAmount(): void {
    const qty = this.toNumber(this.baseLegDraft.quantity) || 0;
    const price = this.toNumber(this.baseLegDraft.price) || 0;
    const fees = this.toNumber(this.baseLegDraft.fees) || 0;
    const instr = (this.baseLegDraft.instrument_type || '').toString().toUpperCase();
    const mult = instr === 'OPTION' ? 100 : 1;
    const gross = Math.abs(price * qty * mult);
    const total = gross + Math.abs(fees);
    this.baseLegDraft.amount = Math.round(total * 100) / 100;
  }

  applyReserveDefault(positionId: string): void {
    const pm = this.positionMetrics.find((p) => p.position.position_id === positionId);
    if (!pm) {
      return;
    }
    const baseValue = pm.base_value || 0;
    const suggested = baseValue * this.defaultReservePct;
    this.reserveDraft.reserved_cash = Math.round(suggested * 100) / 100;
  }

  rrClass(value?: number | null): string {
    if (value === undefined || value === null) return 'badge-neutral';
    if (value >= 1.1) return 'badge-green';
    if (value >= 1.0) return 'badge-yellow';
    return 'badge-red';
  }

  reserveCoverageClass(value?: number | null): string {
    if (value === undefined || value === null) return 'badge-neutral';
    if (value >= 1.0) return 'badge-green';
    if (value >= 0.9) return 'badge-yellow';
    return 'badge-red';
  }

  modeClass(mode?: string | null): string {
    if (!mode) return 'badge-neutral';
    if (mode === 'SCALE_READY') return 'badge-green';
    if (mode === 'STRENGTHEN') return 'badge-red';
    return 'badge-yellow';
  }

  incomeAllowedClass(allowed?: boolean | null, value?: number | null): string {
    if (!allowed || !value || value <= 0) return 'badge-red';
    return 'badge-green';
  }

  incomeClass(value?: number | null, allowed?: boolean | null): string {
    if (value === undefined || value === null) return 'badge-neutral';
    if (allowed && value > 0) return 'badge-green';
    return 'badge-red';
  }

  yieldClass(valuePct: number | undefined, target: number): string {
    if (valuePct === undefined || valuePct === null) return 'badge-neutral';
    const v = valuePct;
    if (v >= target) return 'badge-green';
    if (v >= target * 0.75) return 'badge-yellow';
    return 'badge-red';
  }

  navSeriesForChart(): any[] {
    if (this.businessMetrics?.nav_weekly && this.businessMetrics.nav_weekly.length > 1) {
      return this.businessMetrics.nav_weekly;
    }
    return this.businessMetrics?.nav_monthly || [];
  }

  navSeriesLabel(): string {
    if (this.businessMetrics?.nav_weekly && this.businessMetrics.nav_weekly.length > 1) {
      return 'Weekly';
    }
    if (this.businessMetrics?.nav_monthly?.length) {
      return 'Monthly';
    }
    return '';
  }

  navPath(points: any[] | undefined, key: 'nav_total' | 'nav_cash' | 'nav_long_value'): string {
    if (!points || points.length < 2) {
      return '';
    }
    const values = points
      .map((p) => this.toNumber((p as any)[key]))
      .filter((v) => v !== undefined) as number[];
    if (values.length < 2) {
      return '';
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const step = points.length > 1 ? this.navChartWidth / (points.length - 1) : this.navChartWidth;
    let d = '';
    points.forEach((pt, idx) => {
      const val = this.toNumber((pt as any)[key]);
      if (val === undefined) {
        return;
      }
      const x = idx * step;
      const y = this.navChartHeight - ((val - min) / range) * this.navChartHeight;
      d += `${d ? ' L ' : 'M '}${x.toFixed(1)} ${y.toFixed(1)}`;
    });
    return d;
  }

  navStartLabel(): string {
    const series = this.navSeriesForChart();
    return series.length ? series[0]?.period_start : '';
  }

  navEndLabel(): string {
    const series = this.navSeriesForChart();
    return series.length ? series[series.length - 1]?.period_start : '';
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
    this.tradeActionLocked = false;
    this.tradeStrikeLocked = false;
    this.tradeExpiryLocked = false;
    this.selectedOpenShortKey = undefined;

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
      condition: row.condition || row.notes || undefined,
      base_position_id: row.base_position_id,
    };
    if (row.base_position_id) {
      this.selectedTradePositionId = row.base_position_id;
      this.tradeTickerLocked = true;
      this.tradeStrategyLocked = true;
      this.tradeSideLocked = this.tradeDraft.strategy === 'CFM';
    } else {
      this.selectedTradePositionId = undefined;
      this.tradeTickerLocked = false;
      this.tradeStrategyLocked = false;
      this.tradeSideLocked = false;
    }
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
      base_position_id: this.selectedTradePositionId,
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
    this.selectedTradePositionId = undefined;
    this.tradeTickerLocked = false;
    this.tradeStrategyLocked = false;
    this.tradeSideLocked = false;
    this.tradeActionLocked = false;
    this.tradeStrikeLocked = false;
    this.tradeExpiryLocked = false;
    this.selectedOpenShortKey = undefined;
    this.updateAvailableOpenShorts();
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
    return computeExpiryTotals(this.filteredLedgerSummaries(), this.contractMultiplier);
  }

  get expiryMonthGroups(): ExpiryMonthGroup[] {
    const totals = computeExpiryTotals(this.filteredLedgerSummaries(), this.contractMultiplier);
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
          netProtection: 0,
          children: [],
        };
      }
      const bucket = groups[monthKey];
      bucket.children.push(total);
      bucket.netContracts += total.netContracts;
      bucket.netPremium += total.netPremium;
      bucket.netJuice += total.netJuice;
      bucket.netProtection += total.netProtection;
    });

    return Object.values(groups)
      .map((group) => ({
        ...group,
        netJuicePer100: group.netJuice * 100,
        netProtection: roundTo2(group.netProtection),
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
      condition: undefined,
      base_position_id: undefined,
    };
    this.enforceSideForStrategy(draft);
    return draft;
  }

  private buildBlankNav(account?: string): NavSnapshot {
    const today = new Date().toISOString().slice(0, 10);
    return {
      account: account || '',
      date: today,
      nav_cash: undefined,
      nav_long_value: undefined,
      nav_liabilities: undefined,
      nav_total: 0,
      deposits: 0,
      withdrawals: 0,
    };
  }

  private buildBlankBase(account?: string): BasePosition {
    const today = new Date().toISOString().slice(0, 10);
    return {
      position_id: '',
      account: account || '',
      symbol: '',
      strategy: 'CFM',
      base_type: 'SHARES',
      opened_date: today,
      closed_date: undefined,
    };
  }

  private buildBlankBaseLeg(): BaseLeg {
    const today = new Date().toISOString().slice(0, 10);
    this.baseLegDateTime = `${today}T09:30`;
    return {
      base_leg_id: this.newId(),
      position_id: '',
      date: today,
      time: '09:30',
      instrument_type: 'SHARES',
      side: 'BUY',
      quantity: 0,
      strike: undefined,
      expiry: undefined,
      price: 0,
      fees: 0,
      amount: 0,
      tag: 'OPEN',
      condition: undefined,
    };
  }

  private newId(): string {
    if ((crypto as any)?.randomUUID) {
      return (crypto as any).randomUUID();
    }
    return 'leg-' + Math.random().toString(36).slice(2, 10);
  }

  loadBaseLegOptions(positionId?: string): void {
    if (!positionId) {
      this.baseLegOptions = [];
      return;
    }
    this.dashboardService.listBaseLegs(positionId).subscribe({
      next: (legs) => {
        // Only show legs that have an OPEN row with a matching MARK row and net qty > 0.
        const grouped = legs.reduce<Record<string, { open?: BaseLeg; mark?: BaseLeg; net: number }>>((acc, leg) => {
          const id = leg.base_leg_id || '';
          if (!id) return acc;
          const tag = (leg.tag || '').toString().toUpperCase();
          const qty = Number(leg.quantity || 0);
          if (!acc[id]) acc[id] = { net: 0 };
          if (tag === 'OPEN') acc[id].open = leg;
          if (tag === 'MARK') acc[id].mark = leg;
          if (tag === 'CLOSE') acc[id].net -= qty;
          if (tag === 'OPEN') acc[id].net += qty;
          return acc;
        }, {});
        this.baseLegOptions = Object.values(grouped)
          .filter((g) => g.open && g.mark && g.net > 0)
          .map((g) => g.open as BaseLeg);
      },
      error: () => {
        this.baseLegOptions = [];
      },
    });
  }

  onBaseLegSelect(legId: string): void {
    this.selectedBaseLegId = legId;
    if (!legId) {
      this.baseLegDraft = this.buildBlankBaseLeg();
      this.baseLegDraft.position_id = this.selectedPositionId || '';
      return;
    }
    const leg = this.baseLegOptions.find((l) => l.base_leg_id === legId);
    if (!leg) {
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    this.baseLegDraft = {
      ...leg,
      date: today,
      time: '09:30',
      tag: 'OPEN',
      amount: 0,
      fees: leg.fees ?? 0,
    };
    this.baseLegDateTime = `${today}T09:30`;
  }

  private buildBlankReserve(): ReserveRow {
    const today = new Date().toISOString().slice(0, 10);
    return {
      position_id: '',
      as_of_date: today,
      reserved_cash: 0,
      note_or_rule_text: '',
    };
  }

  private buildBlankReplacement(): ReplacementCost {
    const today = new Date().toISOString().slice(0, 10);
    return {
      position_id: '',
      as_of_date: today,
      replacement_cost_same_size: 0,
      unit_replacement_cost: 0,
      method: 'MANUAL',
    };
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

  private updateLedgerFilterOptions(summaries: LedgerSummary[]): void {
    const tickers = new Set<string>();
    const sides = new Set<string>();
    const strikes = new Set<string>();
    const expiries = new Set<string>();

    summaries.forEach((summary) => {
      if (summary.ticker) {
        tickers.add(summary.ticker.toUpperCase());
      }
      const side = normalizeSideOption(summary.side);
      if (side) {
        sides.add(side);
      }
      const strike = formatStrikeOption(summary.strike);
      if (strike) {
        strikes.add(strike);
      }
      const expiry = normalizeExpiryOption(summary.expiry);
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

  private updatePortfolioExpiryOptions(rows: LedgerRow[]): void {
    const expiries: string[] = [];
    rows.forEach((row) => {
      if (!row.expiry) {
        return;
      }
      const parsed = new Date(row.expiry);
      if (Number.isNaN(parsed.getTime())) {
        return;
      }
      expiries.push(parsed.toISOString().slice(0, 10));
    });

    if (!expiries.length) {
      this.portfolioExpiryMin = undefined;
      this.portfolioExpiryMax = undefined;
      return;
    }

    expiries.sort((a, b) => a.localeCompare(b));
    this.portfolioExpiryMin = expiries[0];
    this.portfolioExpiryMax = expiries[expiries.length - 1];
    if (this.portfolioExpiryStart && !expiries.includes(this.portfolioExpiryStart)) {
      this.portfolioExpiryStart = '';
    }
    if (this.portfolioExpiryEnd && !expiries.includes(this.portfolioExpiryEnd)) {
      this.portfolioExpiryEnd = '';
    }
  }

  private formatNumber(value: number | null | undefined, digits: string = '1.2-2'): string {
    if (value === null || value === undefined || isNaN(value as number)) {
      return '—';
    }
    return (value as number).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  private formatDisplay(perContract: number | null, total: number | null, mode?: string): string {
    const totalFormatted = this.formatNumber(total ?? null);
    if (totalFormatted === '—') {
      return totalFormatted;
    }
    if (mode === 'all_contracts_per100') {
      const perFormatted = this.formatNumber(perContract ?? null);
      if (perFormatted === '—') {
        return totalFormatted;
      }
      return `${totalFormatted} (${perFormatted}/100)`;
    }
    return totalFormatted;
  }

  formatDetailValue(kind: 'premium' | 'juice' | 'protection', row: LedgerRow): string {
    const contracts = this.toNumber(row.contracts) ?? 0;
    if (kind === 'premium') {
      const per = this.toNumber(row.premium_buyback) ?? null;
      const perContract = per !== null ? per * this.contractMultiplier : null;
      const total = per !== null ? per * contracts * this.contractMultiplier : null;
      return this.formatDisplay(perContract, total, this.displayMode);
    }
    if (kind === 'juice') {
      const per = calculateJuicePerContract(row, this.contractMultiplier);
      const total = calculateSignedJuiceRaw(row, this.contractMultiplier);
      return this.formatDisplay(per, total !== null ? Math.abs(total) : null, this.displayMode);
    }
    // protection
    const protRaw = calculateProtectionRaw(row, this.contractMultiplier);
    const totalProt = protRaw !== null ? Math.abs(protRaw) : null;
    const perProt = contracts ? (totalProt !== null ? totalProt / Math.abs(contracts) : null) : totalProt;
    return this.formatDisplay(perProt, totalProt, this.displayMode);
  }

  formatSummaryValue(kind: 'premium' | 'juice' | 'protection', summary: LedgerSummary): string {
    const contracts = summary.netContracts || 0;
    if (kind === 'premium') {
      const per = contracts !== 0 ? summary.netPremium / contracts : null;
      return this.formatDisplay(per, summary.netPremium, this.displayMode);
    }
    if (kind === 'juice') {
      const per = contracts !== 0 ? summary.netJuice / contracts : null;
      return this.formatDisplay(per, summary.netJuice, this.displayMode);
    }
    const perProt = contracts !== 0 ? summary.netProtection / contracts : null;
    return this.formatDisplay(perProt, summary.netProtection, this.displayMode);
  }

  // Fixed formatter for Juice by Expiry: always show All contracts + /100
  formatSummaryAllPer100(kind: 'premium' | 'juice' | 'protection', summary: LedgerSummary): string {
    const contracts = summary.netContracts || 0;
    if (kind === 'premium') {
      const per = contracts !== 0 ? summary.netPremium / contracts : null;
      return this.formatDisplay(per, summary.netPremium, 'all_contracts_per100');
    }
    if (kind === 'juice') {
      const per = contracts !== 0 ? summary.netJuice / contracts : null;
      return this.formatDisplay(per, summary.netJuice, 'all_contracts_per100');
    }
    const perProt = contracts !== 0 ? summary.netProtection / contracts : null;
    return this.formatDisplay(perProt, summary.netProtection, 'all_contracts_per100');
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
      const baseKey = extractBaseKey(row);
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
      summaries = summaries.filter((summary) => selected.has(normalizeSideOption(summary.side)));
    }
    if (this.selectedStrikes.length) {
      const selected = new Set(this.selectedStrikes);
      summaries = summaries.filter((summary) =>
        selected.has(formatStrikeOption(summary.strike))
      );
    }
    if (this.selectedExpiries.length) {
      const selected = new Set(this.selectedExpiries);
      summaries = summaries.filter((summary) =>
        selected.has(normalizeExpiryOption(summary.expiry))
      );
    }
    if (this.ledgerOpenOnly) {
      summaries = summaries.filter((summary) => summary.netContracts > 0);
    }
    return sortSummaries(summaries, this.ledgerSortOrder);
  }

  private computeOpenBalances(rows: LedgerRow[]): Record<string, { remaining: number; row: LedgerRow }> {
    const balances: Record<string, { remaining: number; row: LedgerRow }> = {};
    rows.forEach((row) => {
      const baseKey = extractBaseKey(row);
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

  private refreshOpenShortOptions(): void {
    const options: {
      key: string;
      base_position_id?: string | null;
      ticker?: string | null;
      side?: string | null;
      strike?: number | null;
      expiry?: string | null;
      remaining: number;
      label: string;
    }[] = [];
    Object.entries(this.computeOpenBalances(this.ledgerRows)).forEach(([key, info]) => {
      const remaining = info.remaining ?? 0;
      const row = info.row;
      if (remaining > 0 && row) {
        const label = `${(row.ticker || '').toUpperCase()} ${row.side || ''} ${row.strike ?? ''} ${
          row.expiry || '—'
        } · open ${remaining}`;
        options.push({
          key,
          base_position_id: row.base_position_id,
          ticker: row.ticker,
          side: row.side,
          strike: row.strike as any,
          expiry: row.expiry as any,
          remaining,
          label,
        });
      }
    });
    this.openShortOptions = options;
    this.updateAvailableOpenShorts();
  }

  private updateAvailableOpenShorts(): void {
    const baseId = this.selectedTradePositionId || this.tradeDraft?.base_position_id;
    this.availableOpenShorts = baseId
      ? this.openShortOptions.filter((opt) => opt.base_position_id === baseId)
      : [];
    if (!this.availableOpenShorts.some((opt) => opt.key === this.selectedOpenShortKey)) {
      this.selectedOpenShortKey = undefined;
      this.tradeActionLocked = false;
      this.tradeStrikeLocked = false;
      this.tradeExpiryLocked = false;
    }
  }

  onOpenShortSelect(key?: string): void {
    this.selectedOpenShortKey = key || undefined;
    this.tradeActionLocked = false;
    this.tradeStrikeLocked = false;
    this.tradeExpiryLocked = false;
    if (!key) {
      return;
    }
    const opt = this.availableOpenShorts.find((o) => o.key === key);
    if (!opt) {
      return;
    }
    this.tradeDraft.action = 'Close';
    this.tradeActionLocked = true;
    this.tradeDraft.strike = opt.strike ?? this.tradeDraft.strike;
    this.tradeStrikeLocked = opt.strike !== undefined && opt.strike !== null;
    this.tradeDraft.expiry = opt.expiry ?? this.tradeDraft.expiry;
    this.tradeExpiryLocked = !!opt.expiry;
    this.tradeDraft.contracts = opt.remaining ?? this.tradeDraft.contracts;
    // Keep ticker/strategy/side from base position locks already applied.
  }

}
