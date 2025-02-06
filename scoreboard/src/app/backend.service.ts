import {Injectable} from '@angular/core';
import {RoundInformation, ServiceStat, ServiceStatsInformation, Team, TeamHistoryInformation} from "./models";
import {HttpClient} from "@angular/common/http";
import {map} from "rxjs/operators";
import {BehaviorSubject, Observable, of, Subject} from "rxjs";
import {retryWithBackoff} from "./retryWithBackoff";


export enum GameStates {
    STOPPED = 1,
    SUSPENDED = 2,
    RUNNING = 3
}

interface CurrentStateJson {
    current_tick: number;
    state: GameStates;
    current_tick_until: number;
    scoreboard_tick: number;
    banned_teams?: number[];
}


/**
 * Service storing data from backend, and retrieving data if necessary. Current state is automatically updated.
 * You can subscribe to: #newestScoreboardTick and #eventNotifications
 */
@Injectable({
    providedIn: 'root'
})
export class BackendService {

    private readonly url_base = 'api/';
    //private readonly url_base = 'http://localhost/scoreboard-api/api/';

    public teams: { [key: number]: Team } = {};

    private loadTeams() {
        this.http.get<Team[]>(this.url_base + 'scoreboard_teams.json')
            .pipe(retryWithBackoff(2000, 20))
            .subscribe(teams => {
                for (let id of Object.keys(teams))
                    teams[id].id = parseInt(id, 10);
                this.teams = teams;
            }, err => {
                console.error(err);
                setTimeout(() => this.loadTeams(), 5000);
            });
    }

    private round_ranking: { [key: number]: RoundInformation } = [];

    getRanking(tick: number): Observable<RoundInformation> {
        if (this.round_ranking.hasOwnProperty(tick))
            return of(this.round_ranking[tick]);
        return this.http.get<RoundInformation>(this.url_base + 'scoreboard_round_' + tick + '.json').pipe(
            retryWithBackoff(1500, 10),
            map((json: RoundInformation) => {
                this.round_ranking[json.tick] = json;
                // Check for events that should be triggered
                if (tick == this.currentState.scoreboard_tick && (tick - 1) in this.round_ranking) {
                    let old_firstbloods = {};
                    for (let service of this.round_ranking[tick - 1].services) {
                        old_firstbloods[service.name] = service.first_blood.length;
                    }
                    for (let service of json.services) {
                        for (let i = old_firstbloods[service.name]; i < service.first_blood.length; i++) {
                            this.eventNotifications.next(['firstblood', service.name, service.first_blood[i]]);
                        }
                    }
                    // check for "final" notifications
                    if (this.finalScoreboardTick === tick && this.currentState.state == GameStates.STOPPED) {
                        this.eventNotifications.next(['final', '', '']);
                    }
                    // check for reloads (to get scoreboard updates)
                    else if (tick % 60 == 7) {
                        console.log('Reload scheduled ...');
                        setTimeout(() => {
                            location.reload();
                        }, Math.random() * 50000 + 5000);
                    }
                    // evict caches if services have changed
                    if (JSON.stringify(this.round_ranking[tick - 1].services.map(s => s.name)) != JSON.stringify(json.services.map(s => s.name))) {
                        this.teamPointHistoryCache = {};
                    }
                    // append to cache if necessary
                    for (let teamId of Object.keys(this.teamPointHistoryCache)) {
                        if (this.teamPointHistoryCache[teamId][0].length == tick) {
                            for (let rank of json.scoreboard) {
                                if (rank.team_id.toString() == teamId) {
                                    for (let i = 0; i < rank.services.length; i++) {
                                        this.teamPointHistoryCache[teamId][i].push(rank.services[i].o + rank.services[i].d + rank.services[i].s);
                                    }
                                    break;
                                }
                            }
                        }
                    }
                }
                return json;
            })
        );
    }

    private teamPointHistoryCache = {};

    getTeamPointHistory(team_id: number): Observable<number[][]> {
        if (this.teamPointHistoryCache.hasOwnProperty(team_id) && this.teamPointHistoryCache[team_id][0].length >= this.currentState.current_tick + 1) {
            console.log('Serving from cache: ', team_id);
            return of(this.teamPointHistoryCache[team_id]);
        }
        return this.http.get<TeamHistoryInformation>(this.url_base + 'scoreboard_team_' + team_id + '.json').pipe(
            retryWithBackoff(1500, 3),
            map(json => {
                if (json.points.length > 0)
                    this.teamPointHistoryCache[team_id] = json.points;
                return json.points;
            })
        );
    }

    getTeamPointHistorySimple(team_id: number): Observable<number[]> {
        return this.getTeamPointHistory(team_id).pipe(
            map(points => {
                if (points.length == 0) return [];
                let result = new Array(points[0].length).fill(0);
                for (let i = 0; i < points[0].length; i++) {
                    for (let p of points) {
                        result[i] += p[i];
                    }
                }
                return result;
            })
        );
    }

    getServiceStatHistory(): Observable<ServiceStat[][]> {
        return this.http.get<ServiceStatsInformation>(this.url_base + 'scoreboard_service_stats.json').pipe(
            retryWithBackoff(1500, 3),
            map(json => {
                return json.stats;
            })
        );
    }

    currentState: CurrentStateJson = {
        current_tick: -1,
        state: GameStates.STOPPED,
        current_tick_until: 0,
        scoreboard_tick: -1
    };
    bannedTeams = {};

    newestScoreboardTick = new BehaviorSubject<number>(-1);
    deltaClientToServer: number = 0; // (time on client) - (time on server)
    private lastDateHeader: string = null;
    private finalScoreboardTick: number = null; // the tick to show the final greeting

    /**
     * Events are: (firstblood, servicename, teamname) and (final, '', '')
     */
    eventNotifications = new Subject<[string, string, string]>();

    private updateCurrentState() {
        this.http.get<CurrentStateJson>(this.url_base + 'scoreboard_current.json', {observe: 'response'}).subscribe(response => {
            // Save current state
            let old_state = this.currentState;
            this.currentState = response.body;
            this.bannedTeams = {};
            if (this.currentState.banned_teams) {
                for (let id of this.currentState.banned_teams) {
                    this.bannedTeams[id] = true;
                }
            }

            // Read "Date" header from server and calculate how much this client's clock is off
            let dateHeader = response.headers.get('Date');
            if (dateHeader && dateHeader != this.lastDateHeader) { // if date set and not a request from cache
                this.deltaClientToServer = Math.floor(((new Date()).getTime() - (new Date(dateHeader)).getTime()) / 1000);
                console.log('Time delta', this.deltaClientToServer, dateHeader);
            }
            this.lastDateHeader = dateHeader;

            // Check current state again "soon" (2-10 sec)
            let wait_time = this.currentState.current_tick_until - Math.floor((new Date()).getTime() / 1000);
            if (wait_time < 2 || this.currentState.scoreboard_tick < this.currentState.current_tick - 1) {
                if (this.currentState.state == GameStates.RUNNING) wait_time = 1 + Math.random() * 0.5;
                else if (this.currentState.state == GameStates.SUSPENDED) wait_time = 5;
                else wait_time = 10;
            } else if (wait_time > 10) {
                wait_time = 10;
            }

            // Trigger events
            if (this.currentState.state == GameStates.STOPPED && old_state.state == GameStates.RUNNING) {
                this.finalScoreboardTick = this.currentState.current_tick;
                wait_time = 2;
            }
            if (this.currentState.scoreboard_tick != old_state.scoreboard_tick) {
                this.newestScoreboardTick.next(this.currentState.scoreboard_tick);
            }

            setTimeout(() => this.updateCurrentState(), wait_time * 1000);

        }, err => {
            console.error(err);
            setTimeout(() => this.updateCurrentState(), 5000);
        });
    }

    constructor(private http: HttpClient) {
        this.loadTeams();
        this.updateCurrentState();
        window['triggerFinalNotification'] = () => {
            this.eventNotifications.next(['final', '', '']);
        };
        window['triggerFirstblood'] = () => {
            this.eventNotifications.next(['firstblood', this.round_ranking[Object.keys(this.round_ranking)[0]].services[0].name, this.teams[2].name]);
        };
    }
}
