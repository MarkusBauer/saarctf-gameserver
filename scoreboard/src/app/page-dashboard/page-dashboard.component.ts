import {Component, OnDestroy, OnInit} from '@angular/core';
import {RoundInfoListeningComponent} from "../scoretable/scoretable.component";
import {BackendService} from "../backend.service";
import {UiService} from "../ui.service";
import {ServiceResult} from "../models";

@Component({
    selector: 'app-page-dashboard',
    templateUrl: './page-dashboard.component.html',
    styleUrl: './page-dashboard.component.less',
    standalone: false
})
export class PageDashboardComponent extends RoundInfoListeningComponent implements OnInit, OnDestroy {
    constructor(backend: BackendService, public ui: UiService) {
        super(backend);
    }

    sumCapturedDelta(services: ServiceResult[]) {
        let sum = 0;
        for (let s of services) {
            sum += s.dcap;
        }
        return sum;
    }

    sumStolenDelta(services: ServiceResult[]) {
        let sum = 0;
        for (let s of services) {
            sum += s.dst;
        }
        return sum;
    }

}
