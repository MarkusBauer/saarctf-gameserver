import {Component, Input, OnInit, ViewChild, ViewContainerRef} from '@angular/core';
import {Service} from "../models";

@Component({
    selector: 'app-table-service-header-cell',
    templateUrl: './table-service-header-cell.component.html',
    styleUrls: ['./table-service-header-cell.component.less'],
    standalone: false
})
export class TableServiceHeaderCellComponent implements OnInit {

	@Input() services: Array<Service>;

	@ViewChild('template', {static: true}) template;

	constructor(private viewContainerRef: ViewContainerRef) {
	}

	ngOnInit(): void {
		this.viewContainerRef.createEmbeddedView(this.template);
	}

	indexTrack(index, item) {
		return index;
	}

}
