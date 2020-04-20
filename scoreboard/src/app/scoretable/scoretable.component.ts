import {Component, OnDestroy, OnInit} from '@angular/core';
import {BackendService} from "../backend.service";
import {Rank, RoundInformation} from "../models";
import {Subscription} from "rxjs";
import {UiService} from "../ui.service";

@Component({
	selector: 'app-scoretable',
	templateUrl: './scoretable.component.html',
	styleUrls: ['./scoretable.component.less']
})
export class ScoretableComponent implements OnInit, OnDestroy {

	public info: RoundInformation = {tick: -1, services: [], scoreboard: []};

	public shownTick: number = -1;
	private shownTickIsRecent: boolean = true;
	private newestScoreboardTickSubscription: Subscription;
	private rankingSubscription: Subscription;

	constructor(public backend: BackendService, public ui: UiService) {
		window['showTick'] = (num) => this.showTick(num);
	}

	ngOnInit() {
		this.newestScoreboardTickSubscription = this.backend.newestScoreboardTick.subscribe(tick => {
			if (this.shownTickIsRecent)
				this.showTick(tick)
		});
	}

	ngOnDestroy() {
		if (this.rankingSubscription) {
			this.rankingSubscription.unsubscribe();
			this.rankingSubscription = null;
		}
		this.newestScoreboardTickSubscription.unsubscribe();
	}

	showTick(num: number) {
		if (this.rankingSubscription) {
			this.rankingSubscription.unsubscribe();
			this.rankingSubscription = null;
		}
		console.log('New tick: ', num);
		this.shownTick = num;
		this.shownTickIsRecent = num == this.backend.currentState.scoreboard_tick;
		this.rankingSubscription = this.backend.getRanking(num).subscribe(rank => this.info = rank);
	}

	teamTrackBy(index, item: Rank) {
		return item.team_id;
	}

	indexTrack(index, item) {
		return index;
	}

	statusToClass(status: string): string {
		switch (status) {
			case 'SUCCESS':
				return 'label-success';
			case 'FLAGMISSING':
			case 'MUMBLE':
				return 'label-warning';
			case 'OFFLINE':
			case 'TIMEOUT':
			case 'CRASH':
				return 'label-danger';
			case 'REVOKED':
			case 'PENDING':
			default:
				return 'label-default';
		}
	}

	statusToTooltip(status: string): string {
		switch (status) {
			case 'SUCCESS':
				return 'Service online';
			case 'FLAGMISSING':
				return 'No flag found';
			case 'MUMBLE':
				return 'Mumble';
			case 'OFFLINE':
			case 'TIMEOUT':
				return 'Service unreachable';
			case 'CRASH':
				return 'Checker crashed';
			case 'REVOKED':
			case 'PENDING':
				return 'Not checked';
			default:
				return status;
		}
	}

	statusToText(status: string): string {
		switch (status) {
			case 'SUCCESS':
				return 'up';
			case 'FLAGMISSING':
				return 'flag';
			case 'MUMBLE':
				return 'mumble';
			case 'OFFLINE':
			case 'TIMEOUT':
				return 'down';
			case 'CRASH':
			case 'REVOKED':
			case 'PENDING':
			default:
				return '-';
		}
	}

	floatToString(n: number, zeroIsNegative = false): string {
		if (zeroIsNegative) {
			return (n > 0 ? '+' : (n === 0.0 ? '-' : '')) + n.toFixed(1);
		}
		return (n < 0 ? '' : '+') + n.toFixed(1);
	}

	intToString(n: number, zeroIsNegative = false): string {
		if (zeroIsNegative) {
			return (n > 0 ? '+' : (n === 0.0 ? '-' : ''));
		}
		return (n < 0 ? '' : '+') + n;
	}

}
