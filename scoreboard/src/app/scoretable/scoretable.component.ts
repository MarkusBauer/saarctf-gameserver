import {Component, OnDestroy, OnInit} from '@angular/core';
import {BackendService} from "../backend.service";
import {Rank, RoundInformation} from "../models";
import {Subscription} from "rxjs";
import {UiService} from "../ui.service";
import {StatusUtils} from "../table-line-cells/table-line-cells.component";


@Component({
    template: '',
})
export abstract class RoundInfoListeningComponent implements OnInit, OnDestroy {
    protected shownTickIsRecent: boolean = true;
    protected newestScoreboardTickSubscription: Subscription;

    private rankingSubscription: Subscription;
    public shownTick: number = -1;

    public info: RoundInformation = {tick: -1, services: [], scoreboard: []};

    constructor(public backend: BackendService) {
    }

    public statusToClass = StatusUtils.statusToClass;
    public statusToTooltip = StatusUtils.statusToTooltip;
    public statusToText = StatusUtils.statusToText;

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

    floatToString(n: number, zeroIsNegative = false): string {
        if (zeroIsNegative) {
            return (n > 0 ? '+' : (n === 0.0 ? '-' : '')) + n.toFixed(1);
        }
        return (n < 0 ? '' : '+') + n.toFixed(1);
    }
}


@Component({
    selector: 'app-scoretable',
    templateUrl: './scoretable.component.html',
    styleUrls: ['./scoretable.component.less']
})
export class ScoretableComponent extends RoundInfoListeningComponent implements OnInit, OnDestroy {

    constructor(backend: BackendService, public ui: UiService) {
        super(backend);
        window['showTick'] = (num) => this.showTick(num);
    }
}
