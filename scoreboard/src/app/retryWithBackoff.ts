import {Observable, of, throwError} from "rxjs";
import {delay, mergeMap, retryWhen} from "rxjs/operators";

export function retryWithBackoff(delayMs: number, maxRetry = 5, backoffMs = 1500) {
	let retries = maxRetry;
	return (src: Observable<any>) => src.pipe(
		retryWhen((errors: Observable<any>) => errors.pipe(
			mergeMap(error => {
				if (retries-- > 0) {
					const backoffTime = delayMs + (maxRetry - retries) * backoffMs;
					return of(error).pipe(delay(backoffTime));
				}
				return throwError(`HTTP request failed after ${maxRetry} attempts.`);
			})
		))
	);
}