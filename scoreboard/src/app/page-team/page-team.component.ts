import {Component, ElementRef, Injectable, OnDestroy, OnInit, ViewChild} from '@angular/core';
import {ActivatedRoute} from "@angular/router";
import {interval, combineLatest, Subject, Subscription} from "rxjs";
import {BackendService} from "../backend.service";
import {Rank, RoundInformation} from "../models";
import {UiService} from "../ui.service";
import {KeyValue} from "@angular/common";
import {Chart, ChartData, ChartOptions} from "chart.js";
import {BaseChartDirective} from "ng2-charts";
import {addScheme, COLORS} from "../chart-colorschemes";


@Injectable()
export abstract class StatisticsComponentBase implements OnInit, OnDestroy {
    public loading: number = 0;
    public currentTick: number = null;
    public currentRoundInfo: RoundInformation = null;

    private darkmodeSubscription: Subscription;
    private newestScoreboardTickSubscription: Subscription;

    constructor(public backend: BackendService, public ui: UiService) {
    }

    ngOnInit(): void {
        this.newestScoreboardTickSubscription = this.backend.newestScoreboardTick.subscribe(tick => {
            this.setCurrentTick(tick);
        });
        this.darkmodeSubscription = this.ui.darkmodeChanges.subscribe(darkmode => this.updateChartColors());
    }

    ngOnDestroy() {
        this.newestScoreboardTickSubscription.unsubscribe();
        this.darkmodeSubscription.unsubscribe();
    }

    protected abstract updateChartColors();

    protected setCurrentTick(tick: number) {
        this.currentTick = tick;
        if (tick >= 0 || tick == -1) {
            this.loading++;
            this.backend.getRanking(tick).subscribe(roundinfo => {
                this.loading--;
                this.currentRoundInfo = roundinfo;
                this.setCurrentRoundInfo(tick, roundinfo);
            });
        }
    }

    protected abstract setCurrentRoundInfo(tick: number, roundinfo: RoundInformation) ;
}


@Component({
    selector: 'app-page-team',
    templateUrl: './page-team.component.html',
    styleUrls: ['./page-team.component.less'],
    standalone: false
})
export class PageTeamComponent extends StatisticsComponentBase {

    public teamId: number = null;
    public tickInfos: { [key: number]: Rank } = {};
    public tickInfosLength: number = 0;
    public numResults: number = 7;

    // the team behind this one
    private dataAfterUs = addScheme({
        data: [],
        label: "team1",
        fill: false,
        pointRadius: 0,
        stack: '0',
        borderDash: [5, 5]
    }, 0, true);
    // the team before this one
    private dataBeforeUs = addScheme({
        data: [],
        label: "team3",
        fill: false,
        pointRadius: 0,
        stack: '1',
        borderDash: [10, 5]
    }, 1, true);
    public chartData: ChartData = {
        datasets: [],
        labels: []
    };
    public chartOptions: ChartOptions = {
        maintainAspectRatio: false,
        responsive: true,
        interaction: {
            mode: 'nearest',
            axis: 'x',
            intersect: false
        },
        scales: {
            y: {stacked: true, min: 0},
        },
    };
    @ViewChild(BaseChartDirective) chart?: BaseChartDirective;

    @ViewChild('loadMoreSpinner', {static: true}) loadMoreSpinner: ElementRef;

    private loadMoreSpinnerSubscription: Subscription;

    constructor(backend: BackendService, ui: UiService, private route: ActivatedRoute) {
        super(backend, ui);
    }

    ngOnInit(): void {
        super.ngOnInit();
        this.route.paramMap.subscribe(map => {
            this.teamId = parseInt(map.get('teamid'));
            this.tickInfos = {};
            this.tickInfosLength = 0;
            this.numResults = 7;
            if (this.currentTick !== null) {
                this.fetchRoundInfos(this.numResults, true);
            }
        });

        let isSpinnerShowing = new Subject();
        let observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                isSpinnerShowing.next(entry.isIntersecting);
            });
        });
        observer.observe(this.loadMoreSpinner.nativeElement);

        this.loadMoreSpinnerSubscription =
            combineLatest([interval(500), isSpinnerShowing]).subscribe(([_, isShowing]) => {
                if (isShowing && this.loading == 0) {
                    this.loadMore();
                    if (document.scrollingElement.clientHeight + document.scrollingElement.scrollTop
                        == document.scrollingElement.scrollHeight) {
                        // prevent staying completely scrolled down
                        document.scrollingElement.scrollBy(0, -1);
                    }
                }
            });
        this.loadMoreSpinnerSubscription.add(() => observer.disconnect());
    }

    ngOnDestroy() {
        super.ngOnDestroy();
        this.loadMoreSpinnerSubscription.unsubscribe();
    }

    setCurrentRoundInfo(tick: number, roundinfo: RoundInformation) {
        if (tick >= 0) {
            this.addRoundInfo(roundinfo);
            this.fetchRoundInfos(this.numResults, true);
        } else {
            this.updateGraph();
        }
    }

    addRoundInfo(ri: RoundInformation) {
        for (let rank of ri.scoreboard) {
            if (rank.team_id === this.teamId) {
                this.tickInfos[ri.tick] = rank;
                this.tickInfosLength = Object.keys(this.tickInfos).length;
                break;
            }
        }
    }

    fetchRoundInfos(count: number, updateGraph = false) {
        for (let i = this.currentTick; i > this.currentTick - count; i--) {
            if (i >= 0 && !this.tickInfos[i]) {
                this.loading++;
                this.backend.getRanking(i).subscribe(ri => {
                    this.addRoundInfo(ri);
                    this.loading--;
                    if (updateGraph && ri.tick == this.currentTick)
                        this.updateGraph();
                });
            } else if (updateGraph && i == this.currentTick) {
                this.updateGraph();
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

    updateGraph() {
        if (!this.currentRoundInfo || this.currentRoundInfo.tick < 0 || this.teamId === null)
            return;
        // Get team before/after
        let teamAfterUs: number = null;
        let teamBeforeUs: number = null;
        for (let i = 0; i < this.currentRoundInfo.scoreboard.length; i++) {
            if (this.currentRoundInfo.scoreboard[i].team_id === this.teamId) {
                if (i > 0)
                    teamBeforeUs = this.currentRoundInfo.scoreboard[i - 1].team_id;
                if (i + 1 < this.currentRoundInfo.scoreboard.length)
                    teamAfterUs = this.currentRoundInfo.scoreboard[i + 1].team_id;
                break;
            }
        }
        // Update other team series
        let pos = 0;
        if (teamBeforeUs !== null) {
            if (this.chartData.datasets.length <= pos || this.chartData.datasets[pos] != this.dataBeforeUs) {
                this.chartData.datasets.splice(pos, 0, this.dataBeforeUs);
            }
            let beforePos = pos;
            this.backend.getTeamPointHistorySimple(teamBeforeUs).subscribe(points => {
                this.chartData.datasets[beforePos].data = points;
                this.chart?.update();
            });
            this.chartData.datasets[pos].label = 'Team ' + this.backend.teams[teamBeforeUs].name;
            pos++;
        } else if (this.chartData.datasets.length > pos && this.chartData.datasets[pos] == this.dataBeforeUs) {
            this.chartData.datasets.splice(pos, 1);
        }
        if (teamAfterUs !== null) {
            if (this.chartData.datasets.length <= pos || this.chartData.datasets[pos] != this.dataAfterUs) {
                this.chartData.datasets.splice(pos, 0, this.dataAfterUs);
            }
            let afterPos = pos;
            this.backend.getTeamPointHistorySimple(teamAfterUs).subscribe(points => {
                this.chartData.datasets[afterPos].data = points;
                this.chart?.update();
            });
            this.chartData.datasets[pos].label = 'Team ' + this.backend.teams[teamAfterUs].name;
            pos++;
        } else if (this.chartData.datasets.length > pos && this.chartData.datasets[pos] == this.dataAfterUs) {
            this.chartData.datasets.splice(pos, 1);
        }

        // Update service series
        let serviceOffset = pos;
        for (let i = 0; i < this.currentRoundInfo.services.length; i++) {
            if (this.chartData.datasets.length <= pos) {
                this.chartData.datasets.push(addScheme({
                    data: [], label: this.currentRoundInfo.services[i].name,
                    fill: true, pointRadius: 0
                }, (i % (COLORS.length - 2)) + 2));
            } else {
                this.chartData.datasets[pos].label = this.currentRoundInfo.services[i].name;
            }
            pos++;
        }
        while (this.chartData.datasets.length > pos) {
            this.chartData.datasets.pop();
        }
        while (this.chartData.labels.length <= this.currentTick) {
            this.chartData.labels.push(this.chartData.labels.length);
        }

        // Get the necessary data
        this.backend.getTeamPointHistory(this.teamId).subscribe(points => {
            for (let i = 0; i < points.length; i++) {
                this.chartData.datasets[i + serviceOffset].data = points[i];
            }
            this.chart?.update();
        });
    }

    updateChartColors() {
        this.chartOptions.color = Chart.defaults.color;
        addScheme(this.dataAfterUs, 0, true);
        addScheme(this.dataBeforeUs, 1, true);
        for (let ds of this.chartData.datasets) {
            if (ds['colorIndex'] > 1)
                addScheme(ds, ds['colorIndex'], false);
        }
        this.chartOptions = {...this.chartOptions};
        this.chart?.update();
    }
}