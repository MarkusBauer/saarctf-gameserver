import {Injectable} from '@angular/core';
import {Subject} from "rxjs";
import {setSchemeDarkmode} from "./chart-colorschemes";
import {SessionStorage} from "@efaps/ngx-store";

/**
 * Service storing user preferences (in session storage for persistence).
 */
@Injectable({
	providedIn: 'root'
})
export class UiService {

	@SessionStorage({key: 'showHistory'})
	public showHistory: boolean = true;
	@SessionStorage({key: 'showOnlySums'})
	public showOnlySums: boolean = false;
	@SessionStorage({key: 'showImages'})
	public showImages: boolean = true;
	@SessionStorage({key: 'showNotifications'})
	public showNotifications: boolean = true;
	@SessionStorage({key: 'darkmode'})
	public darkmode: boolean = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
	public darkmodeChanges = new Subject<boolean>();

	constructor() {
		this.setDarkmode(this.darkmode);
	}

	setDarkmode(enabled: boolean) {
		if (enabled) {
			document.body.parentElement.classList.add('dark');
		} else {
			document.body.parentElement.classList.remove('dark');
		}
		setSchemeDarkmode(enabled);
		if (enabled != this.darkmode) {
			this.darkmodeChanges.next(enabled);
		}
		this.darkmode = enabled;
	}
}
