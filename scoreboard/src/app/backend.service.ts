import {Injectable} from '@angular/core';
import {RoundInformation, Team} from "./models";
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
		this.http.get<Array<Team>>(this.url_base + 'scoreboard_teams.json')
			.pipe(retryWithBackoff(2000, 20))
			.subscribe(teams => this.teams = teams, err => {
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
				}
				return json;
			})
		);
	}

	currentState: CurrentStateJson = {
		current_tick: -1,
		state: GameStates.STOPPED,
		current_tick_until: 0,
		scoreboard_tick: -1
	};

	newestScoreboardTick = new BehaviorSubject<number>(-1);
	deltaClientToServer: number = 0; // (time on client) - (time on server)
	private lastDateHeader: string = null;
	private finalScoreboardTick: number = null; // the tick to show the final greeting

	eventNotifications = new Subject<[string, string, string]>();

	private updateCurrentState() {
		this.http.get<CurrentStateJson>(this.url_base + 'scoreboard_current.json', {observe: 'response'}).subscribe(response => {
			// Save current state
			let old_state = this.currentState;
			this.currentState = response.body;

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
			setTimeout(() => this.updateCurrentState(), wait_time * 1000);

			// Trigger events
			if (this.currentState.scoreboard_tick != old_state.scoreboard_tick)
				this.newestScoreboardTick.next(this.currentState.scoreboard_tick);
			if (this.currentState.state == GameStates.STOPPED && old_state.state == GameStates.RUNNING) {
				this.finalScoreboardTick = this.currentState.scoreboard_tick;
			}

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
	}
}
