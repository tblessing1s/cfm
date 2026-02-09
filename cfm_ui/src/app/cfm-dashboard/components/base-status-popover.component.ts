import { Component, ElementRef, HostListener } from '@angular/core';

import { BASE_STATUS_DEFINITIONS } from '../cfm-dashboard.constants';

@Component({
  selector: 'app-base-status-popover',
  templateUrl: './base-status-popover.component.html',
  styleUrls: ['./base-status-popover.component.css'],
})
export class BaseStatusPopoverComponent {
  open = false;
  readonly definitions = BASE_STATUS_DEFINITIONS;

  constructor(private readonly elementRef: ElementRef) {}

  toggle(): void {
    this.open = !this.open;
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.elementRef.nativeElement.contains(event.target)) {
      this.open = false;
    }
  }
}
