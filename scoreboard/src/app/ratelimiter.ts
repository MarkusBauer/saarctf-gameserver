import {asyncScheduler, Observable, of, SchedulerLike} from "rxjs";
import {concatAll, delay, map} from "rxjs/operators";

/**
 * Limit the value stream of an Observable, ensures at least "delay" milliseconds between two values.
 */
export class RateLimiter {

	private lastValueIssued = 0;

	constructor(private delay: number, private scheduler: SchedulerLike = asyncScheduler) {
	}

	limit<T>(stream: Observable<T>): Observable<T> {
		return stream.pipe(
			map(x => {
				const now = this.scheduler.now();
				const wait = this.lastValueIssued + this.delay - now;
				if (wait > 0) {
					this.lastValueIssued += this.delay;
					return of(x).pipe(delay(Math.min(wait, this.delay), this.scheduler));
				} else {
					this.lastValueIssued = now;
					return [x];
				}
			}),
			concatAll()
		);
	}

}