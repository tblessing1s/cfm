import { LedgerRow } from '../services/dashboard.service';

export interface LedgerSummary {
  key: string;
  ticker: string;
  side: string;
  strike: number;
  expiry: string | null;
  netContracts: number;
  netPremium: number;
  netJuice: number;
  netJuicePer100: number;
  netProtection: number;
  rows: LedgerRow[];
}

export interface ExpiryTotal {
  expiry: string;
  netContracts: number;
  netPremium: number;
  netJuice: number;
  netJuicePer100: number;
  netProtection: number;
}

export interface ExpiryMonthGroup {
  month: string;
  netContracts: number;
  netPremium: number;
  netJuice: number;
  netJuicePer100: number;
  netProtection: number;
  children: ExpiryTotal[];
}

export type LedgerSortColumn =
  | 'date'
  | 'ticker'
  | 'side'
  | 'strike'
  | 'expiry'
  | 'netContracts'
  | 'netPremium'
  | 'netJuice'
  | 'netJuicePer100';

export type LedgerSortOrder = Array<{
  column: LedgerSortColumn;
  direction: 'asc' | 'desc';
}>;

export const DEFAULT_CONTRACT_MULTIPLIER = 100;
export const LEDGER_PLACEHOLDER = '—';

export const toNumber = (value: number | string | undefined | null): number | undefined => {
  if (value === undefined || value === null) {
    return undefined;
  }

  const asNumber = typeof value === 'string' ? parseFloat(value) : value;
  return Number.isFinite(asNumber) ? Number(asNumber) : undefined;
};

export const roundTo2 = (value: number): number => Math.round(value * 100) / 100;

export const sortLedgerRows = (rows: LedgerRow[]): LedgerRow[] =>
  [...rows].sort((a, b) => {
    const da = a.date ? new Date(a.date).getTime() : 0;
    const db = b.date ? new Date(b.date).getTime() : 0;
    return db - da;
  });

export const normalizeSideOption = (value: string | undefined): string => {
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
};

export const formatStrikeOption = (value: number | null | undefined): string => {
  if (!value || !Number.isFinite(value)) {
    return '';
  }
  const rounded = Math.round(value * 100) / 100;
  let label = rounded.toFixed(2);
  label = label.replace(/\.00$/, '');
  label = label.replace(/(\.\d)0$/, '$1');
  return label;
};

export const normalizeExpiryOption = (value: string | null | undefined): string => {
  const trimmed = (value || '').trim();
  return trimmed || LEDGER_PLACEHOLDER;
};

export const extractBaseKey = (row: LedgerRow): string | null => {
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
};

export const calculateJuicePerContractRaw = (row: LedgerRow): number | null => {
  const premium = toNumber(row.premium_buyback);
  if (premium === undefined) {
    return null;
  }
  const strike = toNumber(row.strike);
  const underlying = toNumber(row.underlying);
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

  return roundTo2(juice);
};

export const calculateJuicePerContract = (
  row: LedgerRow,
  contractMultiplier: number = DEFAULT_CONTRACT_MULTIPLIER
): number | null => {
  const raw = calculateJuicePerContractRaw(row);
  if (raw === null) {
    return null;
  }
  return roundTo2(Math.abs(raw) * contractMultiplier);
};

export const calculateSignedJuiceRaw = (
  row: LedgerRow,
  contractMultiplier: number = DEFAULT_CONTRACT_MULTIPLIER
): number | null => {
  const perContract = calculateJuicePerContractRaw(row);
  if (perContract === null) {
    return null;
  }
  const contracts = toNumber(row.contracts);
  if (contracts === undefined) {
    return null;
  }
  return roundTo2(perContract * contracts * contractMultiplier);
};

export const calculateSignedJuice = (
  row: LedgerRow,
  contractMultiplier: number = DEFAULT_CONTRACT_MULTIPLIER
): number | null => {
  const raw = calculateSignedJuiceRaw(row, contractMultiplier);
  if (raw === null) {
    return null;
  }
  return roundTo2(Math.abs(raw));
};

export const calculateSignedJuicePer100 = (
  row: LedgerRow,
  contractMultiplier: number = DEFAULT_CONTRACT_MULTIPLIER
): number | null => {
  const signed = calculateSignedJuiceRaw(row, contractMultiplier);
  if (signed === null) {
    return null;
  }
  return roundTo2(signed / contractMultiplier);
};

export const calculateProtectionRaw = (
  row: LedgerRow,
  contractMultiplier: number = DEFAULT_CONTRACT_MULTIPLIER
): number | null => {
  const juiceRaw = calculateSignedJuiceRaw(row, contractMultiplier);
  const premium = toNumber(row.premium_buyback);
  const contracts = toNumber(row.contracts) ?? 0;
  if (juiceRaw === null || premium === undefined) {
    return null;
  }
  const juiceAbs = Math.abs(juiceRaw);
  const premiumTotal = premium * contracts * contractMultiplier;
  const action = (row.action || '').toString().toLowerCase();
  const isClose = action.includes('close');
  const protection = premiumTotal - juiceAbs;
  return roundTo2(isClose ? -protection : protection);
};

export const calculateProtection = (
  row: LedgerRow,
  contractMultiplier: number = DEFAULT_CONTRACT_MULTIPLIER
): number | null => {
  const raw = calculateProtectionRaw(row, contractMultiplier);
  if (raw === null) {
    return null;
  }
  return roundTo2(Math.abs(raw));
};

export const buildLedgerSummaries = (
  rows: LedgerRow[],
  contractMultiplier: number = DEFAULT_CONTRACT_MULTIPLIER
): LedgerSummary[] => {
  const groups: Record<string, LedgerSummary> = {};

  rows.forEach((row) => {
    const baseKey = extractBaseKey(row);
    if (!baseKey) {
      return;
    }

    const action = (row.action || '').toLowerCase();
    const isClose = action.includes('close');
    const contracts = Number(row.contracts || 0);
    const premium = Number(row.premium_buyback || 0);
    const signedJuiceRaw = calculateSignedJuiceRaw(row, contractMultiplier) ?? 0;
    const protectionRaw = calculateProtectionRaw(row, contractMultiplier) ?? 0;

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
        netProtection: 0,
        rows: [],
      };
    }

    const summary = groups[baseKey];
    const contractDelta = isClose ? -contracts : contracts;
    const premiumTotal = premium * contracts * contractMultiplier;
    const premiumDelta = isClose ? -premiumTotal : premiumTotal;
    const protectionDelta = isClose ? -Math.abs(protectionRaw) : Math.abs(protectionRaw);
    const juiceDelta = signedJuiceRaw;

    summary.netContracts += contractDelta;
    summary.netPremium += premiumDelta;
    summary.netJuice += juiceDelta;
    summary.netProtection += protectionDelta;
    summary.rows.push(row);
  });

  Object.values(groups).forEach((summary) => {
    summary.netJuice = roundTo2(summary.netJuice);
    summary.netPremium = roundTo2(summary.netPremium);
    summary.netProtection = roundTo2(summary.netProtection);
    summary.netJuicePer100 = roundTo2(summary.netJuice / contractMultiplier);
  });

  return Object.values(groups);
};

export const computeExpiryTotals = (
  summaries: LedgerSummary[],
  contractMultiplier: number = DEFAULT_CONTRACT_MULTIPLIER
): ExpiryTotal[] => {
  const grouped: Record<string, ExpiryTotal> = {};
  summaries.forEach((summary) => {
    // Only include fully paired positions (netContracts == 0) in expiry totals.
    if (summary.netContracts !== 0) {
      return;
    }

    const key = summary.expiry || LEDGER_PLACEHOLDER;
    if (!grouped[key]) {
      grouped[key] = {
        expiry: key,
        netContracts: 0,
        netPremium: 0,
        netJuice: 0,
        netJuicePer100: 0,
        netProtection: 0,
      };
    }
    const bucket = grouped[key];
    bucket.netContracts += summary.netContracts;
    bucket.netPremium += summary.netPremium;
    bucket.netJuice += summary.netJuice;
    bucket.netProtection += summary.netProtection;
  });

  return Object.values(grouped)
    .map((item) => ({
      ...item,
      netJuicePer100: item.netJuice / contractMultiplier,
      netProtection: roundTo2(item.netProtection),
    }))
    .sort((a, b) => {
      if (a.expiry === LEDGER_PLACEHOLDER) return 1;
      if (b.expiry === LEDGER_PLACEHOLDER) return -1;
      return b.expiry.localeCompare(a.expiry);
    });
};

export const sortSummaries = (list: LedgerSummary[], orders: LedgerSortOrder): LedgerSummary[] => {
  const sorted = [...list].sort((a, b) => {
    for (const { column, direction } of orders) {
      const va = getSummarySortValue(a, column);
      const vb = getSummarySortValue(b, column);

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

    const da = getSummarySortValue(a, 'date') as number;
    const db = getSummarySortValue(b, 'date') as number;
    return db - da;
  });

  return sorted;
};

export const getSummarySortValue = (
  summary: LedgerSummary,
  column: LedgerSortColumn
): string | number => {
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
};
