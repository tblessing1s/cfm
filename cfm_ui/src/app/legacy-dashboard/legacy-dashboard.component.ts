import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

import {
  AccountOption,
  DashboardMetrics,
  DashboardService,
  LedgerEntryCreate,
  LedgerRow,
  BusinessDashboard,
  PositionMetrics,
  MarkPositionRow,
  MinimalPositionStatus,
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
  CashMovement,
  CashAllocation,
} from '../services/dashboard.service';
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
} from '../utils/ledger-utils';

interface LedgerDraft {
  account?: string;
  ticker: string;
  action: 'Open' | 'Close' | 'Mark';
  strategy: string;
  side: 'Call' | 'Put';
  contracts?: number;
  strike?: number;
  expiry?: string;
  trade_datetime?: string;
  premium?: number;
  underlying?: number;
  condition?: string;
  base_position_id?: string;
  base_leg_id?: string;
}

@Component({
  selector: 'app-legacy-dashboard',
  templateUrl: './legacy-dashboard.component.html',
  styleUrls: ['./legacy-dashboard.component.css'],
})
export class LegacyDashboardComponent implements OnInit {
  accounts: AccountOption[] = [];
  selectedAccount?: string;
  activePage: 'business' | 'data' | 'trades' = 'business';
  activeBusinessView: 'snapshot' | 'cashflow' = 'snapshot';
  metrics?: DashboardMetrics;
  businessMetrics?: BusinessDashboard;
  layerSectionsOpen: Record<number, boolean> = {
    1: true,
    2: false,
    3: false,
    4: false,
  };
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
  markPositions: MarkPositionRow[] = [];
  minimalStatuses: MinimalPositionStatus[] = [];
  markBaseLegs: Record<string, BaseLeg[]> = {};
  markDeltaEditorOpen: Record<string, boolean> = {};
  markDeltaLegSelection: Record<string, string> = {};
  markDeltaDraft: Record<string, number | null> = {};
  markCardExpanded: Record<string, boolean> = {};
  showClosedBases = false;
  showClosedStocks = false;
  showAdvanced = false;
  showRegimeDialog = false;
  showPlanDialog = false;
  showRegimeForm = false;
  selectedTradePositionId?: string;
  selectedTradeBaseLegId?: string;
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
    base_leg_id?: string | null;
    ticker?: string | null;
    strategy?: string | null;
    side?: string | null;
    strike?: number | null;
    expiry?: string | null;
    remaining: number;
    label: string;
  }[] = [];
  availableOpenShorts: {
    key: string;
    base_position_id?: string | null;
    base_leg_id?: string | null;
    ticker?: string | null;
    strategy?: string | null;
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
  private readonly statusEps = 0.01;
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
  baseLegFilterOptions: string[] = [];
  selectedBaseLegIds: string[] = [];
  baseLegFilterOpen = false;
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
  baseLegLookup: Record<string, { open?: BaseLeg; mark?: BaseLeg; net?: number }> = {};
  selectedBaseLegId: string = '';
  baseLegDateTime?: string;
  tradeBaseLegOptions: BaseLeg[] = [];
  tradeBaseLegLookup: Record<string, { open?: BaseLeg; mark?: BaseLeg; net?: number }> = {};
  legInstrumentOptions = ['CALL', 'PUT', 'SHARES'];
  legSideOptions = ['BUY', 'SELL'];
  legTagOptions = ['OPEN', 'CLOSE'];
  baseLegIntrinsicPreview?: number;
  baseLegExtrinsicPreview?: number;
  conditionOptions = ['GREEN', 'YELLOW', 'RED'];
  tradeConditionOptions = ['GREEN', 'YELLOW', 'RED'];
  reserveDraft: ReserveRow = this.buildBlankReserve();
  replacementDraft: ReplacementCost = this.buildBlankReplacement();
  cashMovementDraft: CashMovement = this.buildBlankCashMovement();
  cashMovements: CashMovement[] = [];
  cashMovementWarning?: string;
  cashMovementError?: string;
  showCashAllocateModal = false;
  cashAllocateTicker?: string;
  cashAllocateType: 'extrinsic' | 'protection' = 'extrinsic';
  cashAllocateAmount?: number;
  cashAllocations: CashAllocation[] = [];
  selectedPositionId?: string;
  defaultReservePct = 0.05;
  navChartWidth = 360;
  navChartHeight = 120;
  // Targets for coloring
  weeklyYieldTargetPct = 0.5; // % of NAV
  monthlyYieldTargetPct = 2.0; // % of NAV
  selectedDataForm: 'nav' | 'base' | 'leg' | 'cash' = 'nav';
  cashDirectionOptions = ['DEPOSIT', 'WITHDRAWAL'];
  cashPurposeOptions = ['ACCOUNT', 'EXTRINSIC', 'PROTECTION'];
  dataFormHelp: Record<string, { label: string; when: string }> = {
    nav: { label: 'Account value snapshot', when: 'Log account net liq (NAV) weekly or daily; include free cash, deposits, withdrawals.' },
    base: { label: 'Base position', when: 'Create once per engine/symbol before logging base legs or reserves.' },
    leg: { label: 'Base leg', when: 'Whenever you buy/sell/roll the base (shares/long options).' },
    cash: { label: 'Cash movement', when: 'Track cash added/removed and what it was used for (account, extrinsic, protection).' },
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
    leg_instrument: 'CALL/PUT for option bases; SHARES for stock bases.',
    leg_side: 'BUY or SELL for the base leg.',
    leg_tag: 'OPEN / ROLL_OUT / ROLL_IN / CLOSE / ADD / REDUCE.',
    leg_price: 'Price paid/received per unit (share or contract) for the base leg.',
    leg_fees: 'Commissions/fees associated with this base leg.',
    leg_amount: 'Signed cash flow for the leg (BUY negative, SELL positive).',
    leg_underlying: 'Underlying price used to split intrinsic vs extrinsic.',
    leg_delta: 'Optional delta for long option legs (used for strength scoring).',
    leg_intrinsic: 'Computed intrinsic portion of the premium (not stored).',
    leg_extrinsic: 'Computed extrinsic portion of the premium (not stored).',
    leg_condition: 'Condition when logging this leg: GREEN (growth OK), YELLOW/RED (stay in cash).',
    cash_direction: 'Deposit adds cash; withdrawal pulls cash out of the account.',
    cash_purpose: 'What the cash is intended for: general account, extrinsic paydown, or intrinsic protection.',
    cash_position: 'Optional base position tied to the movement for tracking.',
    cash_amount: 'Dollar amount of the movement.',
    cash_note: 'Optional note about why the cash moved.',
    reserve_position: 'Base position this reserve is tied to.',
    reserve_cash: 'Cash earmarked for this base to cover rolls/assignments.',
    reserve_note: 'Rule or reason for this reserve.',
    replacement_position: 'Base position this replacement cost applies to.',
    replacement_same: 'Cost to rebuild the entire base at current prices.',
    replacement_unit: 'Cost per unit (share/contract) to rebuild.',
  };
  businessError?: string;
  businessSuccess?: string;

  private initialPage: 'business' | 'data' | 'trades' = 'business';

  constructor(
    private dashboardService: DashboardService,
    private route: ActivatedRoute,
  ) {
    const page = (this.route.snapshot.queryParamMap.get('page') ?? '').toLowerCase();
    if (page === 'business' || page === 'data' || page === 'trades') {
      this.initialPage = page;
    }
  }

  ngOnInit(): void {
    this.tradeDraft = this.buildBlankDraft();

    this.dashboardService.getAccounts().subscribe({
      next: (accounts) => {
        this.accounts = accounts.map((acc) => this.normalizeAccountOption(acc));
        if (accounts.length) {
          this.selectedAccount = accounts[0].name;
          this.tradeDraft.account = this.selectedAccount;
          this.cashMovementDraft = this.buildBlankCashMovement(this.selectedAccount);
          this.trades = [];
          this.loadMetrics();
          this.loadPortfolio();
          this.loadBusiness();
          this.loadRegimes();
          if (this.selectedStock) {
            this.loadProtection(this.selectedStock);
          }
          this.loadLedger(this.selectedAccount);
          this.setPage(this.initialPage);
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
      this.loadTradeBaseLegOptions();
    }
  }

  setBusinessView(view: 'snapshot' | 'cashflow'): void {
    this.activeBusinessView = view;
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
        this.loadCashAllocations();
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

  loadCashAllocations(): void {
    if (!this.selectedAccount) {
      this.cashAllocations = [];
      return;
    }
    this.dashboardService.listCashAllocations(this.selectedAccount).subscribe({
      next: (rows) => {
        this.cashAllocations = this.normalizeProtectionAllocations(rows || []);
      },
      error: () => {
        this.cashAllocations = [];
      },
    });
  }

  stockNetJuice(row: StockSummaryRow): number {
    return row.short_extrinsic_net ?? row.income_total_realized ?? 0;
  }

  stockInitialBaseValue(row: StockSummaryRow): number {
    if (row.original_base_value !== undefined && row.original_base_value !== null) {
      return row.original_base_value;
    }
    const intrinsic = row.initial_base_intrinsic ?? 0;
    const extrinsic = row.initial_base_extrinsic ?? 0;
    return intrinsic + extrinsic;
  }

  stockExtrinsicEntryTarget(row: StockSummaryRow): number {
    const goal = this.stockInitialBaseValue(row) * 0.015;
    return goal * 1.25;
  }

  stockExtrinsicExitTarget(row: StockSummaryRow): number {
    const goal = this.stockInitialBaseValue(row) * 0.015;
    return goal * 0.25;
  }

  stockWeeklyReturnPct(row: StockSummaryRow): number {
    const base = this.stockInitialBaseValue(row);
    if (!base) {
      return 0;
    }
    const weekly = row.avg_weekly_income ?? row.income_rate_weekly ?? 0;
    return (weekly / base) * 100;
  }

  isProtected(row: StockSummaryRow): boolean {
    const gap = row.protection_gap ?? 0;
    const allocated = this.allocatedForStock(row.ticker, 'protection');
    return (gap - allocated) <= this.statusEps;
  }

  isPaidOff(row: StockSummaryRow): boolean {
    const initialExtrinsic = row.initial_base_extrinsic ?? 0;
    const remaining = initialExtrinsic - this.stockNetJuice(row);
    return remaining <= this.statusEps;
  }

  isIncomeGenerating(row: StockSummaryRow): boolean {
    const initialExtrinsic = row.initial_base_extrinsic ?? 0;
    return this.isProtected(row) && this.isPaidOff(row) && this.stockNetJuice(row) > initialExtrinsic + this.statusEps;
  }

  overallStatus(row: StockSummaryRow): 'green' | 'yellow' | 'red' {
    if (!this.isProtected(row)) {
      return 'red';
    }
    if (this.isPaidOff(row)) {
      return 'green';
    }
    return 'yellow';
  }

  breakerState(row: StockSummaryRow): string {
    return (row.breaker_state || 'NONE').toUpperCase();
  }

  breakerPillClass(row: StockSummaryRow): string {
    const state = this.breakerState(row);
    if (state === 'EMERGENCY') return 'emergency';
    if (state === 'HARD') return 'hard';
    if (state === 'SOFT') return 'soft';
    return 'none';
  }

  breakerReasons(row: StockSummaryRow): string {
    const reasons = row.breaker_reasons || [];
    return reasons.length ? reasons.join(', ') : '—';
  }

  breakerAction(row: StockSummaryRow): string {
    return (row.breaker_action || 'HOLD').toUpperCase();
  }

  breakerCountdown(row: StockSummaryRow): string {
    return row.breaker_countdown || '—';
  }

  private breakerStateDescription(state: string): string {
    switch (state) {
      case 'EMERGENCY':
        return 'immediate risk-off, exit now';
      case 'HARD':
        return 'risk-off, exit preferred';
      case 'SOFT':
        return 'caution mode, protect base and avoid growth';
      case 'NONE':
        return 'normal trading conditions';
      default:
        return '';
    }
  }

  private breakerActionDescription(action: string): string {
    switch (action) {
      case 'EXIT':
        return 'close or hedge out';
      case 'REDUCE':
        return 'trim exposure or size down';
      case 'DEFEND':
        return 'add protection and avoid new adds';
      case 'GROW':
        return 'add exposure if setup is clean';
      case 'HOLD':
        return 'no change to exposure';
      default:
        return '';
    }
  }

  stockDetailBreakerState(): string {
    return (this.stockDetail?.breaker_state || 'NONE').toUpperCase();
  }

  stockDetailBreakerPillClass(): string {
    const state = this.stockDetailBreakerState();
    if (state === 'EMERGENCY') return 'emergency';
    if (state === 'HARD') return 'hard';
    if (state === 'SOFT') return 'soft';
    return 'none';
  }

  stockDetailBreakerReasons(): string {
    const reasons = this.stockDetail?.breaker_reasons || [];
    return reasons.length ? reasons.join(', ') : '—';
  }

  stockDetailBreakerAction(): string {
    return (this.stockDetail?.breaker_action || 'HOLD').toUpperCase();
  }

  stockDetailBreakerStateLabel(): string {
    const state = this.stockDetailBreakerState();
    const description = this.breakerStateDescription(state);
    return description ? `${state} - ${description}` : state;
  }

  stockDetailBreakerActionLabel(): string {
    const action = this.stockDetailBreakerAction();
    const description = this.breakerActionDescription(action);
    return description ? `${action} - ${description}` : action;
  }

  stockDetailBreakerCountdown(): string {
    return this.stockDetail?.breaker_countdown || '—';
  }


  portfolioNetJuice(): number {
    return this.portfolioSummary?.open_mark_net_juice ?? 0;
  }

  portfolioExtrinsicRemaining(): number {
    const initialExtrinsic = this.portfolioSummary?.open_mark_initial_extrinsic ?? 0;
    return initialExtrinsic - this.portfolioNetJuice();
  }

  portfolioIsProtected(): boolean {
    const gap = this.portfolioSummary?.open_mark_protection_gap ?? 0;
    return gap <= this.statusEps;
  }

  portfolioIsPaidOff(): boolean {
    return this.portfolioExtrinsicRemaining() <= this.statusEps;
  }

  portfolioIsIncomeGenerating(): boolean {
    const initialExtrinsic = this.portfolioSummary?.total_initial_base_extrinsic ?? 0;
    return this.portfolioIsProtected() && this.portfolioIsPaidOff() && this.portfolioNetJuice() > initialExtrinsic + this.statusEps;
  }

  portfolioExtraExtrinsic(): number {
    const initialExtrinsic = this.portfolioSummary?.open_mark_initial_extrinsic ?? 0;
    const extra = this.portfolioNetJuice() - initialExtrinsic;
    return extra > this.statusEps ? extra : 0;
  }

  portfolioExtrinsicAllocation(): number {
    return Math.max(0, this.portfolioExtrinsicRemaining());
  }

  portfolioProtectionAllocation(): number {
    return this.portfolioSummary?.open_mark_protection_gap ?? 0;
  }

  portfolioReserveCash(): number {
    const base = this.portfolioSummary?.open_mark_initial_base_value ?? 0;
    return base * 0.07;
  }

  portfolioUnusedCash(): number {
    const totalCash = this.portfolioSummary?.total_cash ?? 0;
    const allocated = this.portfolioExtrinsicAllocation() + this.portfolioProtectionAllocation() + this.portfolioReserveCash();
    return Math.max(0, totalCash - allocated - this.allocatedCashTotal());
  }

  allocatedCashTotal(): number {
    return this.cashAllocations.reduce((sum, item) => sum + (item.amount || 0), 0);
  }

  stockExtrinsicGap(row: StockSummaryRow): number {
    const initialExtrinsic = row.initial_base_extrinsic ?? 0;
    const gap = initialExtrinsic - this.stockNetJuice(row);
    return Math.max(0, gap);
  }

  stockProtectionGap(row: StockSummaryRow): number {
    return Math.max(0, row.protection_gap ?? 0);
  }

  selectedAllocationGap(): number {
    const row = this.stockRows.find((r) => r.ticker === this.cashAllocateTicker);
    if (!row) {
      return 0;
    }
    return this.cashAllocateType === 'extrinsic' ? this.stockExtrinsicGap(row) : this.stockProtectionGap(row);
  }

  selectedAllocationMax(): number {
    return Math.min(this.portfolioUnusedCash(), this.selectedAllocationGap());
  }

  allocationFor(ticker: string, type: 'extrinsic' | 'protection'): number {
    return this.cashAllocations.find((item) => item.ticker === ticker && item.type === type)?.amount ?? 0;
  }

  allocatedForStock(ticker: string, type: 'extrinsic' | 'protection'): number {
    return this.cashAllocations
      .filter((item) => item.ticker === ticker && item.type === type)
      .reduce((sum, item) => sum + (item.amount || 0), 0);
  }

  stockDetailProtectionAllocation(): number {
    if (!this.stockDetail) {
      return 0;
    }
    return this.allocatedForStock(this.stockDetail.ticker, 'protection');
  }

  stockDetailShortIntrinsicRealized(): number {
    if (!this.stockDetail) {
      return 0;
    }
    return this.stockDetail.short_intrinsic_realized ?? 0;
  }

  stockDetailShortIntrinsicUnrealized(): number {
    if (!this.stockDetail) {
      return 0;
    }
    return this.stockDetail.short_intrinsic_unrealized ?? 0;
  }

  stockDetailProtectionWithAllocation(): number {
    if (!this.stockDetail) {
      return 0;
    }
    const realized = this.stockDetail.short_intrinsic_realized;
    const unrealized = this.stockDetail.short_intrinsic_unrealized;
    const hasBreakout = realized !== undefined && realized !== null || unrealized !== undefined && unrealized !== null;
    const baseProtection = hasBreakout
      ? this.stockDetailShortIntrinsicRealized() + this.stockDetailShortIntrinsicUnrealized()
      : (this.stockDetail.total_protection_collected ?? 0);
    return baseProtection + this.stockDetailProtectionAllocation();
  }

  stockDetailBasePlusProtectionWithAllocation(): number {
    if (!this.stockDetail) {
      return 0;
    }
    return (this.stockDetail.current_base_intrinsic ?? 0) + this.stockDetailProtectionWithAllocation();
  }

  openCashAllocateModal(): void {
    this.showCashAllocateModal = true;
    this.cashAllocateTicker = this.stockRows[0]?.ticker;
    this.cashAllocateType = 'extrinsic';
    this.cashAllocateAmount = undefined;
  }

  closeCashAllocateModal(): void {
    this.showCashAllocateModal = false;
  }

  updateCashAllocateAmount(value: number | null): void {
    const max = this.selectedAllocationMax();
    if (value === null || value === undefined || Number.isNaN(value)) {
      this.cashAllocateAmount = undefined;
      return;
    }
    this.cashAllocateAmount = Math.max(0, Math.min(value, max));
  }

  saveCashAllocation(): void {
    if (!this.cashAllocateTicker) {
      return;
    }
    const gap = this.selectedAllocationGap();
    const max = this.selectedAllocationMax();
    const amount = Math.max(0, Math.min(this.cashAllocateAmount ?? 0, max));
    if (!this.selectedAccount) {
      return;
    }
    const effectiveAmount =
      this.cashAllocateType === 'protection' && gap <= this.statusEps ? 0 : amount;
    this.dashboardService
      .saveCashAllocation({
        account: this.selectedAccount,
        ticker: this.cashAllocateTicker,
        type: this.cashAllocateType,
        amount: effectiveAmount,
      })
      .subscribe({
        next: (saved) => {
          const idx = this.cashAllocations.findIndex(
            (item) => item.ticker === saved.ticker && item.type === saved.type
          );
          if (idx >= 0) {
            this.cashAllocations[idx] = saved;
          } else {
            this.cashAllocations.push(saved);
          }
          if (saved.amount <= 0) {
            this.cashAllocations = this.cashAllocations.filter(
              (item) => !(item.ticker === saved.ticker && item.type === saved.type)
            );
          }
          this.closeCashAllocateModal();
        },
      });
  }

  private normalizeProtectionAllocations(rows: CashAllocation[]): CashAllocation[] {
    if (!rows.length || !this.selectedAccount || !this.stockRows.length) {
      return rows;
    }
    const updates: CashAllocation[] = [];
    const normalized = rows.map((item) => {
      if (item.type !== 'protection') {
        return item;
      }
      const row = this.stockRows.find((stock) => stock.ticker === item.ticker);
      if (!row) {
        return item;
      }
      const gap = this.stockProtectionGap(row);
      const current = item.amount ?? 0;
      const clamped = Math.max(0, Math.min(current, gap));
      if (Math.abs(clamped - current) > this.statusEps) {
        const updated = { ...item, amount: clamped };
        updates.push(updated);
        return updated;
      }
      return item;
    });
    updates.forEach((item) => {
      this.dashboardService
        .saveCashAllocation({
          account: this.selectedAccount as string,
          ticker: item.ticker,
          type: item.type,
          amount: item.amount ?? 0,
        })
        .subscribe({
          next: (saved) => {
            const idx = this.cashAllocations.findIndex(
              (entry) => entry.ticker === saved.ticker && entry.type === saved.type
            );
            if (idx >= 0) {
              if (saved.amount <= 0) {
                this.cashAllocations.splice(idx, 1);
              } else {
                this.cashAllocations[idx] = saved;
              }
            }
          },
        });
    });
    return normalized.filter((item) => item.amount && item.amount > 0);
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
        if (this.activePage === 'trades') {
          this.loadTradeBaseLegOptions();
        }
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
    this.dashboardService.getMarkDashboard(this.selectedAccount).subscribe({
      next: (rows) => {
        this.markPositions = rows || [];
        this.syncMarkDeltaSelections();
      },
      error: () => {
        this.markPositions = [];
      },
    });
    this.dashboardService.getMinimalPositionStatus(this.selectedAccount).subscribe({
      next: (rows) => {
        this.minimalStatuses = rows || [];
      },
      error: () => {
        this.minimalStatuses = [];
      },
    });
    this.dashboardService
      .listPositionMetrics(this.selectedAccount, this.showClosedBases, expiryStart, expiryEnd)
      .subscribe({
        next: (rows) => {
          this.applyPositionMetrics(rows);
        },
        error: () => {
          this.positionMetrics = [];
        },
      });
    this.loadCashMovements(this.selectedAccount);
  }

  private syncMarkDeltaSelections(): void {
    const existing = new Set(this.markPositions.map((row) => row.position_id));
    for (const key of Object.keys(this.markDeltaEditorOpen)) {
      if (!existing.has(key)) {
        delete this.markDeltaEditorOpen[key];
        delete this.markDeltaLegSelection[key];
        delete this.markDeltaDraft[key];
        delete this.markBaseLegs[key];
        delete this.markCardExpanded[key];
      }
    }
  }

  toggleMarkCard(positionId: string): void {
    this.markCardExpanded[positionId] = !this.markCardExpanded[positionId];
  }

  sectionHelp(section: 'regime' | 'ticket' | 'posture'): string {
    if (section === 'regime') {
      return 'Market + Stock Regime (Green/Yellow/Red) drive Conviction.';
    }
    if (section === 'ticket') {
      return 'Long DTE = days to expiry (worst). Long Delta = lowest delta. Ticket Health: A=strong, B=ok, C=fragile.';
    }
    return 'Conviction (HIGH/MED/LOW) + Ticket Health -> Operating Posture (ATTACK/MANAGE/DEFEND).';
  }

  postureGuidance(posture: string): string {
    const value = (posture || '').toUpperCase();
    if (value === 'ATTACK') {
      return 'Lean into weekly income. Scale only if ticket stays strong and regimes stay Green.';
    }
    if (value === 'DEFEND') {
      return 'Reduce risk: tighten rolls, avoid scaling, and prioritize protection.';
    }
    return 'Manage risk: keep weeklies steady, monitor runway, and scale only with added protection.';
  }

  postureHelp(): string {
    return 'ATTACK: high conviction + healthy ticket. MANAGE: mixed signals. DEFEND: low conviction or fragile ticket.';
  }

  postureFocus(posture: string): string[] {
    const value = (posture || '').toUpperCase();
    if (value === 'ATTACK') {
      return ['Focus on growth', 'Sell weekly for income', 'Add only on strength'];
    }
    if (value === 'DEFEND') {
      return ['Reduce position risk', 'Prioritize protection', 'Consider exit if Red persists'];
    }
    return ['Scale cautiously', 'Add protection if growing', 'Plan next roll'];
  }

  defenseTightness(posture: string): string {
    const value = (posture || '').toUpperCase();
    if (value === 'ATTACK') return 'Relaxed';
    if (value === 'DEFEND') return 'Tight';
    return 'Moderate';
  }

  defenseHelp(): string {
    return 'Relaxed: short strike at/slightly OTM. Moderate: near ATM. Tight: ATM or slightly ITM for max protection.';
  }

  toggleMarkDeltaEditor(positionId: string): void {
    const open = !this.markDeltaEditorOpen[positionId];
    this.markDeltaEditorOpen[positionId] = open;
    if (open) {
      this.loadMarkBaseLegs(positionId);
    }
  }

  loadMarkBaseLegs(positionId: string): void {
    this.dashboardService.listBaseLegs(positionId).subscribe({
      next: (legs) => {
        const active = legs.filter((leg) => this.isActiveMarkLeg(leg));
        const sorted = [...active].sort((a, b) => {
          const aExp = a.expiry ? new Date(a.expiry).getTime() : 0;
          const bExp = b.expiry ? new Date(b.expiry).getTime() : 0;
          if (aExp !== bExp) return aExp - bExp;
          const aStrike = a.strike ?? 0;
          const bStrike = b.strike ?? 0;
          return aStrike - bStrike;
        });
        this.markBaseLegs[positionId] = sorted;
        if (!this.markDeltaLegSelection[positionId] && sorted.length) {
          this.onMarkDeltaLegSelect(positionId, sorted[0].base_leg_id);
        }
      },
      error: () => {
        this.markBaseLegs[positionId] = [];
      },
    });
  }

  onMarkDeltaLegSelect(positionId: string, legId: string): void {
    this.markDeltaLegSelection[positionId] = legId;
    const leg = (this.markBaseLegs[positionId] || []).find((row) => row.base_leg_id === legId);
    this.markDeltaDraft[positionId] = leg?.delta ?? null;
  }

  markLegLabel(leg: BaseLeg): string {
    const expiry = leg.expiry ? new Date(leg.expiry).toISOString().slice(0, 10) : '—';
    const strike = leg.strike !== undefined && leg.strike !== null ? leg.strike : '—';
    return `${expiry} · ${strike}`;
  }

  isMarkDeltaHealthy(positionId: string): boolean {
    const val = this.markDeltaDraft[positionId];
    return val !== null && val !== undefined && val >= 0.85;
  }

  setMarkDeltaHealthy(positionId: string, checked: boolean): void {
    this.markDeltaDraft[positionId] = checked ? 0.85 : 0.84;
  }

  private isActiveMarkLeg(leg: BaseLeg): boolean {
    const tag = (leg.tag || '').toUpperCase();
    if (tag !== 'MARK') return false;
    if (leg.expiry) {
      const expiry = new Date(leg.expiry);
      const today = new Date();
      expiry.setHours(0, 0, 0, 0);
      today.setHours(0, 0, 0, 0);
      if (expiry < today) return false;
    }
    return true;
  }

  saveMarkDelta(positionId: string): void {
    const legId = this.markDeltaLegSelection[positionId];
    if (!legId) {
      this.businessError = 'Select a base leg before saving delta.';
      return;
    }
    const delta = this.markDeltaDraft[positionId];
    this.dashboardService.updateBaseLeg(legId, { delta }).subscribe({
      next: (updated) => {
        const legs = this.markBaseLegs[positionId] || [];
        const idx = legs.findIndex((row) => row.base_leg_id === updated.base_leg_id);
        if (idx >= 0) {
          legs[idx] = { ...legs[idx], delta: updated.delta };
        }
        this.markBaseLegs[positionId] = [...legs];
        this.loadBusiness();
        this.businessSuccess = 'Delta saved.';
      },
      error: () => {
        this.businessError = 'Unable to save delta.';
      },
    });
  }

  loadCashMovements(account: string): void {
    this.dashboardService.listCashMovements(account).subscribe({
      next: (rows) => {
        this.cashMovements = [...rows].sort(
          (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
        );
      },
      error: () => {
        this.cashMovements = [];
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
        this.loadBusiness();
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
      this.tradeDraft.base_leg_id = undefined;
      this.selectedTradeBaseLegId = undefined;
      return;
    }
    const pm = this.positionMetrics.find((p) => p.position.position_id === positionId);
    if (pm) {
      this.tradeDraft.ticker = pm.position.symbol;
      this.tradeDraft.strategy = this.normalizeStrategy(pm.position.strategy || this.tradeDraft.strategy);
      this.tradeDraft.side = 'Call';
      this.tradeDraft.base_position_id = pm.position.position_id;
      this.tradeDraft.base_leg_id = undefined;
      this.selectedTradeBaseLegId = undefined;
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
        this.loadBusiness();
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
    this.cashMovementDraft = this.buildBlankCashMovement(accountName);
    this.updateCashMovementWarning();
    this.cashMovementError = undefined;
    this.selectedTradePositionId = undefined;
    this.tradeTickerLocked = false;
    this.tradeStrategyLocked = false;
    this.selectedTickers = [];
    this.selectedSides = [];
    this.selectedStrikes = [];
    this.selectedExpiries = [];
    this.selectedBaseLegIds = [];
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

  get selectedTradePositionMetrics(): PositionMetrics | undefined {
    const positionId = this.selectedTradePositionId || this.tradeDraft?.base_position_id;
    if (!positionId) {
      return undefined;
    }
    return this.positionMetrics.find((pm) => pm.position.position_id === positionId);
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
    const strategy = this.normalizeStrategy(this.tradeDraft.strategy);
    const requiresBase = strategy === 'CFM';
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
    if (!hasBasics) {
      return false;
    }
    if (requiresBase && !this.tradeDraft.base_position_id) {
      return false;
    }
    return true;
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

    if (!this.tradeDraft.strategy) {
      this.entryError = 'Strategy is required.';
      return;
    }

    if (!this.tradeDraft.expiry) {
      this.entryError = 'Pick an expiration date.';
      return;
    }

    const contracts = this.toNumber(this.tradeDraft.contracts);
    const strike = this.toNumber(this.tradeDraft.strike);
    const premium = this.toNumber(this.tradeDraft.premium);
    const strategy = this.normalizeStrategy(this.tradeDraft.strategy);

    this.enforceSideForStrategy();
    if (strategy === 'CFM' && !this.tradeDraft.base_position_id) {
      this.entryError = 'Select a base position before staging a CFM trade.';
      return;
    }
    const underlying = this.toNumber(this.tradeDraft.underlying);

    if (this.tradeDraft.action === 'Open') {
      const maxContracts = this.tradeContractLimit();
      if (maxContracts !== null && contracts !== undefined && contracts > maxContracts) {
        this.entryError = `Contracts cannot exceed ${maxContracts} for the selected base leg.`;
        this.tradeDraft.contracts = maxContracts;
        return;
      }
    }

    const underlyingPayload =
      this.tradeDraft.action === 'Close' || this.tradeDraft.action === 'Mark' ? undefined : underlying ?? undefined;
    const staged: LedgerEntryCreate = {
      account,
      // `datetime-local` is a local-time value with no timezone. Sending it as-is
      // avoids shifting the time when converting to UTC via `toISOString()`.
      trade_datetime: this.tradeDraft.trade_datetime,
      ticker,
      strategy: this.normalizeStrategy(this.tradeDraft.strategy),
      action: this.tradeDraft.action,
      side: this.tradeDraft.side,
      contracts: contracts ?? 0,
      strike: strike ?? 0,
      expiry: this.tradeDraft.expiry!,
      premium: premium ?? 0,
      underlying: underlyingPayload,
      condition: this.tradeDraft.condition,
      base_position_id: this.tradeDraft.base_position_id,
      base_leg_id: this.tradeDraft.base_leg_id,
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

  submitCashMovement(): void {
    if (!this.selectedAccount || !this.cashMovementDraft.date) {
      this.cashMovementError = 'Select account and date for the cash movement.';
      return;
    }
    const amount = this.toNumber(this.cashMovementDraft.amount);
    if (!amount || amount <= 0) {
      this.cashMovementError = 'Enter a valid cash amount.';
      return;
    }
    if (!this.cashMovementDraft.direction || !this.cashMovementDraft.purpose) {
      this.cashMovementError = 'Select direction and purpose.';
      return;
    }
    this.cashMovementError = undefined;
    const payload: CashMovement = {
      ...this.cashMovementDraft,
      account: this.selectedAccount,
      amount,
      direction: this.cashMovementDraft.direction.toUpperCase(),
      purpose: this.cashMovementDraft.purpose.toUpperCase(),
    };
    this.dashboardService.createCashMovement(payload).subscribe({
      next: () => {
        this.businessSuccess = 'Saved cash movement.';
        this.businessError = undefined;
        this.cashMovementError = undefined;
        this.cashMovementDraft = this.buildBlankCashMovement(this.selectedAccount);
        this.updateCashMovementWarning();
        this.loadCashMovements(this.selectedAccount);
      },
      error: () => {
        this.cashMovementError = 'Unable to save cash movement.';
      },
    });
  }

  setDataForm(form: 'nav' | 'base' | 'leg' | 'cash'): void {
    this.selectedDataForm = form;
    if (form === 'leg') {
      this.loadBaseLegOptions(this.selectedPositionId);
    }
    if (form === 'cash') {
      this.cashMovementDraft.position_id = this.selectedPositionId || undefined;
      this.updateCashMovementWarning();
    }
  }

  onPositionSelect(positionId: string | undefined): void {
    this.selectedPositionId = positionId || undefined;
    const pid = this.selectedPositionId || '';
    this.baseLegDraft.position_id = pid;
    this.reserveDraft.position_id = pid;
    this.replacementDraft.position_id = pid;
    this.cashMovementDraft.position_id = pid || undefined;
    this.updateCashMovementWarning();
    this.selectedBaseLegId = '';
    this.baseLegOptions = [];
    this.baseLegLookup = {};
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

  updateCashMovementWarning(): void {
    this.cashMovementWarning = undefined;
    const amount = this.toNumber(this.cashMovementDraft.amount);
    if (!amount || amount <= 0) {
      return;
    }
    const direction = (this.cashMovementDraft.direction || '').toUpperCase();
    const purpose = (this.cashMovementDraft.purpose || '').toUpperCase();
    const positionId = this.cashMovementDraft.position_id;

    if (!positionId) {
      if (purpose === 'EXTRINSIC' || purpose === 'PROTECTION') {
        this.cashMovementWarning = 'No base selected; this will be tracked at the account level only.';
      }
      return;
    }

    const pm = this.positionMetrics.find((p) => p.position.position_id === positionId);
    if (!pm || direction !== 'WITHDRAWAL') {
      return;
    }

    const remainingExtrinsic = Math.max(0, (pm.initial_base_extrinsic ?? 0) - (pm.net_juice_to_date ?? 0));
    const initialIntrinsic = pm.initial_base_intrinsic ?? 0;
    const currentIntrinsic = pm.current_base_intrinsic ?? 0;
    const protection = pm.net_intrinsic_to_date ?? 0;
    const protectionGap = Math.max(0, initialIntrinsic - (currentIntrinsic + protection));

    if (amount > remainingExtrinsic + this.statusEps) {
      const overage = amount - remainingExtrinsic;
      const extrinsicText = this.formatNumber(remainingExtrinsic, '1.2-2');
      const overageText = this.formatNumber(overage, '1.2-2');
      const gapText = this.formatNumber(protectionGap, '1.2-2');
      this.cashMovementWarning =
        `Withdrawal exceeds remaining extrinsic (~${extrinsicText}) by ${overageText}. ` +
        (protectionGap > this.statusEps ? `Intrinsic gap is ~${gapText}; excess could erode protection.` : 'Excess could erode intrinsic protection.');
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
    const gross = Math.abs(price * qty * 100);
    const total = gross + Math.abs(fees);
    this.baseLegDraft.amount = Math.round(total * 100) / 100;
    this.recomputeBaseLegPremiumBreakdown();
  }

  onTradeBaseLegSelect(legId?: string): void {
    this.selectedTradeBaseLegId = legId || undefined;
    if (!legId) {
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
      this.tradeDraft.base_leg_id = undefined;
      this.tradeDraft.base_position_id = undefined;
      this.tradeDraft.contracts = undefined;
      return;
    }
    const entry = this.tradeBaseLegLookup[legId];
    const leg = entry?.mark || entry?.open;
    if (!leg) {
      return;
    }
    this.tradeDraft.base_leg_id = leg.base_leg_id;
    this.tradeDraft.base_position_id = leg.position_id;
    this.selectedTradePositionId = leg.position_id;
    const pm = this.positionMetrics.find((p) => p.position.position_id === leg.position_id);
    if (pm) {
      this.tradeDraft.ticker = pm.position.symbol;
      this.tradeDraft.strategy = this.normalizeStrategy(pm.position.strategy || this.tradeDraft.strategy);
      this.tradeDraft.side = 'Call';
      this.tradeTickerLocked = true;
      this.tradeStrategyLocked = true;
      this.tradeSideLocked = this.normalizeStrategy(pm.position.strategy) === 'CFM';
    }
    this.tradeActionLocked = false;
    this.tradeStrikeLocked = false;
    this.tradeExpiryLocked = false;
    this.applyTradeContractLimit(true);
    this.selectedOpenShortKey = undefined;
    this.updateAvailableOpenShorts();
  }

  onTradeActionChange(action: 'Open' | 'Close' | 'Mark'): void {
    this.tradeDraft.action = action;
    if (action === 'Open') {
      this.applyTradeContractLimit(true);
    }
  }

  onTradeContractsChange(value: number | string | null): void {
    const numeric = this.toNumber(value as number | string | undefined);
    if (numeric === undefined) {
      this.tradeDraft.contracts = undefined;
      return;
    }
    const maxContracts = this.tradeContractLimit();
    if (this.tradeDraft.action === 'Open' && maxContracts !== null && numeric > maxContracts) {
      this.tradeDraft.contracts = maxContracts;
      return;
    }
    this.tradeDraft.contracts = numeric;
  }

  tradeContractsMax(): number | null {
    return this.tradeContractLimit();
  }

  tradeBaseLegLabel(leg: BaseLeg): string {
    const pm = this.positionMetrics.find((p) => p.position.position_id === leg.position_id);
    const symbol = pm?.position.symbol || leg.position_id;
    const date = leg.date ? new Date(leg.date).toISOString().slice(0, 10) : '';
    return `${symbol} · ${leg.base_leg_id}${date ? ' · ' + date : ''}`;
  }

  recomputeBaseLegPremiumBreakdown(): void {
    const instr = (this.baseLegDraft.instrument_type || '').toUpperCase();
    const optionTokens = new Set(['', 'OPTION', 'CALL', 'PUT', 'OPTION_CALL', 'OPTION_PUT', 'CALL_OPTION', 'PUT_OPTION']);
    if (!optionTokens.has(instr)) {
      this.baseLegIntrinsicPreview = undefined;
      this.baseLegExtrinsicPreview = undefined;
      return;
    }
    const qty = this.toNumber(this.baseLegDraft.quantity);
    const price = this.toNumber(this.baseLegDraft.price);
    const strike = this.toNumber(this.baseLegDraft.strike);
    const underlying = this.toNumber(this.baseLegDraft.underlying_price);
    if (qty === undefined || price === undefined || strike === undefined || underlying === undefined) {
      this.baseLegIntrinsicPreview = undefined;
      this.baseLegExtrinsicPreview = undefined;
      return;
    }
    const isPut = instr === 'PUT' || instr === 'OPTION_PUT' || instr === 'PUT_OPTION';
    const intrinsicPer = Math.max(0, isPut ? strike - underlying : underlying - strike);
    const multiplier = 100;
    const intrinsicTotal = intrinsicPer * qty * multiplier;
    const premiumTotal = price * qty * multiplier;
    this.baseLegIntrinsicPreview = Math.round(intrinsicTotal * 100) / 100;
    this.baseLegExtrinsicPreview = Math.round((premiumTotal - intrinsicTotal) * 100) / 100;
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

  protectionClass(value?: boolean | null): string {
    if (value === undefined || value === null) return 'badge-neutral';
    return value ? 'badge-green' : 'badge-red';
  }

  stageClass(stage?: string | null): string {
    if (!stage) return 'badge-neutral';
    if (stage === 'PAYCHECK_MODE' || stage === 'MATURE') return 'badge-green';
    if (stage === 'PROTECTED') return 'badge-yellow';
    if (stage === 'BUILDING') return 'badge-red';
    return 'badge-neutral';
  }

  actionClass(action?: string | null): string {
    if (!action) return 'badge-neutral';
    if (action === 'PROTECTION_ROLL_NOW') return 'badge-red';
    if (action === 'PROTECTION_ROLL') return 'badge-yellow';
    if (action === 'INCOME_ROLL') return 'badge-green';
    return 'badge-neutral';
  }

  toggleLayerSection(layer: number): void {
    this.layerSectionsOpen[layer] = !this.layerSectionsOpen[layer];
  }

  portfolioPrincipalCost(): number {
    return this.positionMetrics.reduce((sum, pm) => sum + (pm.principal_cost || 0), 0);
  }

  portfolioLiquidationValue(): number {
    return this.positionMetrics.reduce((sum, pm) => sum + (pm.liquidation_value || 0), 0);
  }

  portfolioCushion(): number {
    return this.positionMetrics.reduce((sum, pm) => sum + (pm.cushion || 0), 0);
  }

  portfolioSafetyReserve(): number {
    return this.positionMetrics.reduce((sum, pm) => sum + (pm.safety_reserve || 0), 0);
  }

  portfolioWithdrawableNow(): number {
    return this.positionMetrics.reduce((sum, pm) => sum + (pm.withdrawable_now || 0), 0);
  }

  portfolioProtectedNow(): boolean | null {
    if (!this.positionMetrics.length) return null;
    const principal = this.portfolioPrincipalCost();
    if (!principal) return false;
    return this.portfolioLiquidationValue() >= principal;
  }

  layeredPositionRows(): PositionMetrics[] {
    return [...this.positionMetrics].sort((a, b) => {
      const aEmergency = a.emergency_roll ? 1 : 0;
      const bEmergency = b.emergency_roll ? 1 : 0;
      if (aEmergency !== bEmergency) {
        return bEmergency - aEmergency;
      }
      const aUnprotected = (a.cushion ?? 0) < 0 ? 1 : 0;
      const bUnprotected = (b.cushion ?? 0) < 0 ? 1 : 0;
      if (aUnprotected !== bUnprotected) {
        return bUnprotected - aUnprotected;
      }
      const ratioA = this.positionRiskRatio(a);
      const ratioB = this.positionRiskRatio(b);
      if (ratioA !== ratioB) {
        return ratioA - ratioB;
      }
      return (a.position.symbol || '').localeCompare(b.position.symbol || '');
    });
  }

  private positionRiskRatio(pm: PositionMetrics): number {
    const cushion = pm.cushion ?? 0;
    const reserve = pm.safety_reserve ?? 0;
    if (!reserve) {
      return Number.POSITIVE_INFINITY;
    }
    return cushion / reserve;
  }

  private applyPositionMetrics(rows: PositionMetrics[]): void {
    this.positionMetrics = this.showClosedBases ? rows : rows.filter((pm) => !pm.position.closed_date);
    if (this.selectedPositionId) {
      const exists = rows.some((pm) => pm.position.position_id === this.selectedPositionId);
      if (!exists) {
        this.selectedPositionId = undefined;
      }
    }
    if (this.selectedPositionId) {
      this.applyReserveDefault(this.selectedPositionId);
    }
    this.updateCashMovementWarning();
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

  baseStrengthStatus(extrinsicRemaining?: number | null, protectionGap?: number | null): string {
    const extrinsic = extrinsicRemaining ?? 0;
    const gap = protectionGap ?? 0;
    const eps = 1e-6;
    if (extrinsic <= eps && gap <= eps) return 'Fully protected';
    if (extrinsic > eps && gap > eps) return 'Needs paydown + protection';
    if (extrinsic > eps) return 'Needs extrinsic paydown';
    return 'Needs intrinsic protection';
  }

  baseStrengthGuidance(extrinsicRemaining?: number | null, protectionGap?: number | null): string {
    const extrinsic = extrinsicRemaining ?? 0;
    const gap = protectionGap ?? 0;
    const eps = 1e-6;
    if (extrinsic <= eps && gap <= eps) return 'No remaining extrinsic or protection gap.';
    if (extrinsic > eps && gap > eps) return 'Reduce extrinsic and add short intrinsic.';
    if (extrinsic > eps) return 'Reduce extrinsic with short income.';
    return 'Add short intrinsic protection.';
  }

  cashMovementTotal(direction?: string, purpose?: string): number {
    const dir = direction ? direction.toUpperCase() : undefined;
    const purp = purpose ? purpose.toUpperCase() : undefined;
    return this.cashMovements
      .filter((m) => (dir ? (m.direction || '').toUpperCase() === dir : true))
      .filter((m) => (purp ? (m.purpose || '').toUpperCase() === purp : true))
      .reduce((sum, m) => sum + (Number(m.amount) || 0), 0);
  }

  movementLabel(value?: string): string {
    if (!value) return '';
    const lower = value.toLowerCase();
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }

  positionLabel(positionId?: string): string {
    if (!positionId) return '—';
    const pm = this.positionMetrics.find((p) => p.position.position_id === positionId);
    if (!pm) return positionId;
    return `${pm.position.symbol} · ${pm.position.strategy}`;
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
      underlying: entry.underlying,
      base_position_id: entry.base_position_id,
      base_leg_id: entry.base_leg_id,
    };
    this.enforceSideForStrategy(this.tradeDraft);
    this.selectedTradePositionId = entry.base_position_id;
    this.selectedTradeBaseLegId = entry.base_leg_id;
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
    let action: 'Open' | 'Close' | 'Mark' = 'Open';
    if (actionClean.includes('close')) {
      action = 'Close';
    } else if (actionClean.includes('mark')) {
      action = 'Mark';
    }
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
      underlying: row.underlying ?? undefined,
      condition: row.condition || row.notes || undefined,
      base_position_id: row.base_position_id,
      base_leg_id: row.base_leg_id,
    };
    if (row.base_leg_id) {
      this.selectedTradeBaseLegId = row.base_leg_id;
      const leg = this.tradeBaseLegLookup[row.base_leg_id]?.open || this.tradeBaseLegLookup[row.base_leg_id]?.mark;
      if (leg) {
        this.tradeDraft.base_position_id = leg.position_id;
        this.selectedTradePositionId = leg.position_id;
      }
      this.tradeTickerLocked = true;
      this.tradeStrategyLocked = true;
      this.tradeSideLocked = this.tradeDraft.strategy === 'CFM';
    } else {
      this.selectedTradeBaseLegId = undefined;
      this.selectedTradePositionId = this.tradeDraft.base_position_id;
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

    if (!this.tradeDraft.strategy) {
      this.submitError = 'Strategy is required.';
      return;
    }

    const contracts = this.toNumber(this.tradeDraft.contracts);
    const strike = this.toNumber(this.tradeDraft.strike);
    const premium = this.toNumber(this.tradeDraft.premium);
    const underlying = this.toNumber(this.tradeDraft.underlying);
    const strategy = this.normalizeStrategy(this.tradeDraft.strategy);

    if (strategy === 'CFM' && !this.tradeDraft.base_position_id) {
      this.submitError = 'Select a base position before saving a CFM trade.';
      return;
    }
    if (strategy === 'CFM' && this.tradeDraft.side === 'Call' && underlying === undefined) {
      this.submitError = 'Underlying price is required for CFM Call trades.';
      return;
    }

    const underlyingPayload =
      this.tradeDraft.action === 'Close' || this.tradeDraft.action === 'Mark' ? undefined : underlying ?? undefined;
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
      underlying: underlyingPayload,
      base_position_id: this.tradeDraft.base_position_id,
      base_leg_id: this.tradeDraft.base_leg_id,
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
    this.selectedTradeBaseLegId = undefined;
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

  toggleBaseLegFilter(): void {
    this.baseLegFilterOpen = !this.baseLegFilterOpen;
  }

  closeBaseLegFilter(): void {
    this.baseLegFilterOpen = false;
  }

  isAllBaseLegsSelected(): boolean {
    return (
      this.baseLegFilterOptions.length > 0 &&
      this.selectedBaseLegIds.length === this.baseLegFilterOptions.length
    );
  }

  toggleAllBaseLegs(checked: boolean): void {
    this.selectedBaseLegIds = checked ? [...this.baseLegFilterOptions] : [];
    this.ledgerPage = 1;
  }

  toggleBaseLegSelection(baseLegId: string, checked: boolean): void {
    const next = new Set(this.selectedBaseLegIds);
    if (checked) {
      next.add(baseLegId);
    } else {
      next.delete(baseLegId);
    }
    this.selectedBaseLegIds = Array.from(next);
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

  private normalizeStrategy(value: string | undefined): 'CFM' | 'JL' {
    if (typeof value === 'string') {
      const normalized = value.toLowerCase();
      if (normalized.includes('juice') || normalized.includes('jl')) {
        return 'JL';
      }
      if (normalized.includes('cashflow') || normalized.includes('cfm')) {
        return 'CFM';
      }
    }
    return 'CFM';
  }

  private buildBlankDraft(account?: string): LedgerDraft {
    const today = new Date().toISOString().slice(0, 10);
    const draft: LedgerDraft = {
      account,
      trade_datetime: `${today}T09:30`,
      ticker: '',
      action: 'Open',
      strategy: 'CFM',
      side: 'Call',
      contracts: undefined,
      strike: undefined,
      expiry: undefined,
      premium: undefined,
      underlying: undefined,
      condition: undefined,
      base_position_id: undefined,
      base_leg_id: undefined,
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
    this.baseLegIntrinsicPreview = undefined;
    this.baseLegExtrinsicPreview = undefined;
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
      underlying_price: undefined,
      delta: undefined,
      fees: 0,
      amount: 0,
      tag: 'OPEN',
      condition: undefined,
    };
  }

  private buildBlankCashMovement(account?: string): CashMovement {
    const today = new Date().toISOString().slice(0, 10);
    return {
      movement_id: this.newId(),
      account: account || '',
      date: today,
      direction: 'DEPOSIT',
      purpose: 'ACCOUNT',
      amount: 0,
      position_id: undefined,
      note: '',
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
      this.baseLegLookup = {};
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
        this.baseLegLookup = grouped;
        this.baseLegOptions = Object.values(grouped)
          .filter((g) => g.open && g.mark && g.net > 0)
          .map((g) => g.open as BaseLeg);
      },
      error: () => {
        this.baseLegOptions = [];
        this.baseLegLookup = {};
      },
    });
  }

  onBaseLegSelect(legId: string): void {
    this.selectedBaseLegId = legId;
    if (!legId) {
      this.baseLegDraft = this.buildBlankBaseLeg();
      this.baseLegIntrinsicPreview = undefined;
      this.baseLegExtrinsicPreview = undefined;
      this.baseLegDraft.position_id = this.selectedPositionId || '';
      return;
    }
    const entry = this.baseLegLookup[legId];
    const leg = entry?.mark || entry?.open;
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
    this.recomputeBaseLegAmount();
  }

  loadTradeBaseLegOptions(): void {
    this.dashboardService.listBaseLegs().subscribe({
      next: (legs) => {
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
        this.tradeBaseLegLookup = grouped;
        this.tradeBaseLegOptions = Object.values(grouped)
          .filter((g) => g.open && g.mark && g.net > 0)
          .map((g) => g.open as BaseLeg);
      },
      error: () => {
        this.tradeBaseLegOptions = [];
        this.tradeBaseLegLookup = {};
      },
    });
  }

  filteredTradeBaseLegOptions(): BaseLeg[] {
    const positionId = this.selectedTradePositionId || this.tradeDraft?.base_position_id;
    if (!positionId) {
      return this.tradeBaseLegOptions;
    }
    return this.tradeBaseLegOptions.filter((leg) => leg.position_id === positionId);
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
    if (draft && this.normalizeStrategy(draft.strategy) === 'CFM') {
      draft.side = 'Call';
    }
  }

  private tradeContractLimit(): number | null {
    const legId = this.selectedTradeBaseLegId || this.tradeDraft?.base_leg_id;
    if (!legId) {
      return null;
    }
    const entry = this.tradeBaseLegLookup[legId];
    const candidate = entry?.net ?? entry?.open?.quantity ?? entry?.mark?.quantity;
    const numeric = this.toNumber(candidate as number | string | undefined);
    if (numeric === undefined || numeric <= 0) {
      return null;
    }
    return Math.floor(numeric);
  }

  private applyTradeContractLimit(force: boolean = false): void {
    if (this.tradeDraft.action !== 'Open') {
      return;
    }
    const maxContracts = this.tradeContractLimit();
    if (maxContracts === null) {
      return;
    }
    const current = this.toNumber(this.tradeDraft.contracts);
    if (force || current === undefined || current > maxContracts) {
      this.tradeDraft.contracts = maxContracts;
    }
  }

  private updateLedgerFilterOptions(summaries: LedgerSummary[]): void {
    const tickers = new Set<string>();
    const sides = new Set<string>();
    const strikes = new Set<string>();
    const expiries = new Set<string>();
    const baseLegIds = new Set<string>();

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
      summary.rows?.forEach((row) => {
        const value = (row.base_leg_id || '').toString().trim();
        if (value) {
          baseLegIds.add(value);
        }
      });
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

    this.baseLegFilterOptions = Array.from(baseLegIds).sort();
    if (this.selectedBaseLegIds.length) {
      const available = new Set(this.baseLegFilterOptions);
      this.selectedBaseLegIds = this.selectedBaseLegIds.filter((baseLegId) => available.has(baseLegId));
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
    if (this.selectedBaseLegIds.length) {
      const selected = new Set(this.selectedBaseLegIds);
      const rows = this.ledgerRows.filter((row) =>
        selected.has((row.base_leg_id || '').toString().trim())
      );
      summaries = buildLedgerSummaries(rows, this.contractMultiplier);
    }
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
      if (action.includes('mark')) {
        return;
      }
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
      base_leg_id?: string | null;
      ticker?: string | null;
      strategy?: string | null;
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
          base_leg_id: row.base_leg_id,
          ticker: row.ticker,
          strategy: row.strategy,
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
    const baseLegId = this.selectedTradeBaseLegId || this.tradeDraft?.base_leg_id;
    const basePositionId = this.selectedTradePositionId || this.tradeDraft?.base_position_id;
    if (baseLegId) {
      this.availableOpenShorts = this.openShortOptions.filter((opt) => opt.base_leg_id === baseLegId);
    } else if (basePositionId) {
      this.availableOpenShorts = this.openShortOptions.filter((opt) => opt.base_position_id === basePositionId);
    } else {
      this.availableOpenShorts = [...this.openShortOptions];
    }
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
    if (opt.ticker) {
      this.tradeDraft.ticker = opt.ticker;
    }
    if (opt.strategy) {
      this.tradeDraft.strategy = this.normalizeStrategy(opt.strategy);
    }
    if (opt.side) {
      this.tradeDraft.side = opt.side as any;
    }
    if (opt.base_position_id) {
      this.tradeDraft.base_position_id = opt.base_position_id;
    }
    if (opt.base_leg_id) {
      this.tradeDraft.base_leg_id = opt.base_leg_id;
    }
    this.tradeDraft.action = 'Close';
    this.tradeDraft.strike = opt.strike ?? this.tradeDraft.strike;
    this.tradeStrikeLocked = opt.strike !== undefined && opt.strike !== null;
    this.tradeDraft.expiry = opt.expiry ?? this.tradeDraft.expiry;
    this.tradeExpiryLocked = !!opt.expiry;
    this.tradeDraft.contracts = opt.remaining ?? this.tradeDraft.contracts;
    this.tradeTickerLocked = !!this.tradeDraft.ticker;
    this.tradeStrategyLocked = !!this.tradeDraft.strategy;
    this.tradeSideLocked = !!this.tradeDraft.side;
  }

}
