import {Component, OnDestroy, OnInit} from '@angular/core';
import {BackendService, GameStates} from "../backend.service";

@Component({
    selector: 'app-current-tick',
    templateUrl: './current-tick.component.html',
    styleUrls: ['./current-tick.component.less'],
    standalone: false
})
export class CurrentTickComponent implements OnInit, OnDestroy {

	public currentTime = 0;
	public currentTimeInterval;
	public GameStates = GameStates;

	constructor(public backend: BackendService) {
	}

	ngOnInit() {
		this.currentTimeInterval = setInterval(() => this.currentTime = Math.round(new Date().getTime() / 1000), 500);
	}

	ngOnDestroy() {
		clearInterval(this.currentTimeInterval);
	}

	formatRemainingTime(currentTime: number) {
		// server time offset!
		let remaining = this.backend.currentState.current_tick_until - currentTime + this.backend.deltaClientToServer;
		if (remaining < 0) remaining = 0;
		let m = Math.floor(remaining / 60);
		let s = Math.floor(remaining % 60);
		return (m < 10 ? '0' + m : m) + ':' + (s < 10 ? '0' + s : s);
	}
}
