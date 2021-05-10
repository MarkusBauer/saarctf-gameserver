import {Component, OnDestroy, OnInit} from '@angular/core';
import {ActivatedRoute} from "@angular/router";
import {Subscription} from "rxjs";
import {BackendService} from "../backend.service";
import {Rank, RoundInformation} from "../models";
import {UiService} from "../ui.service";
import {KeyValue} from "@angular/common";

@Component({
	selector: 'app-page-team',
	templateUrl: './page-team.component.html',
	styleUrls: ['./page-team.component.less']
})
export class PageTeamComponent implements OnInit, OnDestroy {

	public teamId: number = null;
	public currentTick: number = null;
	public currentRoundInfo: RoundInformation = null;
	public tickInfos: { [key: number]: Rank } = {};
	public tickInfosLength: number = 0;
	public numResults: number = 7;
	public loading: number = 0;

	private newestScoreboardTickSubscription: Subscription;

	constructor(public backend: BackendService, public ui: UiService, private route: ActivatedRoute) {
	}

	ngOnInit(): void {
		this.route.paramMap.subscribe(map => {
			this.teamId = parseInt(map.get('teamid'));
			this.tickInfos = {};
			this.tickInfosLength = 0;
			this.numResults = 7;
			if (this.currentTick !== null) {
				this.fetchRoundInfos(this.numResults);
			}
		});
		this.newestScoreboardTickSubscription = this.backend.newestScoreboardTick.subscribe(tick => {
			this.setCurrentTick(tick);
		});
	}

	ngOnDestroy() {
		this.newestScoreboardTickSubscription.unsubscribe();
	}

	setCurrentTick(tick: number) {
		this.currentTick = tick;
		if (tick >= 0 || tick == -1) {
			this.loading++;
			this.backend.getRanking(tick).subscribe(roundinfo => {
				this.loading--;
				this.currentRoundInfo = roundinfo;
				if (tick >= 0) {
					this.addRoundInfo(roundinfo);
					this.fetchRoundInfos(this.numResults);
				}
			});
		}
	}

	addRoundInfo(ri: RoundInformation) {
		for (let rank of ri.scoreboard) {
			if (rank.team_id == this.teamId) {
				this.tickInfos[ri.tick] = rank;
				this.tickInfosLength = Object.keys(this.tickInfos).length;
				break;
			}
		}
	}

	fetchRoundInfos(count: number) {
		for (let i = this.currentTick; i > this.currentTick - count; i--) {
			if (i >= 0 && !this.tickInfos[i]) {
				this.loading++;
				this.backend.getRanking(i).subscribe(ri => {
					this.addRoundInfo(ri);
					this.loading--;
				});
			}
		}
	}

	keyTrackBy(index, item: KeyValue<number, Rank>) {
		return item.key;
	}

	keyDescOrder = (a: KeyValue<string, Rank>, b: KeyValue<string, Rank>): number => {
		let keyA = parseInt(a.key);
		let keyB = parseInt(b.key);
		return keyA > keyB ? -1 : (keyB > keyA ? 1 : 0);
	}

	floatToString(n: number, zeroIsNegative = false): string {
		if (zeroIsNegative) {
			return (n > 0 ? '+' : (n === 0.0 ? '-' : '')) + n.toFixed(1);
		}
		return (n < 0 ? '' : '+') + n.toFixed(1);
	}

	loadMore() {
		this.numResults += 7;
		this.fetchRoundInfos(this.numResults);
	}

}
