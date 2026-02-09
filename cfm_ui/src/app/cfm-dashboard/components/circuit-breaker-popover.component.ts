import { Component, ElementRef, HostListener, Input } from '@angular/core';

import {
  CIRCUIT_BREAKER_QUESTIONS,
  CIRCUIT_BREAKER_STATUS_LABELS,
} from '../cfm-dashboard.constants';
import { CircuitBreakers, CircuitBreakerStatus } from '../cfm-dashboard.models';
import { computeCircuitBreakerStatus } from '../cfm-dashboard.utils';

@Component({
  selector: 'app-circuit-breaker-popover',
  templateUrl: './circuit-breaker-popover.component.html',
  styleUrls: ['./circuit-breaker-popover.component.css'],
})
export class CircuitBreakerPopoverComponent {
  @Input({ required: true }) circuitBreakers!: CircuitBreakers;
  @Input({ required: true }) status!: CircuitBreakerStatus;

  open = false;
  readonly questions = CIRCUIT_BREAKER_QUESTIONS;
  readonly statusLabels = CIRCUIT_BREAKER_STATUS_LABELS;

  constructor(private readonly elementRef: ElementRef) {}

  toggle(): void {
    this.open = !this.open;
  }

  get warningHit(): boolean {
    return (
      this.circuitBreakers.cb_8_21_cross ||
      this.circuitBreakers.cb_price_below_50 ||
      this.circuitBreakers.cb_drop_15_from_run_high
    );
  }

  get exitHit(): boolean {
    return (
      this.circuitBreakers.cb_below_50_2_closes ||
      this.circuitBreakers.cb_price_below_200 ||
      this.circuitBreakers.cb_50_below_200 ||
      this.circuitBreakers.cb_drop_20_from_run_high
    );
  }

  answerForKey(key: string): string {
    const typedKey = key as keyof CircuitBreakers;
    return this.circuitBreakers[typedKey] ? 'Yes' : 'No';
  }

  statusTone(): 'green' | 'yellow' | 'red' {
    const computedStatus = computeCircuitBreakerStatus(this.circuitBreakers);
    if (computedStatus === CircuitBreakerStatus.Exit) {
      return 'red';
    }
    if (computedStatus === CircuitBreakerStatus.Warning) {
      return 'yellow';
    }
    return 'green';
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.elementRef.nativeElement.contains(event.target)) {
      this.open = false;
    }
  }
}
