import {Component, HostListener, OnDestroy, OnInit} from '@angular/core';
import {BackendService} from "../backend.service";
import {Subscription} from "rxjs";
import {RateLimiter} from "../ratelimiter";
import {animate, keyframes, query, stagger, state, style, transition, trigger} from "@angular/animations";
import {UiService} from "../ui.service";
import {Team} from "../models";
import { environment } from '../../environments/environment';


/**
 * Big "first blood" popup showed for every first blood in the game.
 * First blood events are emitted from BackendService.
 * Notifications can be disabled in UiService.
 */
@Component({
	selector: 'app-notification-overlay',
	templateUrl: './notification-overlay.component.html',
	styleUrls: ['./notification-overlay.component.less', './pyro.less'],
	animations: [
		trigger('backdropAnimations', [
			state('*', style({opacity: 1})),
			transition(':enter', [
				style({opacity: 0}),
				animate(500),
			]),
			transition(':leave', [
				animate("400ms 600ms", style({opacity: 0}))
			])
		]),
		trigger('mainAnimations', [
			state('*', style({opacity: 1})),
			transition(':enter', [
				query('.message-what, .message-service, .message-team', [
					style({transform: 'scale(0)', opacity: 0})
				]),
				style({opacity: 0}),
				animate('400ms 500ms'),
				query('.message-what', [
					animate("1500ms 400ms", keyframes([
						style({transform: 'scale(0)', opacity: 0, offset: 0.0}),
						style({transform: 'scale(1.1)', opacity: 0.75, offset: 0.6}),
						style({transform: 'scale(0.9)', opacity: 1, offset: 0.8}),
						style({transform: 'scale(1)', opacity: 1, offset: 1.0})
					]))
				]),
				query('.message-service', [
					animate('800ms 800ms', style({transform: 'scale(1)', opacity: 1}))
				]),
				query('.message-team', [
					animate('800ms 800ms', style({transform: 'scale(1)', opacity: 1}))
				])
			]),
			transition(':leave', [
				animate(400, style({opacity: 0}))
			])
		]),
		trigger('pyroAnimations', [
			state('*', style({opacity: 1})),
			transition(':enter', [
				style({opacity: 0}),
				animate(500),
				transition(':leave', [
					animate("400ms 600ms", style({opacity: 0}))
				])
			]),
			transition(':leave', [
				animate("400ms 600ms", style({opacity: 0}))
			])
		])
	]
})
export class NotificationOverlayComponent implements OnInit, OnDestroy {

	private subscription: Subscription;
	private limiter: RateLimiter = new RateLimiter(12000);

	public teamname: string = null;
	public servicename: string = null;
	public visible = false;
    public teamsInEndscreen = environment.show_teams_in_endscreen;

	constructor(public backend: BackendService, public ui: UiService) {
	}

	ngOnInit() {
		this.subscription = this.limiter.limit(this.backend.eventNotifications).subscribe(x => {
			if (x[0] == 'firstblood') {
				this.firstBlood(x[1], x[2])
			} else if (x[0] == 'final') {
				console.log('Game is over!');
				this.gameover();
			}
		});
	}

	ngOnDestroy(): void {
		this.subscription.unsubscribe();
	}

	firstBlood(service: string, team: string) {
		console.log("FIRST BLOOD: " + team + ' @ ' + service);
		if (!this.ui.showNotifications)
			return;
		this.teamname = team;
		this.servicename = service;
		this.visible = true;
		// Animation time: 5.6sec
		setTimeout(() => {
			this.visible = false;
		}, 10000);
	}

	// Quit notification screen on escape
	@HostListener('document:keydown.escape', ['$event']) onKeydownHandler(event: KeyboardEvent) {
		this.visible = false;
	}


	public pyroBackdropVisible = false;
	public pyroVisible = false;
	public topTeams: Array<[Team, number]> = [];

	pyro() {
		if (!this.ui.showNotifications)
			return;
		this.pyroBackdropVisible = true;
		setTimeout(() => {
			this.pyroVisible = true;
		}, 1000);
		setTimeout(() => {
			this.pyroVisible = false;
			this.pyroBackdropVisible = false;
		}, 30000);
	}

	gameover() {
		this.backend.getRanking(this.backend.currentState.current_tick).subscribe(ranking => {
			this.topTeams = [
				[this.backend.teams[ranking.scoreboard[0].team_id], ranking.scoreboard[0].points],
				[this.backend.teams[ranking.scoreboard[1].team_id], ranking.scoreboard[1].points],
				[this.backend.teams[ranking.scoreboard[2].team_id], ranking.scoreboard[2].points],
			];
			this.pyro();
		});
	}

}
