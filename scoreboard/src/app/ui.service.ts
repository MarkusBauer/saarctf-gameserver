import {Injectable} from '@angular/core';
import {SessionStorage} from "ngx-store-9";

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

	constructor() {
	}
}
