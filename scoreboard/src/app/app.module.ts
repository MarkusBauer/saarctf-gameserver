import {BrowserModule} from '@angular/platform-browser';
import {NgModule} from '@angular/core';

import {AppComponent} from './app.component';
import {ScoretableComponent} from './scoretable/scoretable.component';
import {HttpClientModule} from "@angular/common/http";
import {CurrentTickComponent} from './current-tick/current-tick.component';
import {PopoverModule} from "ngx-bootstrap/popover";
import {BsDropdownModule} from "ngx-bootstrap/dropdown";
import {SettingsComponent} from './settings/settings.component';
import {BrowserAnimationsModule} from "@angular/platform-browser/animations";
//import {WebStorageModule} from "ngx-store-9";
import { NotificationOverlayComponent } from './notification-overlay/notification-overlay.component';

@NgModule({
	declarations: [
		AppComponent,
		ScoretableComponent,
		CurrentTickComponent,
		SettingsComponent,
		NotificationOverlayComponent
	],
	imports: [
		BrowserModule,
		HttpClientModule,
		BrowserAnimationsModule,
		PopoverModule.forRoot(),
		BsDropdownModule.forRoot(),
		//WebStorageModule
	],
	providers: [],
	bootstrap: [AppComponent]
})
export class AppModule {
}
