import {Component} from '@angular/core';
import {setTheme} from "ngx-bootstrap";

@Component({
	selector: 'app-root',
	templateUrl: 'app.component.html',
	styleUrls: ['app.component.less']
})
export class AppComponent {
	title = 'scoreboard';

	constructor() {
		setTheme('bs3');
	}
}
