import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';

import { CfmDashboardComponent } from './cfm-dashboard/cfm-dashboard.component';
import { LegacyDashboardComponent } from './legacy-dashboard/legacy-dashboard.component';

const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard/cfm' },
  { path: 'dashboard/cfm', component: CfmDashboardComponent },
  { path: 'dashboard/legacy', component: LegacyDashboardComponent },
  { path: '**', redirectTo: 'dashboard/cfm' },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule],
})
export class AppRoutingModule {}
