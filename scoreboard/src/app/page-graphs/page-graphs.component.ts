import {Component, QueryList, ViewChildren} from '@angular/core';
import {BackendService} from "../backend.service";
import {forkJoin, Observable, Subscription} from "rxjs";
import {Chart, ChartData, ChartOptions} from "chart.js";
import {BaseChartDirective} from "ng2-charts";
import {UiService} from "../ui.service";
import {addScheme, COLORS} from "../chart-colorschemes";
import {StatisticsComponentBase} from "../page-team/page-team.component";
import {RoundInformation, Service, Team} from "../models";

@Component({
    selector: 'app-page-graphs',
    templateUrl: './page-graphs.component.html',
    styleUrls: ['./page-graphs.component.less']
})
export class PageGraphsComponent extends StatisticsComponentBase {

    public chartDatas: { chart: ChartData, title: string }[] = [];
    public chartOptions: ChartOptions = {
        maintainAspectRatio: false,
        responsive: true,
        interaction: {
            mode: 'nearest',
            axis: 'x',
            intersect: false
        },
        scales: {
            y: {stacked: false, min: 0},
        },
    };

    @ViewChildren(BaseChartDirective) charts: QueryList<BaseChartDirective>;

    constructor(public backend: BackendService, public ui: UiService) {
        super(backend, ui);
    }

    protected setCurrentRoundInfo(tick: number, roundinfo: RoundInformation) {
        console.log('SET TICK', tick, roundinfo.tick, this.currentRoundInfo.tick);
        console.log(roundinfo.services);
        this.retrieveData();
    }

    protected updateChartColors() {
        this.chartOptions.color = Chart.defaults.color;
        for (let chart of this.chartDatas) {
            for (let ds of chart.chart.datasets) {
                if (ds['colorIndex'] > 1)
                    addScheme(ds, ds['colorIndex'], false);
            }
        }
        this.chartOptions = {...this.chartOptions};
        this.updateCharts();
    }

    private retrieveData() {
        if (Object.keys(this.backend.teams).length == 0) {
            console.warn('No teams in backend');
            return;
        }
        console.log('retrieveData start...');

        let teams = [];
        let services = this.currentRoundInfo.services;
        let subscriptions: Observable<number[][]>[] = [];
        for (let i = 0; i < this.currentRoundInfo.scoreboard.length && i < 10; i++) {
            let team = this.backend.teams[this.currentRoundInfo.scoreboard[i].team_id];
            teams.push(team);
            subscriptions.push(this.backend.getTeamPointHistory(team.id));
        }

        this.loading++;
        forkJoin(subscriptions).subscribe(points => {
            this.loading--;
            this.setPoints(teams, services, points);
            console.log('retrieveData end...');
        })
    }

    /**
     *
     * @param teams
     * @param services
     * @param points Structure: points[team-index][service-index][tick]
     * @private
     */
    private setPoints(teams: Team[], services: Service[], points: number[][][]) {
        this.chartDatas = [
            {
                chart: this.chartFromArray(teams, this.extractSum(points)),
                title: "Points (overall)"
            }
        ];

        for (let serviceIndex = 0; serviceIndex < services.length; serviceIndex++) {
            let service = services[serviceIndex];
            this.chartDatas.push({
                chart: this.chartFromArray(teams, this.extractIndex(points, serviceIndex)),
                //title: `Points (service ${index + 1})`
                title: `Points (service ${service.name})`
            });
        }
        this.updateCharts();
        setTimeout(() => this.updateCharts(), 20);
    }

    private updateCharts() {
        if (this.charts) {
            for (let chart of this.charts) {
                chart.update();
            }
        }
    }

    private extractIndex(points: number[][][], index: number): number[][] {
        return points.map(teampoints => teampoints[index]);
    }

    private extractSum(points: number[][][]): number[][] {
        let result = [];
        for (let i = 0; i < points.length; i++) {
            result.push(points[i][0].map(x => x));
            for (let j = 1; j < points[i].length; j++) {
                for (let k = 0; k < points[i][j].length; k++) {
                    result[i][k] += points[i][j][k];
                }
            }
        }
        return result;
    }

    private chartFromArray(teams: Team[], points: number[][]) {
        let datasets = [];
        let labels = [];
        for (let i = 0; i < teams.length; i++) {
            datasets.push(addScheme({
                data: points[i],
                label: teams[i].name,
                pointRadius: 0
            }, (teams[i].id % (COLORS.length - 2)) + 2));

            while (labels.length < points[i].length) {
                labels.push(labels.length);
            }
        }

        return {datasets, labels};
    }
}