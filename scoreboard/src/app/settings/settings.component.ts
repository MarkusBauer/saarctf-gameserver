import {Component, OnInit} from '@angular/core';
import {BsDropdownConfig} from "ngx-bootstrap/dropdown";
import {UiService} from "../ui.service";

@Component({
    selector: 'app-settings',
    templateUrl: './settings.component.html',
    styleUrls: ['./settings.component.less'],
    providers: [{ provide: BsDropdownConfig, useValue: { isAnimated: false, autoClose: false } }],
    standalone: false
})
export class SettingsComponent implements OnInit {

	constructor(public ui: UiService) {
	}

	ngOnInit() {
	}

}
