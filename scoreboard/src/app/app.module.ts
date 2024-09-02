import {BrowserModule} from '@angular/platform-browser';
import {NgModule} from '@angular/core';
import {AppRoutingModule} from './app-routing.module';
import {AppComponent} from './app.component';
import {ScoretableComponent} from './scoretable/scoretable.component';
import {HttpClientModule} from "@angular/common/http";
import {CurrentTickComponent} from './current-tick/current-tick.component';
import {PopoverModule} from "ngx-bootstrap/popover";
import {BsDropdownModule} from "ngx-bootstrap/dropdown";
import {SettingsComponent} from './settings/settings.component';
import {BrowserAnimationsModule} from "@angular/platform-browser/animations";
import {WebStorageModule} from "ngx-store";
import { NotificationOverlayComponent } from './notification-overlay/notification-overlay.component';
import { PageIndexComponent } from './page-index/page-index.component';
import { PageTeamComponent } from './page-team/page-team.component';
import { PageNotFoundComponent } from './page-not-found/page-not-found.component';
import { TableLineCellsComponent } from './table-line-cells/table-line-cells.component';
import { TableServiceHeaderCellComponent } from './table-service-header-cell/table-service-header-cell.component';
import {NgChartsModule} from "ng2-charts";
import { PageGraphsComponent } from './page-graphs/page-graphs.component';

@NgModule({
	declarations: [
		AppComponent,
		ScoretableComponent,
		CurrentTickComponent,
		SettingsComponent,
		NotificationOverlayComponent,
		PageIndexComponent,
		PageTeamComponent,
		PageNotFoundComponent,
		TableLineCellsComponent,
		TableServiceHeaderCellComponent,
  PageGraphsComponent
	],
	imports: [
		BrowserModule,
		HttpClientModule,
		BrowserAnimationsModule,
		AppRoutingModule,
		PopoverModule.forRoot(),
		BsDropdownModule.forRoot(),
		WebStorageModule.forRoot(),
		NgChartsModule.forRoot()
	],
	providers: [],
	bootstrap: [AppComponent]
})
export class AppModule {
}
