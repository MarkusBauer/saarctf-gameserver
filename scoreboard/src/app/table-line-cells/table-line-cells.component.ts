import {Component, Input, OnInit, ViewChild, ViewContainerRef} from '@angular/core';
import {Rank} from "../models";


export class StatusUtils {
    static statusToClass(status: string): string {
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
			case 'RECOVERING':
				return 'label-info';
			case 'REVOKED':
			case 'PENDING':
			default:
				return 'label-default';
		}
	}

	static statusToTooltip(status: string): string {
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
			case 'RECOVERING':
				return 'Service online, but flags from previous ticks not found';
			case 'CRASH':
				return 'Checker crashed';
			case 'REVOKED':
			case 'PENDING':
				return 'Not checked';
			default:
				return status;
		}
	}

	static statusToText(status: string): string {
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
			case 'RECOVERING':
				return 'rec';
			case 'CRASH':
			case 'REVOKED':
			case 'PENDING':
			default:
				return '-';
		}
	}
}


@Component({
	//selector: 'app-table-line-cells',
	selector: 'tablelinecells',
	templateUrl: './table-line-cells.component.html',
	styleUrls: ['./table-line-cells.component.less']
})
export class TableLineCellsComponent implements OnInit {

	@Input() rank: Rank;
	@Input() tick: number;

	@ViewChild('template', {static: true}) template;

	constructor(private viewContainerRef: ViewContainerRef) {
	}

	ngOnInit(): void {
		this.viewContainerRef.createEmbeddedView(this.template);
	}

	indexTrack(index, item) {
		return index;
	}

	public statusToClass = StatusUtils.statusToClass;
    public statusToTooltip = StatusUtils.statusToTooltip;
    public statusToText = StatusUtils.statusToText;

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
