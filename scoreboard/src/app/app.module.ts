import {BrowserModule} from '@angular/platform-browser';
import {NgModule} from '@angular/core';
import {AppRoutingModule} from './app-routing.module';
import {AppComponent} from './app.component';
import {ScoretableComponent} from './scoretable/scoretable.component';
import {provideHttpClient, withInterceptorsFromDi} from "@angular/common/http";
import {CurrentTickComponent} from './current-tick/current-tick.component';
import {PopoverModule} from "ngx-bootstrap/popover";
import {BsDropdownModule} from "ngx-bootstrap/dropdown";
import {SettingsComponent} from './settings/settings.component';
import {BrowserAnimationsModule} from "@angular/platform-browser/animations";
import {NotificationOverlayComponent} from './notification-overlay/notification-overlay.component';
import {PageIndexComponent} from './page-index/page-index.component';
import {PageTeamComponent} from './page-team/page-team.component';
import {PageNotFoundComponent} from './page-not-found/page-not-found.component';
import {TableLineCellsComponent} from './table-line-cells/table-line-cells.component';
import {TableServiceHeaderCellComponent} from './table-service-header-cell/table-service-header-cell.component';
import {BaseChartDirective, provideCharts, withDefaultRegisterables} from "ng2-charts";
import {PageGraphsComponent} from './page-graphs/page-graphs.component';
import {WebStorageModule} from "@efaps/ngx-store";

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
    bootstrap: [AppComponent],
    imports: [
        BrowserModule,
        BrowserAnimationsModule,
        AppRoutingModule,
        PopoverModule.forRoot(),
        BsDropdownModule.forRoot(),
        WebStorageModule,
        BaseChartDirective,
    ],
    providers: [
        provideHttpClient(withInterceptorsFromDi()),
        provideCharts(withDefaultRegisterables())
    ]
})
export class AppModule {
}
