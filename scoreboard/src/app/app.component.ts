import {Component} from '@angular/core';
import {setTheme} from "ngx-bootstrap/utils";
import { environment } from '../environments/environment';

@Component({
    selector: 'app-root',
    templateUrl: 'app.component.html',
    styleUrls: ['app.component.less'],
    standalone: false
})
export class AppComponent {
	title = 'scoreboard';
    ctfName = environment.ctf_name;

	constructor() {
		setTheme('bs4');
	}
}
