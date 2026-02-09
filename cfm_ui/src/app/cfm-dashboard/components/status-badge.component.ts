import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-status-badge',
  template: '<span [ngClass]="badgeClass">{{ label }}</span>',
})
export class StatusBadgeComponent {
  @Input({ required: true }) label!: string;
  @Input() tone: 'green' | 'yellow' | 'red' | 'neutral' = 'neutral';

  get badgeClass(): string {
    const base = 'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold';

    switch (this.tone) {
      case 'green':
        return `${base} border-emerald-400/40 bg-emerald-400/15 text-emerald-300`;
      case 'yellow':
        return `${base} border-amber-400/40 bg-amber-400/15 text-amber-200`;
      case 'red':
        return `${base} border-rose-400/40 bg-rose-400/15 text-rose-200`;
      default:
        return `${base} border-slate-500/40 bg-slate-500/15 text-slate-200`;
    }
  }
}
